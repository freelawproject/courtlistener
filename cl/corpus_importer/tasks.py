import copy
import hashlib
import logging
import os
import shutil
from tempfile import NamedTemporaryFile

import internetarchive as ia
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction, DatabaseError
from django.db.models import Q
from django.utils.encoding import force_bytes
from django.utils.timezone import now
from juriscraper.lib.string_utils import harmonize
from juriscraper.pacer import FreeOpinionReport, PossibleCaseNumberApi, \
    DocketReport, AttachmentPage
from pyexpat import ExpatError
from requests.exceptions import ChunkedEncodingError, HTTPError, \
    ConnectionError, ReadTimeout, ConnectTimeout
from requests.packages.urllib3.exceptions import ReadTimeoutError
from rest_framework.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_504_GATEWAY_TIMEOUT,
)

from cl.celery import app
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.pacer import PacerXMLParser, lookup_and_save, get_blocked_status, \
    map_pacer_to_cl_id, map_cl_to_pacer_id, get_first_missing_de_number
from cl.lib.recap_utils import get_document_filename, get_bucket_name
from cl.recap.models import FjcIntegratedDatabase, PacerHtmlFiles
from cl.recap.tasks import update_docket_metadata, add_parties_and_attorneys
from cl.scrapers.models import PACERFreeDocumentLog, PACERFreeDocumentRow
from cl.scrapers.tasks import get_page_count, extract_recap_pdf
from cl.search.tasks import add_or_update_recap_document
from cl.search.models import DocketEntry, RECAPDocument, Court, Docket, Tag

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=5)
def download_recap_item(self, url, filename, clobber=False):
    logger.info("  Getting item at: %s" % url)
    location = os.path.join(settings.MEDIA_ROOT, 'recap', filename)
    try:
        if os.path.isfile(location) and not clobber:
            raise IOError("    IOError: File already exists at %s" % location)
        r = requests.get(
            url,
            stream=True,
            timeout=60,
            headers={'User-Agent': "Free Law Project"},
        )
        r.raise_for_status()
    except requests.Timeout as e:
        logger.warning("    Timed out attempting to get: %s\n" % url)
        raise self.retry(exc=e, countdown=2)
    except requests.RequestException as e:
        logger.warning("    Unable to get %s\nException was:\n%s" % (url, e))
    except IOError as e:
        logger.warning("    %s" % e)
    else:
        with NamedTemporaryFile(prefix='recap_download_') as tmp:
            r.raw.decode_content = True
            try:
                shutil.copyfileobj(r.raw, tmp)
                tmp.flush()
            except ReadTimeoutError as exc:
                # The download failed part way through.
                raise self.retry(exc=exc)
            else:
                # Successful download. Copy from tmp to the right spot. Note
                # that this will clobber.
                shutil.copyfile(tmp.name, location)


@app.task(bind=True, max_retries=3)
def parse_recap_docket(self, filename, debug=False):
    """Parse a docket path, creating items or updating existing ones."""
    docket_path = os.path.join(settings.MEDIA_ROOT, 'recap', filename)
    recap_pks = []
    try:
        pacer_doc = PacerXMLParser(docket_path)
    except IOError:
        logger.warning("Unable to find the docket at: %s" % docket_path)
    else:
        required_fields = ['case_name', 'date_filed']
        for field in required_fields:
            if not getattr(pacer_doc, field):
                logger.error("Missing required field: %s" % field)
                return recap_pks
        docket = lookup_and_save(pacer_doc, debug=debug)
        if docket is not None:
            try:
                recap_pks = pacer_doc.make_documents(docket, debug=debug)
            except (IntegrityError, DocketEntry.MultipleObjectsReturned) as exc:
                raise self.retry(exc=exc, countdown=20 * 60)
            else:
                pacer_doc.make_parties(docket, debug=debug)

    return recap_pks


@app.task(bind=True, max_retries=5)
def get_free_document_report(self, court_id, start, end, session):
    """Get structured results from the PACER free document report"""
    report = FreeOpinionReport(court_id, session)
    try:
        report.query(start, end, sort='case_number')
    except (ConnectionError, ChunkedEncodingError, ReadTimeoutError,
            ConnectTimeout) as exc:
        logger.warning("Unable to get free document report results from %s "
                       "(%s to %s). Trying again." % (court_id, start, end))
        raise self.retry(exc=exc, countdown=5)

    try:
        return report.data
    except IndexError as exc:
        # Happens when the page isn't downloaded properly, ugh.
        raise self.retry(exc=exc, countdown=15)


