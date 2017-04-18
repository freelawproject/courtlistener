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
from django.utils.encoding import force_bytes
from django.utils.timezone import now
from juriscraper.lib.string_utils import harmonize
from juriscraper.pacer import FreeOpinionReport
from requests.exceptions import ChunkedEncodingError, HTTPError, \
    ConnectionError, ReadTimeout
from requests.packages.urllib3.exceptions import ReadTimeoutError

from rest_framework.status import HTTP_403_FORBIDDEN, HTTP_400_BAD_REQUEST

from cl.celery import app
from cl.lib.pacer import PacerXMLParser, lookup_and_save, get_blocked_status, \
    map_pacer_to_cl_id
from cl.lib.recap_utils import get_document_filename, get_bucket_name
from cl.scrapers.models import PACERFreeDocumentLog, PACERFreeDocumentRow
from cl.scrapers.tasks import get_page_count, extract_recap_pdf
from cl.search.models import DocketEntry, RECAPDocument, Court

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
        responses = report.query(start, end, sort='case_number')
    except (ConnectionError, ChunkedEncodingError, ReadTimeoutError) as exc:
        logger.warning("Unable to get free document report results from %s "
                       "(%s to %s). Trying again." % (court_id, start, end))
        raise self.retry(exc=exc, countdown=5)

    try:
        return report.parse(responses)
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
        responses = report.query(start, end, sort='case_number')
    except (ConnectionError, ChunkedEncodingError, ReadTimeoutError,
            ReadTimeout) as exc:
        logger.warning("Unable to get free document report results from %s "
                       "(%s to %s). Trying again." % (court_id, start, end))
        raise self.retry(exc=exc, countdown=10)

    try:
        results = report.parse(responses)
    except (IndexError, HTTPError) as exc:
        # IndexError: When the page isn't downloaded properly.
        # HTTPError: raise_for_status in parse hit bad status.
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
                logger.error("Unable to create docket for %s" % result)
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
                }
            )
    except DatabaseError as e:
        logger.error("Unable to complete database transaction:\n%s" % e)
        return

    if not rd_created and rd.is_available:
        logger.info("Found the item already in the DB with document_number: %s "
                    "and docket_entry: %s!" % (result.document_number, de))
        return

    return {'result': result, 'rd_pk': rd.pk, 'pacer_court_id': result.court_id}


@app.task(bind=True, max_retries=5, ignore_result=True)
def get_and_process_pdf(self, data, session):
    if data is None:
        return
    result = data['result']
    rd = RECAPDocument.objects.get(pk=data['rd_pk'])
    report = FreeOpinionReport(data['pacer_court_id'], session)
    try:
        r = report.download_pdf(result.pacer_case_id, result.pacer_doc_id)
    except (ConnectionError, ChunkedEncodingError, ReadTimeout,
            ReadTimeoutError) as exc:
        logger.warning("Unable to get PDF for %s" % result)
        raise self.retry(exc=exc, countdown=5)

    if r is None:
        logger.error("Unable to get PDF for %s" % result)
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
    rd.save(do_extraction=False, index=False)
    extract_recap_pdf(rd.pk, skip_ocr=True, check_if_needed=False)
    return {'result': result, 'rd_pk': rd.pk}


class OverloadedException(Exception):
    pass


@app.task(bind=True, max_retries=15, ignore_result=True)
def upload_free_opinion_to_ia(self, data):
    if data is None:
        return
    countdown = 5 * self.request.retries + 1  # 5s, 10s, 15s...
    result = data['result']
    rd = RECAPDocument.objects.get(pk=data['rd_pk'])
    file_name = get_document_filename(
        result.court.pk,
        result.pacer_case_id,
        result.document_number,
        0,  # Attachment number is zero for all free opinions.
    )
    bucket_name = get_bucket_name(result.court.pk, result.pacer_case_id)
    try:
        responses = upload_to_ia(
            identifier=bucket_name,
            files=rd.filepath_local.path,
            metadata={
                'title': result.case_name,
                'collection': settings.IA_COLLECTIONS,
                'contributor': '<a href="https://free.law">Free Law Project</a>',
                'court': result.court.pk,
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
    except OverloadedException as exc:
        raise self.retry(exc=exc, countdown=countdown)
    except HTTPError as exc:
        if exc.response.status_code in [
            HTTP_403_FORBIDDEN,    # Can't access bucket, typically.
            HTTP_400_BAD_REQUEST,  # Corrupt PDF, typically.
        ]:
            return [exc.response]
        raise self.retry(exc=exc, countdown=countdown)
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


@app.task(ignore_result=True)
def mark_court_done_on_date(court_id, d):
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
        doc_log.status = PACERFreeDocumentLog.SCRAPE_SUCCESSFUL
        doc_log.date_completed = now()
        doc_log.save()


@app.task(ignore_result=True)
def delete_pacer_row(pk):
    PACERFreeDocumentRow.objects.get(pk=pk).delete()