@app.task(bind=True, max_retries=20)
def get_and_save_free_document_report(self, court_id, start, end, session):
    """Download the Free document report and save it to the DB.

    :param self: The Celery task.
    :param court_id: A pacer court id.
    :param start: a date object representing the first day to get results.
    :param end: a date object representing the last day to get results.
    :param session: A PACER Session object
    :return: None
    """
    report = FreeOpinionReport(court_id, session)
    try:
        report.query(start, end, sort='case_number')
    except (ConnectionError, ChunkedEncodingError, ReadTimeoutError,
            ReadTimeout, ConnectTimeout) as exc:
        logger.warning("Unable to get free document report results from %s "
                       "(%s to %s). Trying again." % (court_id, start, end))
        if self.request.retries == self.max_retries:
            return PACERFreeDocumentLog.SCRAPE_FAILED
        raise self.retry(exc=exc, countdown=10)

    try:
        results = report.data
    except (IndexError, HTTPError) as exc:
        # IndexError: When the page isn't downloaded properly.
        # HTTPError: raise_for_status in parse hit bad status.
        if self.request.retries == self.max_retries:
            return PACERFreeDocumentLog.SCRAPE_FAILED
        raise self.retry(exc=exc, countdown=10)

    for row in results:
        try:
            PACERFreeDocumentRow.objects.create(
                court_id=row.court_id,
                pacer_case_id=row.pacer_case_id,
                docket_number=row.docket_number,
                case_name=row.case_name,
                date_filed=row.date_filed,
                pacer_doc_id=row.pacer_doc_id,
                document_number=row.document_number,
                description=row.description,
                nature_of_suit=row.nature_of_suit,
                cause=row.cause,
             )
        except IntegrityError:
            # Duplicate for whatever reason.
            continue

    return PACERFreeDocumentLog.SCRAPE_SUCCESSFUL


@app.task(bind=True, max_retries=5, ignore_result=True)
def process_free_opinion_result(self, row_pk, cnt):
    """Process a single result from the free opinion report"""
    result = PACERFreeDocumentRow.objects.get(pk=row_pk)
    result.court = Court.objects.get(pk=map_pacer_to_cl_id(result.court_id))
    result.case_name = harmonize(result.case_name)
    result.case_name_short = cnt.make_case_name_short(result.case_name)
    row_copy = copy.copy(result)
    # If we don't do this, the doc's date_filed becomes the docket's
    # date_filed. Bad.
    delattr(row_copy, 'date_filed')
    # If we don't do this, we get the PACER court id and it crashes
    delattr(row_copy, 'court_id')
    # If we don't do this, the id of result tries to smash that of the docket.
    delattr(row_copy, 'id')
    try:
        with transaction.atomic():
            docket = lookup_and_save(row_copy)
            if not docket:
                msg = "Unable to create docket for %s" % result
                logger.error(msg)
                result.error_msg = msg
                result.save()
                self.request.callbacks = None
                return
            docket.blocked, docket.date_blocked = get_blocked_status(docket)
            docket.save()

            de, de_created = DocketEntry.objects.update_or_create(
                docket=docket,
                entry_number=result.document_number,
                defaults={
                    'date_filed': result.date_filed,
                    'description': result.description,
                }
            )
            rd, rd_created = RECAPDocument.objects.update_or_create(
                docket_entry=de,
                document_number=result.document_number,
                attachment_number=None,
                defaults={
                    'pacer_doc_id': result.pacer_doc_id,
                    'document_type': RECAPDocument.PACER_DOCUMENT,
                    'is_free_on_pacer': True,
                }
            )
    except IntegrityError as e:
        msg = "Raised IntegrityError: %s" % e
        logger.error(msg)
        if self.request.retries == self.max_retries:
            result.error_msg = msg
            result.save()
            return
        raise self.retry(exc=e)
    except DatabaseError as e:
        msg = "Unable to complete database transaction:\n%s" % e
        logger.error(msg)
        result.error_msg = msg
        result.save()
        self.request.callbacks = None
        return

    if not rd_created and rd.is_available:
        # The item already exists and is available. Fantastic, mark it as free,
        # and call it a day.
        rd.is_free_on_pacer = True
        rd.save()
        result.delete()
        self.request.callbacks = None
        return

    return {'result': result, 'rd_pk': rd.pk, 'pacer_court_id': result.court_id}


@app.task(bind=True, max_retries=15, interval_start=5, interval_step=5,
          ignore_result=True)
def get_and_process_pdf(self, data, session, row_pk, index=False):
    if data is None:
        return
    result = data['result']
    rd = RECAPDocument.objects.get(pk=data['rd_pk'])
    report = FreeOpinionReport(data['pacer_court_id'], session)
    try:
        r = report.download_pdf(result.pacer_case_id, result.pacer_doc_id)
    except (ConnectTimeout, ConnectionError, ReadTimeout, ReadTimeoutError,
            ChunkedEncodingError) as exc:
        logger.warning("Unable to get PDF for %s" % result)
        raise self.retry(exc=exc)
    except HTTPError as exc:
        if exc.response.status_code in [HTTP_500_INTERNAL_SERVER_ERROR,
                                        HTTP_504_GATEWAY_TIMEOUT]:
            logger.warning("Ran into HTTPError: %s. Retrying." %
                           exc.response.status_code)
            raise self.retry(exc)
        else:
            msg = "Ran into unknown HTTPError. %s. Aborting." % \
                  exc.response.status_code
            logger.error(msg)
            PACERFreeDocumentRow.objects.filter(pk=row_pk).update(error_msg=msg)
            self.request.callbacks = None
            return

    if r is None:
        msg = "Unable to get PDF for %s at %s with doc id %s" % \
              (result, result.court_id, result.pacer_doc_id)
        logger.error(msg)
        PACERFreeDocumentRow.objects.filter(pk=row_pk).update(error_msg=msg)
        self.request.callbacks = None
        return

    file_name = get_document_filename(
        result.court.pk,
        result.pacer_case_id,
        result.document_number,
        0,  # Attachment number is zero for all free opinions.
    )
    cf = ContentFile(r.content)
    rd.filepath_local.save(file_name, cf, save=False)
    rd.is_available = True  # We've got the PDF.

    # request.content is sometimes a str, sometimes unicode, so
    # force it all to be bytes, pleasing hashlib.
    rd.sha1 = hashlib.sha1(force_bytes(r.content)).hexdigest()
    rd.is_free_on_pacer = True
    rd.page_count = get_page_count(rd.filepath_local.path, 'pdf')

    # Save and extract, skipping OCR.
    rd.save(do_extraction=False, index=index)
    extract_recap_pdf(rd.pk, skip_ocr=True, check_if_needed=False)
    return {'result': result, 'rd_pk': rd.pk}


class OverloadedException(Exception):
    pass


@app.task(bind=True, max_retries=15, interval_start=5, interval_step=5)
def upload_free_opinion_to_ia(self, rd_pk):
    rd = RECAPDocument.objects.get(pk=rd_pk)
    d = rd.docket_entry.docket
    file_name = get_document_filename(
        d.court_id,
        d.pacer_case_id,
        rd.document_number,
        0,  # Attachment number is zero for all free opinions.
    )
    bucket_name = get_bucket_name(d.court_id, d.pacer_case_id)
    try:
        responses = upload_to_ia(
            identifier=bucket_name,
            files=rd.filepath_local.path,
            metadata={
                'title': best_case_name(d),
                'collection': settings.IA_COLLECTIONS,
                'contributor': '<a href="https://free.law">Free Law Project</a>',
                'court': d.court_id,
                'language': 'eng',
                'mediatype': 'texts',
                'description': "This item represents a case in PACER, "
                               "the U.S. Government's website for "
                               "federal case data. If you wish to see "
                               "the entire case, please consult PACER "
                               "directly.",
                'licenseurl': 'https://www.usa.gov/government-works',
            },
        )
    except (OverloadedException, ExpatError) as exc:
        # Overloaded: IA wants us to slow down.
        # ExpatError: The syntax of the XML file that's supposed to be returned
        #             by IA is bad (or something).
        if self.request.retries == self.max_retries:
            # Give up for now. It'll get done next time cron is run.
            return
        raise self.retry(exc=exc)
    except HTTPError as exc:
        if exc.response.status_code in [
            HTTP_403_FORBIDDEN,    # Can't access bucket, typically.
            HTTP_400_BAD_REQUEST,  # Corrupt PDF, typically.
        ]:
            return [exc.response]
        if self.request.retries == self.max_retries:
            # This exception is also raised when the endpoint is overloaded, but
            # doesn't get caught in the OverloadedException below due to
            # multiple processes running at the same time. Just give up for now.
            return
        raise self.retry(exc=exc)
    except (requests.Timeout, requests.RequestException) as exc:
        logger.warning("Timeout or unknown RequestException. Unable to upload "
                       "to IA. Trying again if retries not exceeded: %s" % rd)
        if self.request.retries == self.max_retries:
            # Give up for now. It'll get done next time cron is run.
            return
        raise self.retry(exc=exc)
    if all(r.ok for r in responses):
        rd.filepath_ia = "https://archive.org/download/%s/%s" % (
            bucket_name, file_name)
        rd.save(do_extraction=False, index=False)


access_key = settings.IA_ACCESS_KEY
secret_key = settings.IA_SECRET_KEY
session = ia.get_session({'s3': {
    'access': access_key,
    'secret': secret_key,
}})


def upload_to_ia(identifier, files, metadata=None):
    """Upload an item and its files to the Internet Archive

    On the Internet Archive there are Items and files. Items have a global
    identifier, and files go inside the item:

        https://internetarchive.readthedocs.io/en/latest/items.html

    This function mirrors the IA library's similar upload function, but builds
    in retries and various assumptions that make sense. Note that according to
    emails with IA staff, it is best to maximize the number of files uploaded to
    an Item at a time, rather than uploading each file in a separate go.

    :param identifier: The global identifier within IA for the item you wish to
    work with.
    :param files: The filepaths or file-like objects to upload. This value can
    be an iterable or a single file-like object or string.
    :param metadata: Metadata used to create a new item. If the item already
    exists, the metadata will not be updated

    :rtype: list
    :returns: List of response objects, one per file.
    """
    metadata = {} if metadata is None else metadata
    logger.info("Uploading file to Internet Archive with identifier: %s and "
                "files %s" % (identifier, files))
    try:
        item = session.get_item(identifier)
    except AttributeError:
        logger.info(session.__dict__)
        raise
    # Before pushing files, check if the endpoint is overloaded. This is
    # lighter-weight than attempting a document upload off the bat.
    if session.s3_is_overloaded(identifier, access_key):
        raise OverloadedException("S3 is currently overloaded.")
    responses = item.upload(files=files, metadata=metadata,
                            queue_derive=False, verify=True)
    logger.info("Item uploaded to IA with responses %s" %
                [r.status_code for r in responses])
    return responses


@app.task
def mark_court_done_on_date(status, court_id, d):
    court_id = map_pacer_to_cl_id(court_id)
    try:
        doc_log = PACERFreeDocumentLog.objects.filter(
            status=PACERFreeDocumentLog.SCRAPE_IN_PROGRESS,
            court_id=court_id,
        ).latest('date_queried')
    except PACERFreeDocumentLog.DoesNotExist:
        return
    else:
        doc_log.date_queried = d
        doc_log.status = status
        doc_log.date_completed = now()
        doc_log.save()

    return status


@app.task(ignore_result=True)
def delete_pacer_row(pk):
    PACERFreeDocumentRow.objects.get(pk=pk).delete()


@app.task(bind=True, max_retries=2, interval_start=5 * 60,
          interval_step=10 * 60, ignore_result=True)
def get_pacer_case_id_for_idb_row(self, pk, session):
    """Populate the pacer_case_id field in the FJC IDB table for an item in the
    IDB table
    """
    logger.info("Getting pacer_case_id for IDB item with pk %s" % pk)
    item = FjcIntegratedDatabase.objects.get(pk=pk)
    pcn = PossibleCaseNumberApi(map_cl_to_pacer_id(item.district_id), session)
    pcn.query(item.docket_number)
    d = pcn.data(case_name='%s v. %s' % (item.plaintiff, item.defendant))
    if d is not None:
        item.pacer_case_id = d['pacer_case_id']
        item.case_name = d['title']
    else:
        # Hack. Storing the error in here will bite us later.
        item.pacer_case_id = "Error"
    item.save()


@app.task(bind=True, max_retries=5, interval_start=5 * 60,
          interval_step=10 * 60, ignore_result=True)
def get_docket_by_pacer_case_id(self, pacer_case_id, court_id, session,
                                tag=None, **kwargs):
    """Get a docket by PACER case id, CL court ID, and a collection of kwargs
    that can be passed to the DocketReport query.

    For details of acceptable parameters, see DocketReport.query()

    :param pacer_case_id: The internal case ID of the item in PACER.
    :param court_id: A courtlistener court ID.
    :param session: A valid PacerSession object.
    :param tag: The tag name that should be stored with the item in the DB.
    :param kwargs: A variety of keyword args to pass to DocketReport.query().
    """
    report = DocketReport(map_cl_to_pacer_id(court_id), session)
    logger.info("Querying docket report %s.%s" % (court_id, pacer_case_id))
    try:
        d = Docket.objects.get(
            pacer_case_id=pacer_case_id,
            court_id=court_id,
        )
    except Docket.DoesNotExist:
        d = None
    except Docket.MultipleObjectsReturned:
        d = None

    if d is not None:
        first_missing_id = get_first_missing_de_number(d)
        if d is not None and first_missing_id > 1:
            # We don't have to get the whole thing!
            kwargs.setdefault('doc_num_start', first_missing_id)

    report.query(pacer_case_id, **kwargs)
    docket_data = report.data
    logger.info("Querying and parsing complete for %s.%s" % (court_id,
                                                             pacer_case_id))

    # Merge the contents into CL.
    try:
        if d is None:
            d = Docket.objects.get(
                Q(pacer_case_id=pacer_case_id) |
                Q(docket_number=docket_data['docket_number']),
                court_id=court_id,
            )
        # Add RECAP as a source if it's not already.
        if d.source in [Docket.DEFAULT, Docket.SCRAPER]:
            d.source = Docket.RECAP_AND_SCRAPER
        elif d.source == Docket.COLUMBIA:
            d.source = Docket.COLUMBIA_AND_RECAP
        elif d.source == Docket.COLUMBIA_AND_SCRAPER:
            d.source = Docket.COLUMBIA_AND_RECAP_AND_SCRAPER
    except Docket.DoesNotExist:
        d = Docket(
            source=Docket.RECAP,
            pacer_case_id=pacer_case_id,
            court_id=court_id
        )
    except Docket.MultipleObjectsReturned:
        logger.error("Too many dockets returned when trying to look up '%s.%s'" %
                     (court_id, pacer_case_id))
        return None

    update_docket_metadata(d, docket_data)
    d.save()
    if tag is not None:
        tag, _ = Tag.objects.get_or_create(name=tag)
        d.tags.add(tag)

    # Add the HTML to the docket in case we need it someday.
    pacer_file = PacerHtmlFiles(content_object=d)
    pacer_file.filepath.save(
        'docket.html',  # We only care about the ext w/UUIDFileSystemStorage
        ContentFile(report.response.text),
    )

    for docket_entry in docket_data['docket_entries']:
        try:
            de, created = DocketEntry.objects.update_or_create(
                docket=d,
                entry_number=docket_entry['document_number'],
                defaults={
                    'description': docket_entry['description'],
                    'date_filed': docket_entry['date_filed'],
                }
            )
        except DocketEntry.MultipleObjectsReturned:
            logger.error(
                "Multiple docket entries found for document entry number '%s' "
                "while processing '%s.%s'" % (docket_entry['document_number'],
                                              court_id, pacer_case_id)
            )
            continue
        else:
            if tag is not None:
                de.tags.add(tag)

        try:
            rd = RECAPDocument.objects.get(
                docket_entry=de,
                # No attachments when uploading dockets.
                document_type=RECAPDocument.PACER_DOCUMENT,
                document_number=docket_entry['document_number'],
            )
        except RECAPDocument.DoesNotExist:
            try:
                rd = RECAPDocument.objects.create(
                    docket_entry=de,
                    # No attachments when uploading dockets.
                    document_type=RECAPDocument.PACER_DOCUMENT,
                    document_number=docket_entry['document_number'],
                    pacer_doc_id=docket_entry['pacer_doc_id'],
                    is_available=False,
                )
            except IntegrityError:
                # Race condition. The item was created after our get failed.
                rd = RECAPDocument.objects.get(
                    docket_entry=de,
                    # No attachments when uploading dockets.
                    document_type=RECAPDocument.PACER_DOCUMENT,
                    document_number=docket_entry['document_number'],
                )
        except RECAPDocument.MultipleObjectsReturned:
            logger.error(
                "Multiple recap documents found for document entry "
                "number: '%s', docket: %s" % (docket_entry['document_number'], d)
            )
            continue

        rd.pacer_doc_id = rd.pacer_doc_id or docket_entry['pacer_doc_id']
        if tag is not None:
            rd.tags.add(tag)

    add_parties_and_attorneys(d, docket_data['parties'])
    logger.info("Created/updated docket: %s" % d)

    return d


@app.task(bind=True, max_retries=15, interval_start=5,
          interval_step=5, ignore_result=True)
def get_pacer_doc_by_rd_and_description(self, rd_pk, description_re, session,
                                        tag=None):
    """Using a RECAPDocument object ID and a description of a document, get the
    document from PACER.

    This function was originally meant to get civil cover sheets, but can be
    repurposed as needed.

    :param rd_pk: The PK of a RECAPDocument object to use as a source.
    :param description_re: A compiled regular expression to search against the
    description provided by the attachment page.
    :param session: The PACER session object to use.
    :param tag: A tag name to apply to any downloaded content.
    :return: None
    """
    rd = RECAPDocument.objects.get(pk=rd_pk)
    d = rd.docket_entry.docket
    pacer_court_id = map_cl_to_pacer_id(d.court_id)
    att_report = AttachmentPage(pacer_court_id, session)
    try:
        att_report.query(rd.pacer_doc_id)
    except (ConnectTimeout, ConnectionError, ReadTimeout, ReadTimeoutError,
            ChunkedEncodingError) as exc:
        logger.warning("Unable to get PDF for %s" % rd)
        raise self.retry(exc=exc)
    except HTTPError as exc:
        if exc.response.status_code in [HTTP_500_INTERNAL_SERVER_ERROR,
                                        HTTP_504_GATEWAY_TIMEOUT]:
            logger.warning("Ran into HTTPError: %s. Retrying." %
                           exc.response.status_code)
            raise self.retry(exc)
        else:
            msg = "Ran into unknown HTTPError. %s. Aborting." % \
                  exc.response.status_code
            logger.error(msg)
            self.request.callbacks = None
            return

    att_found = None
    for attachment in att_report.data['attachments']:
        if description_re.search(attachment['description']):
            att_found = attachment.copy()
            break

    if not att_found:
        msg = "Aborting. Did not find civil cover sheet for %s." % rd
        logger.error(msg)
        self.request.callbacks = None
        return

    # Try to find the item already in the collection
    rd, _ = RECAPDocument.objects.get_or_create(
        docket_entry=rd.docket_entry,
        document_number=1,
        attachment_number=att_found['attachment_number'],
        pacer_doc_id=att_found['pacer_doc_id'],
        document_type=RECAPDocument.ATTACHMENT,
        defaults={
            'date_upload': now(),
        },
    )
    rd.description = att_found['description']
    if tag is not None:
        tag, _ = Tag.objects.get_or_create(name=tag)
        rd.tags.add(tag)

    if rd.is_available:
        # Great. Call it a day.
        rd.save(do_extraction=False, index=False)
        return

    # Not available. Go get it.
    try:
        pacer_case_id = rd.docket_entry.docket.pacer_case_id
        r = att_report.download_pdf(pacer_case_id, att_found['pacer_doc_id'])
    except (ConnectTimeout, ConnectionError, ReadTimeout, ReadTimeoutError,
            ChunkedEncodingError) as exc:
        logger.warning("Unable to get PDF for %s" % att_found['pacer_doc_id'])
        raise self.retry(exc=exc)
    except HTTPError as exc:
        if exc.response.status_code in [HTTP_500_INTERNAL_SERVER_ERROR,
                                        HTTP_504_GATEWAY_TIMEOUT]:
            logger.warning("Ran into HTTPError: %s. Retrying." %
                           exc.response.status_code)
            raise self.retry(exc)
        else:
            msg = "Ran into unknown HTTPError. %s. Aborting." % \
                  exc.response.status_code
            logger.error(msg)
            self.request.callbacks = None
            return

    if r is None:
        msg = "Unable to get PDF for %s at PACER court '%s' with doc id %s" % \
              (rd, pacer_court_id, rd.pacer_doc_id)
        logger.error(msg)
        self.request.callbacks = None
        return

    file_name = get_document_filename(
        d.court_id,
        pacer_case_id,
        rd.document_number,
        rd.attachment_number,
    )
    cf = ContentFile(r.content)
    rd.filepath_local.save(file_name, cf, save=False)
    rd.is_available = True  # We've got the PDF.

    # request.content is sometimes a str, sometimes unicode, force it all to be
    # bytes, pleasing hashlib.
    rd.sha1 = hashlib.sha1(force_bytes(r.content)).hexdigest()
    rd.page_count = get_page_count(rd.filepath_local.path, 'pdf')

    # Save, extract, then save to Solr. Skip OCR for now. Don't do these async.
    rd.save(do_extraction=False, index=False)
    extract_recap_pdf(rd.pk, skip_ocr=True)
    add_or_update_recap_document([rd.pk])
