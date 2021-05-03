import copy
import logging
import os
import shutil
from datetime import date
from io import BytesIO
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Tuple, Union, re

import internetarchive as ia
import requests
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Prefetch
from django.db.models.query import prefetch_related_objects
from django.utils.encoding import force_bytes
from django.utils.timezone import now
from juriscraper.lib.exceptions import PacerLoginException, ParsingException
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize
from juriscraper.pacer import (
    AppellateDocketReport,
    AttachmentPage,
    CaseQuery,
    ClaimsRegister,
    DocketReport,
    FreeOpinionReport,
    PacerSession,
    PossibleCaseNumberApi,
    ShowCaseDocApi,
)
from pyexpat import ExpatError
from requests import Response
from requests.cookies import RequestsCookieJar
from requests.exceptions import HTTPError, RequestException
from requests.packages.urllib3.exceptions import ReadTimeoutError
from rest_framework.renderers import JSONRenderer
from rest_framework.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_504_GATEWAY_TIMEOUT,
)

from cl.alerts.tasks import enqueue_docket_alert, send_docket_alert
from cl.audio.models import Audio
from cl.celery_init import app
from cl.corpus_importer.api_serializers import IADocketSerializer
from cl.corpus_importer.utils import mark_ia_upload_needed
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.celery_utils import throttle_task
from cl.lib.crypto import sha1
from cl.lib.pacer import (
    get_blocked_status,
    get_first_missing_de_date,
    lookup_and_save,
    map_cl_to_pacer_id,
    map_pacer_to_cl_id,
)
from cl.lib.pacer_session import (
    get_or_cache_pacer_cookies,
    get_pacer_cookie_from_cache,
)
from cl.lib.recap_utils import (
    get_bucket_name,
    get_docket_filename,
    get_document_filename,
)
from cl.people_db.models import Attorney, Role
from cl.recap.constants import CR_2017, CR_OLD, CV_2017, CV_2020, CV_OLD
from cl.recap.mergers import (
    add_bankruptcy_data_to_docket,
    add_claims_to_docket,
    add_tags_to_objs,
    find_docket_object,
    make_recap_sequence_number,
    merge_pacer_docket_into_cl_docket,
    save_iquery_to_docket,
    update_docket_metadata,
)
from cl.recap.models import (
    UPLOAD_TYPE,
    FjcIntegratedDatabase,
    PacerHtmlFiles,
    ProcessingQueue,
)
from cl.scrapers.models import PACERFreeDocumentLog, PACERFreeDocumentRow
from cl.scrapers.tasks import extract_recap_pdf, get_page_count
from cl.search.models import (
    ClaimHistory,
    Court,
    Docket,
    DocketEntry,
    RECAPDocument,
    Tag,
)
from cl.search.tasks import add_items_to_solr

logger = logging.getLogger(__name__)


def increment_failure_count(obj: Union[Audio, Docket, RECAPDocument]) -> None:
    if obj.ia_upload_failure_count is None:
        obj.ia_upload_failure_count = 1
    else:
        obj.ia_upload_failure_count += 1
    obj.save()


def generate_ia_json(
    d_pk: int,
    database: str = "default",
) -> Tuple[Docket, str]:
    """Generate JSON for upload to Internet Archive

    :param d_pk: The PK of the docket to generate JSON for
    :param database: The name of the database to use for the queries
    :return: A tuple of the docket object requested and a string of json data
    to upload.
    """
    # This is a pretty highly optimized query that minimizes the hits to the DB
    # when generating a docket JSON rendering, regardless of how many related
    # objects the docket has such as docket entries, parties, etc.
    ds = (
        Docket.objects.filter(pk=d_pk)
        .select_related(
            "originating_court_information",
            "bankruptcy_information",
            "idb_data",
        )
        .prefetch_related(
            "panel",
            "parties",
            # Django appears to have a bug where you can't defer a field on a
            # queryset where you prefetch the values. If you try to, it
            # crashes. We should be able to just do the prefetch below like
            # the ones above and then do the defer statement at the end, but
            # that throws an error.
            Prefetch(
                "docket_entries__recap_documents",
                queryset=RECAPDocument.objects.all().defer("plain_text"),
            ),
            Prefetch(
                "claims__claim_history_entries",
                queryset=ClaimHistory.objects.all().defer("plain_text"),
            ),
        )
        .using(database)
    )
    d = ds[0]

    # Prefetching attorneys needs to be done in a second pass where we can
    # access the party IDs identified above. If we don't do it this way, Django
    # generates a bad query that double-joins the attorney table to the role
    # table. See notes in #901. Doing this way makes for a very large query,
    # but one that is fairly efficient since the double-join, while still
    # there, appears to be ignored by the query planner.
    # Do not add a `using` method here, it causes an additional (unnecessary)
    # query to be run. I think this is a Django bug.
    party_ids = [p.pk for p in d.parties.all()]
    attorney_prefetch = Prefetch(
        "parties__attorneys",
        queryset=Attorney.objects.filter(
            roles__docket_id=d_pk, parties__id__in=party_ids
        )
        .distinct()
        .prefetch_related(
            Prefetch(
                # Only roles for those attorneys in the docket.
                "roles",
                queryset=Role.objects.filter(docket_id=d_pk),
            )
        ),
    )
    prefetch_related_objects(
        [d],
        *[
            "parties__party_types__criminal_complaints",
            "parties__party_types__criminal_counts",
            attorney_prefetch,
        ],
    )

    renderer = JSONRenderer()
    json_str = renderer.render(
        IADocketSerializer(d).data,
        accepted_media_type="application/json; indent=2",
    ).decode()
    return d, json_str


@app.task(bind=True, ignore_result=True)
def save_ia_docket_to_disk(self, d_pk: int, output_directory: str) -> None:
    """For each docket given, save it to disk.

    :param self: The celery task
    :param d_pk: The PK of the docket to serialize to disk
    :param output_directory: The location to save the docket's JSON
    """
    _, j = generate_ia_json(d_pk)
    with open(os.path.join(output_directory, "%s.json" % d_pk), "w") as f:
        f.write(j)


@app.task(bind=True, ignore_result=True)
def upload_recap_json(self, pk: int, database: str = "default") -> None:
    """Make a JSON object for a RECAP docket and upload it to IA"""
    d, json_str = generate_ia_json(pk, database=database)

    file_name = get_docket_filename(d.court_id, d.pacer_case_id, "json")
    bucket_name = get_bucket_name(d.court_id, d.pacer_case_id)
    responses = upload_to_ia(
        self,
        identifier=bucket_name,
        files={file_name: BytesIO(json_str.encode())},
        title=best_case_name(d),
        collection=settings.IA_COLLECTIONS,
        court_id=d.court_id,
        source_url="https://www.courtlistener.com%s" % d.get_absolute_url(),
        media_type="texts",
        description="This item represents a case in PACER, the U.S. "
        "Government's website for federal case data. This "
        "information is uploaded quarterly. To see our most "
        "recent version please use the source url parameter, "
        "linked below. To see the canonical source for this data, "
        "please consult PACER directly.",
    )
    if responses is None:
        increment_failure_count(d)
        return

    if all(r.ok for r in responses):
        d.ia_upload_failure_count = None
        d.ia_date_first_changed = None
        d.ia_needs_upload = False
        d.filepath_ia_json = "https://archive.org/download/%s/%s" % (
            bucket_name,
            file_name,
        )
        d.save()
    else:
        increment_failure_count(d)


@app.task(bind=True, max_retries=5)
def download_recap_item(
    self,
    url: str,
    filename: str,
    clobber: bool = False,
) -> None:
    logger.info("  Getting item at: %s" % url)
    location = os.path.join(settings.MEDIA_ROOT, "recap", filename)
    try:
        if os.path.isfile(location) and not clobber:
            raise IOError("    IOError: File already exists at %s" % location)
        r = requests.get(
            url,
            stream=True,
            timeout=60,
            headers={"User-Agent": "Free Law Project"},
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
        with NamedTemporaryFile(prefix="recap_download_") as tmp:
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


@app.task(bind=True, max_retries=2, soft_time_limit=240)
def get_and_save_free_document_report(
    self: Task,
    court_id: str,
    start: date,
    end: date,
) -> int:
    """Download the Free document report and save it to the DB.

    :param self: The Celery task.
    :param court_id: A pacer court id.
    :param start: a date object representing the first day to get results.
    :param end: a date object representing the last day to get results.
    :return: The status code of the scrape
    """
    cookies = get_or_cache_pacer_cookies(
        "pacer_scraper",
        username=settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    s = PacerSession(
        cookies=cookies,
        username=settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    report = FreeOpinionReport(court_id, s)
    msg = None
    try:
        report.query(start, end, sort="case_number")
    except (
        TypeError,
        RequestException,
        ReadTimeoutError,
        PacerLoginException,
        ParsingException,
        SoftTimeLimitExceeded,
    ) as exc:
        if isinstance(exc, TypeError):
            msg = (
                "TypeError getting free document report results, likely due "
                "to failure to get Nonce."
            )
        elif isinstance(exc, (RequestException, ReadTimeoutError)):
            msg = (
                "Unable to get free document report results at %s (%s to %s)."
            )
        elif isinstance(exc, PacerLoginException):
            msg = (
                "PacerLoginException while getting free docs at %s (%s to %s)."
            )
        elif isinstance(exc, ParsingException):
            msg = "Didn't get nonce at %s (%s to %s)."
        elif isinstance(exc, SoftTimeLimitExceeded):
            msg = "Soft time limit exceeded at %s (%s to %s)."

        if self.request.retries == self.max_retries:
            logger.error(msg, court_id, start, end)
            return PACERFreeDocumentLog.SCRAPE_FAILED
        logger.info(msg + " Retrying.", court_id, start, end)
        raise self.retry(exc=exc, countdown=5)

    try:
        results = report.data
    except (IndexError, HTTPError) as exc:
        # IndexError: When the page isn't downloaded properly.
        # HTTPError: raise_for_status in parse hit bad status.
        if self.request.retries == self.max_retries:
            return PACERFreeDocumentLog.SCRAPE_FAILED
        raise self.retry(exc=exc, countdown=5)

    for row in results:
        PACERFreeDocumentRow.objects.create(
            court_id=row.court_id,
            pacer_case_id=row.pacer_case_id,
            docket_number=row.docket_number,
            case_name=row.case_name,
            date_filed=row.date_filed,
            pacer_doc_id=row.pacer_doc_id,
            pacer_seq_no=row.pacer_seq_no,
            document_number=row.document_number,
            description=row.description,
            nature_of_suit=row.nature_of_suit,
            cause=row.cause,
        )

    return PACERFreeDocumentLog.SCRAPE_SUCCESSFUL


@app.task(bind=True, max_retries=5, ignore_result=True)
@throttle_task("2/s", key="court_id", jitter=(5, 10))
def process_free_opinion_result(
    self,
    row_pk: int,
    court_id: str,
    cnt: CaseNameTweaker,
) -> Optional[Dict[str, Union[PACERFreeDocumentRow, str, int]]]:
    """Add data from a free opinion report to our DB

    :param self: The celery task
    :param row_pk: The pk of the PACERFreeDocumentRow to get
    :param court_id: The court where the item was found, used for throttling
    :param cnt: A case name tweaker, since they're expensive to initialize
    :return a dict containing the free document row, the court id, etc.
    """
    try:
        result = PACERFreeDocumentRow.objects.get(pk=row_pk)
    except PACERFreeDocumentRow.DoesNotExist:
        logger.warning("Unable to find PACERFreeDocumentRow: %s" % row_pk)
        self.request.chain = None
        return

    result.court = Court.objects.get(pk=map_pacer_to_cl_id(result.court_id))
    result.case_name = harmonize(result.case_name)
    result.case_name_short = cnt.make_case_name_short(result.case_name)
    row_copy = copy.copy(result)
    # If we don't do this, the doc's date_filed becomes the docket's
    # date_filed. Bad.
    delattr(row_copy, "date_filed")
    # If we don't do this, we get the PACER court id and it crashes
    delattr(row_copy, "court_id")
    # If we don't do this, the id of result tries to smash that of the docket.
    delattr(row_copy, "id")
    start_time = now()
    try:
        with transaction.atomic():
            d = lookup_and_save(row_copy)
            if not d:
                msg = "Unable to create docket for %s" % result
                logger.error(msg)
                result.error_msg = msg
                result.save()
                self.request.chain = None
                return
            d.blocked, d.date_blocked = get_blocked_status(d)
            mark_ia_upload_needed(d, save_docket=False)
            d.save()

            try:
                de, _ = DocketEntry.objects.update_or_create(
                    docket=d,
                    entry_number=result.document_number,
                    defaults={
                        "date_filed": result.date_filed,
                        "description": result.description,
                    },
                )
            except DocketEntry.MultipleObjectsReturned:
                # This shouldn't happen, but sometimes it does. Handle it.
                de = DocketEntry.objects.filter(
                    docket=d, entry_number=result.document_number
                ).earliest("pk")
                de.date_filed = result.date_filed
                de.description = result.description

            # Update the psn if we have a new value
            de.pacer_sequence_number = (
                result.pacer_seq_no or de.pacer_sequence_number
            )
            # When rsn is generated by the free opinion report, it's poor
            # quality (these entries come in isolation). When it is generated
            # by a docket or other source, it tends to be better. Prefer an
            # existing rsn if we have it.
            recap_sequence_number = make_recap_sequence_number(
                {"date_filed": result.date_filed, "recap_sequence_index": 1}
            )
            de.recap_sequence_number = (
                de.recap_sequence_number or recap_sequence_number
            )
            de.save()
            rds = RECAPDocument.objects.filter(
                docket_entry=de,
                document_number=result.document_number,
                attachment_number=None,
            )
            rd_count = rds.count()
            if rd_count == 0:
                rd = RECAPDocument.objects.create(
                    docket_entry=de,
                    document_number=result.document_number,
                    attachment_number=None,
                    pacer_doc_id=result.pacer_doc_id,
                    document_type=RECAPDocument.PACER_DOCUMENT,
                    is_free_on_pacer=True,
                )
                rd_created = True
            elif rd_count > 0:
                # Could be one item (great!) or more than one (not great).
                # Choose the earliest item and upgrade it.
                rd = rds.earliest("date_created")
                rd.pacer_doc_id = result.pacer_doc_id
                rd.document_type = RECAPDocument.PACER_DOCUMENT
                rd.is_free_on_pacer = True
                rd.save()
                rd_created = False
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
        self.request.chain = None
        return

    if not rd_created and rd.is_available:
        # The item already exists and is available. Fantastic. Call it a day.
        result.delete()
        self.request.chain = None
        return

    if rd_created:
        newly_enqueued = enqueue_docket_alert(d.pk)
        if newly_enqueued:
            send_docket_alert(d.pk, start_time)

    return {
        "result": result,
        "rd_pk": rd.pk,
        "pacer_court_id": result.court_id,
    }


@app.task(
    bind=True,
    max_retries=15,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
def get_and_process_free_pdf(
    self: Task,
    data: Dict[str, Union[PACERFreeDocumentRow, int, str]],
    row_pk: int,
) -> Optional[Dict[str, Union[FreeOpinionReport, int]]]:
    """Get a PDF from a PACERFreeDocumentRow object

    :param self: The celery task
    :param data: The returned results from the previous task, takes the form
    of:
        {'result': <PACERFreeDocumentRow> object,
         'rd_pk': rd.pk,
         'pacer_court_id': result.court_id}
    :param row_pk: The PACERFreeDocumentRow operate on
    """
    if data is None:
        return
    result = data["result"]
    rd = RECAPDocument.objects.get(pk=data["rd_pk"])
    cookies = get_or_cache_pacer_cookies(
        "pacer_scraper",
        username=settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    try:
        r = download_pacer_pdf_by_rd(
            rd.pk, result.pacer_case_id, result.pacer_doc_id, cookies
        )
    except PacerLoginException as exc:
        msg = "PacerLoginException while getting free docs."
        if self.request.retries == self.max_retries:
            logger.warning(msg)
            self.request.chain = None
            return
        logger.info(msg + " Retrying.")
        raise self.retry(exc=exc)
    except (ReadTimeoutError, requests.RequestException) as exc:
        msg = "Request exception getting free PDF"
        if self.request.retries == self.max_retries:
            logger.warning(msg)
            self.request.chain = None
            return
        logger.info(msg + " Retrying.")
        raise self.retry(exc=exc)

    attachment_number = 0  # Always zero for free opinions
    success, msg = update_rd_metadata(
        self,
        rd.pk,
        r,
        result.court_id,
        result.pacer_case_id,
        result.pacer_doc_id,
        result.document_number,
        attachment_number,
    )

    if success is False:
        PACERFreeDocumentRow.objects.filter(pk=row_pk).update(error_msg=msg)
        return

    rd.refresh_from_db()
    rd.is_free_on_pacer = True
    rd.save()

    # Get the data temporarily. OCR is done for all nightly free
    # docs in a separate batch, but may as well do the easy ones.
    extract_recap_pdf(rd.pk, skip_ocr=True, check_if_needed=False)
    return {"result": result, "rd_pk": rd.pk}


class OverloadedException(Exception):
    pass


@app.task(bind=True, max_retries=15, interval_start=5, interval_step=5)
def upload_pdf_to_ia(self: Task, rd_pk: int) -> None:
    rd = RECAPDocument.objects.get(pk=rd_pk)
    d = rd.docket_entry.docket
    file_name = get_document_filename(
        d.court_id,
        d.pacer_case_id,
        rd.document_number,
        rd.attachment_number or 0,
    )
    bucket_name = get_bucket_name(d.court_id, d.pacer_case_id)
    responses = upload_to_ia(
        self,
        identifier=bucket_name,
        files={file_name: rd.filepath_local},
        title=best_case_name(d),
        collection=settings.IA_COLLECTIONS,
        court_id=d.court_id,
        source_url="https://www.courtlistener.com%s" % rd.get_absolute_url(),
        media_type="texts",
        description="This item represents a case in PACER, the U.S. "
        "Government's website for federal case data. If you wish "
        "to see the entire case, please consult PACER directly.",
    )
    if responses is None:
        increment_failure_count(rd)
        return

    if all(r.ok for r in responses):
        rd.ia_upload_failure_count = None
        rd.filepath_ia = "https://archive.org/download/%s/%s" % (
            bucket_name,
            file_name,
        )
        rd.save()
    else:
        increment_failure_count(rd)


access_key = settings.IA_ACCESS_KEY
secret_key = settings.IA_SECRET_KEY
ia_session = ia.get_session(
    {"s3": {"access": access_key, "secret": secret_key}}
)


def upload_to_ia(
    self: Task,
    identifier: str,
    files: Union[str, List[str], List[BytesIO], Dict[str, BytesIO]],
    title: str,
    collection: str,
    court_id: str,
    source_url: str,
    media_type: str,
    description: str,
) -> Optional[List[Response]]:
    """Upload an item and its files to the Internet Archive

    On the Internet Archive there are Items and files. Items have a global
    identifier, and files go inside the item:

        https://internetarchive.readthedocs.io/en/latest/items.html

    This function mirrors the IA library's similar upload function,
    but builds in retries and various assumptions that make
    sense. Note that according to emails with IA staff, it is best to
    maximize the number of files uploaded to an Item at a time, rather
    than uploading each file in a separate go.

    :param self: The celery task
    :param identifier: The global identifier within IA for the item you wish to
    work with.
    :param files: This is a weird parameter from the IA library. It can accept:
     - str: A path to the file to upload
     - list: A list of paths to files or of file objects
     - dict: A filename to file object/path mapping. It's unclear if a list of
       these can be provided as an argument!
    :param title: The title of the item in IA
    :param collection: The collection to add the item to in IA
    :param court_id: The court ID info for the item
    :param source_url: A URL link where the item can found
    :param media_type: The IA mediatype value for the item
    :param description: A description of the item

    :rtype: list or None
    :returns: List of response objects, one per file, or None if an error
    occurred.
    """
    try:
        # Before pushing files, check if the endpoint is overloaded. This is
        # lighter-weight than attempting a document upload off the bat.
        if ia_session.s3_is_overloaded(identifier, access_key):
            raise OverloadedException("S3 is currently overloaded.")
    except OverloadedException as exc:
        # Overloaded: IA wants us to slow down.
        if self.request.retries == self.max_retries:
            # Give up for now. It'll get done next time cron is run.
            return
        raise self.retry(exc=exc)
    logger.info(
        "Uploading file to Internet Archive with identifier: %s and "
        "files %s",
        identifier,
        files,
    )
    try:
        item = ia_session.get_item(identifier)
        responses = item.upload(
            files=files,
            metadata={
                "title": title,
                "collection": collection,
                "contributor": '<a href="https://free.law">Free Law Project</a>',
                "court": court_id,
                "source_url": source_url,
                "language": "eng",
                "mediatype": media_type,
                "description": description,
                "licenseurl": "https://www.usa.gov/government-works",
            },
            queue_derive=False,
            verify=True,
        )
    except ExpatError as exc:
        # ExpatError: The syntax of the XML file that's supposed to be returned
        #             by IA is bad (or something).
        if self.request.retries == self.max_retries:
            # Give up for now. It'll get done next time cron is run.
            return
        raise self.retry(exc=exc)
    except HTTPError as exc:
        if exc.response.status_code in [
            HTTP_403_FORBIDDEN,  # Can't access bucket, typically.
            HTTP_400_BAD_REQUEST,  # Corrupt PDF, typically.
        ]:
            return [exc.response]
        if self.request.retries == self.max_retries:
            # This exception is also raised when the endpoint is
            # overloaded, but doesn't get caught in the
            # OverloadedException below due to multiple processes
            # running at the same time. Just give up for now.
            return
        raise self.retry(exc=exc)
    except (requests.Timeout, requests.RequestException) as exc:
        logger.warning(
            "Timeout or unknown RequestException. Unable to upload "
            "to IA. Trying again if retries not exceeded: %s",
            identifier,
        )
        if self.request.retries == self.max_retries:
            # Give up for now. It'll get done next time cron is run.
            return
        raise self.retry(exc=exc)
    logger.info(
        "Item uploaded to IA with responses %s"
        % [r.status_code for r in responses]
    )
    return responses


@app.task
def mark_court_done_on_date(
    status: int, court_id: str, d: date
) -> Optional[int]:
    court_id = map_pacer_to_cl_id(court_id)
    try:
        doc_log = PACERFreeDocumentLog.objects.filter(
            status=PACERFreeDocumentLog.SCRAPE_IN_PROGRESS, court_id=court_id
        ).latest("date_queried")
    except PACERFreeDocumentLog.DoesNotExist:
        return
    else:
        doc_log.date_queried = d
        doc_log.status = status
        doc_log.date_completed = now()
        doc_log.save()

    return status


@app.task(ignore_result=True)
def delete_pacer_row(data: Dict[str, int], pk: int) -> List[int]:
    try:
        PACERFreeDocumentRow.objects.get(pk=pk).delete()
    except PACERFreeDocumentRow.DoesNotExist:
        pass
    return [data["rd_pk"]]


def make_fjc_idb_lookup_params(
    item: FjcIntegratedDatabase,
) -> Dict[str, Optional[str]]:
    """Given an IDB row, generate good params for looking up that item in the
    PossibleCaseNumberApi.

    :param item: The FjcIntegratedDatabase row you wish to work with.
    :returns: A dict with params you can pass to get_pacer_case_id_and_title.
    """
    params = {
        "office_number": item.office if item.office else None,
    }
    if item.plaintiff or item.defendant:
        # Note that criminal data lacks plaintiff or defendant info in IDB. We
        # could try using "United States" as the plaintiff, but in many cases
        # the plaintiff takes the form of a state. E.g. "Arizona, State of v.
        # Luenig". For a random sample, see:
        # https://www.courtlistener.com/?q=docketNumber%3Acr+AND+-case_name%3Aunited&type=r&order_by=random_123+desc.
        # ∴ not much we can do here for criminal cases
        params["case_name"] = "%s v. %s" % (item.plaintiff, item.defendant)

    if item.dataset_source in [CR_2017, CR_OLD]:
        if item.multidistrict_litigation_docket_number:
            params["docket_number_letters"] = "md"
        else:
            params["docket_number_letters"] = "cr"
    elif item.dataset_source in [CV_2017, CV_2020, CV_OLD]:
        params["docket_number_letters"] = "cv"
    return params


@app.task(
    bind=True,
    max_retries=5,
    interval_start=5 * 60,
    interval_step=10 * 60,
    ignore_results=True,
)
def get_pacer_case_id_and_title(
    self: Task,
    pass_through: Any,
    docket_number: str,
    court_id: str,
    cookies: Optional[RequestsCookieJar] = None,
    user_pk: Optional[int] = None,
    case_name: Optional[str] = None,
    office_number: Optional[str] = None,
    docket_number_letters: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Get the pacer_case_id and title values for a district court docket. Use
    heuristics to disambiguate the results.

    office_number and docket_number_letters are only needed when they are not
    already part of the docket_number passed in. Multiple parameters are needed
    here to allow flexibility when using this API. Some sources, like the IDB,
    have this data all separated out, so it helps not to try to recreate docket
    numbers from data that comes all pulled apart.

    :param self: The celery task
    :param pass_through: This data will be passed through as a key to the
    returned dict for downstream tasks to receive.
    :param docket_number: The docket number to look up. This is a flexible
    field that accepts a variety of docket number styles.
    :param court_id: The CourtListener court ID for the docket number
    :param cookies: A requests.cookies.RequestsCookieJar with the cookies of a
    logged-in PACER user.
    :param user_pk: The PK of a user making the request. This can be provided
    instead of the cookies parameter. If so, this will get the user's cookies
    from redis instead of passing them in as an argument.
    :param case_name: The case name to use for disambiguation. Disambiguation
    is done in Juriscraper using edit distance.
    :param office_number: The number (or letter) where the case took place.
    Typically, this is in the beginning of the docket number before the colon.
    This will be used for disambiguation. If you passed it as part of the
    docket number, it is not needed here.
    :param docket_number_letters: These are the letters, (cv, cr, md, etc.)
    that may appear in a docket number. This is used for disambiguation. If
    you passed these letters in the docket number, you do not need to pass
    these letters again here.
    :return: The dict formed by the PossibleCaseNumberApi lookup if a good
    value is identified, else None. The dict takes the form of:
        {
            'docket_number': force_unicode(node.xpath('./@number')[0]),
            'pacer_case_id': force_unicode(node.xpath('./@id')[0]),
            'title': force_unicode(node.xpath('./@title')[0]),
            'pass_through': pass_through,
        }
    """
    logger.info(
        "Getting pacer_case_id for docket_number %s in court %s",
        docket_number,
        court_id,
    )
    if not cookies:
        # Get cookies from Redis if not provided
        cookies = get_pacer_cookie_from_cache(user_pk)
    s = PacerSession(cookies=cookies)
    report = PossibleCaseNumberApi(map_cl_to_pacer_id(court_id), s)
    msg = None
    try:
        report.query(docket_number)
    except (RequestException, ReadTimeoutError, PacerLoginException) as exc:
        if isinstance(exc, (RequestException, ReadTimeoutError)):
            msg = (
                "Network error while running possible case number query on: "
                "%s.%s"
            )
        elif isinstance(exc, PacerLoginException):
            msg = (
                "PacerLoginException while running possible case number query "
                "on: %s.%s"
            )

        if self.request.retries == self.max_retries:
            logger.warning(msg, court_id, docket_number)
            self.request.chain = None
            return None
        logger.info(msg + " Retrying.", court_id, docket_number)
        raise self.retry(exc=exc)

    try:
        result = report.data(
            case_name=case_name,
            office_number=office_number,
            docket_number_letters=docket_number_letters,
        )
        if result is not None:
            result["pass_through"] = pass_through
        return result
    except ParsingException:
        return None


@app.task(
    bind=True,
    max_retries=5,
    interval_start=5 * 60,
    interval_step=10 * 60,
    ignore_result=True,
)
def do_case_query_by_pacer_case_id(
    self: Task,
    data: Dict[str, str],
    court_id: str,
    cookies: RequestsCookieJar,
    tag_names: List[str] = None,
) -> Optional[Dict[str, Union[str, int]]]:
    """Run a case query (iquery.pl) query on a case and save the data

    :param self: The celery task
    :param data: A dict containing at least the following: {
        'pacer_case_id': The internal pacer case ID for the item.
    }
    :param court_id: A courtlistener court ID
    :param cookies: A requests.cookies.RequestsCookieJar with the cookies of a
    logged-in PACER user.
    :param tag_names: A list of tag names to associate with the docket when
    saving it in the DB.
    :return: A dict with the pacer_case_id and docket_pk values.
    """
    s = PacerSession(cookies=cookies)
    if data is None:
        logger.info("Empty data argument. Terminating chains and exiting.")
        self.request.chain = None
        return

    pacer_case_id = data.get("pacer_case_id")
    report = CaseQuery(map_cl_to_pacer_id(court_id), s)
    logger.info("Querying docket report %s.%s" % (court_id, pacer_case_id))
    try:
        d = Docket.objects.get(pacer_case_id=pacer_case_id, court_id=court_id)
    except Docket.DoesNotExist:
        d = None
    except Docket.MultipleObjectsReturned:
        d = None

    report.query(pacer_case_id)
    docket_data = report.data
    logger.info(
        "Querying and parsing complete for %s.%s" % (court_id, pacer_case_id)
    )

    if not docket_data:
        logger.info("No valid docket data for %s.%s", court_id, pacer_case_id)
        self.request.chain = None
        return

    # Merge the contents into CL.
    if d is None:
        d = find_docket_object(
            court_id, pacer_case_id, docket_data["docket_number"]
        )

    d.add_recap_source()
    update_docket_metadata(d, docket_data)
    d.save()

    add_tags_to_objs(tag_names, [d])

    # Add the HTML to the docket in case we need it someday.
    pacer_file = PacerHtmlFiles(
        content_object=d, upload_type=UPLOAD_TYPE.CASE_REPORT_PAGE
    )
    pacer_file.filepath.save(
        "case_report.html",  # We only care about the ext w/UUIDFileSystemStorage
        ContentFile(report.response.text),
    )

    logger.info("Created/updated docket: %s" % d)
    return {
        "pacer_case_id": pacer_case_id,
        "docket_pk": d.pk,
    }


@app.task(bind=True, ignore_result=True)
def filter_docket_by_tags(
    self: Task,
    data: Optional[Dict[Any, Any]],
    tags: Optional[List[str]],
    court_id: str,
) -> Optional[Dict[Any, Any]]:
    """Stop the chain if the docket that'll be updated is already tagged.

    This is useful for if you're running a bulk download a second time and want
    to avoid downloading items you already purchased in the previous run.

    :param self: The celery task
    :param data: The data from the previous task in the chain
    :param tags: A list of tag names.
    :param court_id: The CL court ID for the item.
    :return: None if a tagged docket is found, else passes through the data
    parameter.
    """
    if data is None:
        logger.info("Empty data argument. Terminating chains and exiting.")
        self.request.chain = None
        return

    ds = Docket.objects.filter(
        pacer_case_id=data["pacer_case_id"],
        court_id=court_id,
        tags__name__in=tags,
    ).distinct()

    count = ds.count()
    if count > 0:
        logger.info(
            "Found %s dockets that were already tagged for "
            "pacer_case_id '%s', court_id '%s'. Aborting chain",
            count,
            data["pacer_case_id"],
            court_id,
        )
        self.request.chain = None
        return None
    return data


# Retry 10 times. First one after 1m, then again every 5 minutes.
@app.task(
    bind=True,
    max_retries=10,
    interval_start=1 * 60,
    interval_step=5 * 60,
    ignore_result=True,
)
@throttle_task("2/s", key="court_id", jitter=(5, 10))
def make_docket_by_iquery(
    self,
    court_id: str,
    pacer_case_id: int,
    using: str = "default",
    tag_names: Optional[List[str]] = None,
) -> Optional[int]:
    """
    Using the iquery endpoint, create or update a docket

    :param self: The celery task
    :param court_id: A CL court ID where we'll look things up
    :param pacer_case_id: The pacer_case_id to use to look up the case
    :param using: The database to use for the docket lookup
    :param tag_names: A list of strings that should be added to the docket as
    tags
    :return: None if failed, else the ID of the created/updated docket
    """
    cookies = get_or_cache_pacer_cookies(
        "pacer_scraper",
        settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    s = PacerSession(
        cookies=cookies,
        username=settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    report = CaseQuery(map_cl_to_pacer_id(court_id), s)
    try:
        report.query(pacer_case_id)
    except (requests.Timeout, requests.RequestException) as exc:
        logger.warning(
            "Timeout or unknown RequestException on iquery crawl. "
            "Trying again if retries not exceeded."
        )
        if self.request.retries == self.max_retries:
            return
        raise self.retry(exc=exc)

    if not report.data:
        logger.info(
            "No valid data found in iquery page for %s.%s",
            court_id,
            pacer_case_id,
        )
        return

    d = find_docket_object(
        court_id,
        str(pacer_case_id),
        report.data["docket_number"],
        using=using,
    )

    d.pacer_case_id = pacer_case_id
    d.add_recap_source()
    return save_iquery_to_docket(
        self,
        report.data,
        d,
        tag_names,
        add_to_solr=True,
    )


# Retry 10 times. First one after 1m, then again every 5 minutes.
@app.task(
    bind=True,
    max_retries=10,
    interval_start=1 * 60,
    interval_step=5 * 60,
    ignore_result=True,
)
def get_docket_by_pacer_case_id(
    self: Task,
    data: Dict[str, Union[str, int]],
    court_id: str,
    cookies: Optional[RequestsCookieJar] = None,
    docket_pk: Optional[int] = None,
    tag_names: Optional[str] = None,
    **kwargs,
) -> Optional[Dict[str, Union[int, bool]]]:
    """Get a docket by PACER case id, CL court ID, and a collection of kwargs
    that can be passed to the DocketReport query.

    For details of acceptable parameters, see DocketReport.query()

    :param self: The celery task
    :param data: A dict containing:
        Required: 'pacer_case_id': The internal case ID of the item in PACER.
        Optional: 'docket_pk': The ID of the docket to work on to avoid lookups
                  if it's known in advance.
    :param court_id: A courtlistener court ID.
    :param cookies: A requests.cookies.RequestsCookieJar with the cookies of a
    logged-in PACER user.
    :param docket_pk: The PK of the docket to update. Can also be provided in
    the data param, above.
    :param tag_names: A list of tag names that should be stored with the item
    in the DB.
    :param kwargs: A variety of keyword args to pass to DocketReport.query().
    :return: A dict indicating if we need to update Solr.
    """
    if data is None:
        logger.info("Empty data argument. Terminating chains and exiting.")
        self.request.chain = None
        return

    # Attempt a light docket look up, we'll do better after fetching more data
    pacer_case_id = data.get("pacer_case_id")
    docket_pk = docket_pk or data.get("docket_pk")
    if docket_pk:
        d = Docket.objects.get(pk=docket_pk)
    else:
        try:
            d = Docket.objects.get(
                pacer_case_id=pacer_case_id, court_id=court_id
            )
        except Docket.DoesNotExist:
            d = None
        except Docket.MultipleObjectsReturned:
            d = None

    if d is not None:
        first_missing_date = get_first_missing_de_date(d)
        kwargs.setdefault("date_start", first_missing_date)

    logging_id = "%s.%s" % (court_id, pacer_case_id)
    logger.info("Querying docket report %s", logging_id)
    s = PacerSession(cookies=cookies)
    report = DocketReport(map_cl_to_pacer_id(court_id), s)
    try:
        report.query(pacer_case_id, **kwargs)
    except (RequestException, ReadTimeoutError) as exc:
        msg = "Network error getting docket: %s"
        if self.request.retries == self.max_retries:
            logger.error(msg + " Aborting chain.", logging_id)
            self.request.chain = None
            return None
        logger.info(msg + " Retrying.", logging_id)
        raise self.retry(exc)
    docket_data = report.data
    logger.info("Querying and parsing complete for %s", logging_id)

    if not docket_data:
        logger.info("No valid docket data for %s", logging_id)
        self.request.chain = None
        return

    if d is None:
        d = find_docket_object(
            court_id, pacer_case_id, docket_data["docket_number"]
        )

    rds_created, content_updated = merge_pacer_docket_into_cl_docket(
        d,
        pacer_case_id,
        docket_data,
        report,
        appellate=False,
        tag_names=tag_names,
    )
    return {
        "docket_pk": d.pk,
        "content_updated": bool(rds_created or content_updated),
    }


@app.task(
    bind=True,
    max_retries=2,
    interval_start=5 * 60,
    interval_step=10 * 60,
    ignore_result=True,
)
def get_appellate_docket_by_docket_number(
    self: Task,
    docket_number: str,
    court_id: str,
    cookies: RequestsCookieJar,
    tag_names: Optional[List[str]] = None,
    **kwargs,
) -> Optional[Dict[str, Union[int, bool]]]:
    """Get a docket by docket number, CL court ID, and a collection of kwargs
    that can be passed to the DocketReport query.

    For details of acceptable parameters, see DocketReport.query()

    :param self: The celery task
    :param docket_number: The docket number of the case.
    :param court_id: A courtlistener/PACER appellate court ID.
    :param cookies: A requests.cookies.RequestsCookieJar with the cookies of a
    logged-in PACER user.
    :param tag_names: The tag name that should be stored with the item in the
    DB, if desired.
    :param kwargs: A variety of keyword args to pass to DocketReport.query().
    """
    s = PacerSession(cookies=cookies)
    report = AppellateDocketReport(court_id, s)
    logging_id = "%s - %s" % (court_id, docket_number)
    logger.info("Querying docket report %s", logging_id)

    try:
        report.query(docket_number, **kwargs)
    except requests.RequestException as e:
        logger.warning("Problem getting docket %s", logging_id)
        if self.request.retries == self.max_retries:
            self.request.chain = None
            return None
        raise self.retry(exc=e)

    docket_data = report.data
    logger.info("Querying and parsing complete for %s", logging_id)

    if docket_data == {}:
        logger.info("Unable to find docket: %s", logging_id)
        self.request.chain = None
        return None

    try:
        d = Docket.objects.get(docket_number=docket_number, court_id=court_id)
    except Docket.DoesNotExist:
        d = None
    except Docket.MultipleObjectsReturned:
        d = None

    if d is None:
        d = find_docket_object(court_id, docket_number, docket_number)

    rds_created, content_updated = merge_pacer_docket_into_cl_docket(
        d,
        docket_number,
        docket_data,
        report,
        appellate=True,
        tag_names=tag_names,
    )
    return {
        "docket_pk": d.pk,
        "content_updated": bool(rds_created or content_updated),
    }


@app.task(
    bind=True,
    max_retries=5,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
def get_attachment_page_by_rd(
    self: Task,
    rd_pk: int,
    cookies: RequestsCookieJar,
) -> Optional[AttachmentPage]:
    """Get the attachment page for the item in PACER.

    :param self: The celery task
    :param rd_pk: The PK of a RECAPDocument object to use as a source.
    :param cookies: A requests.cookies.RequestsCookieJar with the cookies of a
    logged-on PACER user.
    :return: The attachment report populated with the results
    """
    rd = RECAPDocument.objects.get(pk=rd_pk)
    if not rd.pacer_doc_id:
        # Some docket entries are just text/don't have a pacer_doc_id.
        self.request.chain = None
        return

    s = PacerSession(cookies=cookies)
    pacer_court_id = map_cl_to_pacer_id(rd.docket_entry.docket.court_id)
    att_report = AttachmentPage(pacer_court_id, s)
    try:
        att_report.query(rd.pacer_doc_id)
    except HTTPError as exc:
        if exc.response.status_code in [
            HTTP_500_INTERNAL_SERVER_ERROR,
            HTTP_504_GATEWAY_TIMEOUT,
        ]:
            logger.warning(
                "Ran into HTTPError: %s. Retrying.", exc.response.status_code
            )
            raise self.retry(exc)
        else:
            msg = "Ran into unknown HTTPError. %s. Aborting."
            logger.error(msg, exc.response.status_code)
            self.request.chain = None
            return
    except requests.RequestException as exc:
        logger.warning("Unable to get attachment page for %s", rd)
        raise self.retry(exc=exc)
    return att_report


# Retry 10 times. First one after 1m, then again every 5 minutes.
@app.task(
    bind=True,
    max_retries=10,
    interval_start=1 * 60,
    interval_step=5 * 60,
    ignore_result=True,
)
def get_bankr_claims_registry(
    self: Task,
    data: Optional[Dict[str, int]],
    cookies: RequestsCookieJar,
    tag_names: Optional[List[str]] = None,
) -> Optional[Dict[str, int]]:
    """Get the bankruptcy claims registry for a docket

    :param self: The celery task
    :param data: A dict of data containing, primarily, a key to 'docket_pk' for
    the docket for which we want to get the registry. Other keys will be
    ignored.
    :param cookies: A requests.cookies.RequestsCookieJar with the cookies of a
    logged-in PACER user.
    :param tag_names: A list of tag names that should be stored with the claims
    registry information in the DB.
    """
    s = PacerSession(cookies=cookies)
    if data is None or data.get("docket_pk") is None:
        logger.warning(
            "Empty data argument or parameter. Terminating chains "
            "and exiting."
        )
        self.request.chain = None
        return

    d = Docket.objects.get(pk=data["docket_pk"])
    logging_id = "docket %s with pacer_case_id %s" % (d.pk, d.pacer_case_id)
    logger.info("Querying claims information for %s", logging_id)
    report = ClaimsRegister(map_cl_to_pacer_id(d.court_id), s)
    try:
        report.query(d.pacer_case_id, d.docket_number)
    except (RequestException, ReadTimeoutError) as exc:
        if self.request.retries == self.max_retries:
            self.request.chain = None
            logger.error(
                "Max retries completed for %s. Unable to get claims data. "
                "Aborting task, but allowing next task to run.",
                logging_id,
            )
            return data
        logger.info(
            "Ran into networking error while getting claims report for %s. "
            "Retrying.",
            logging_id,
        )
        raise self.retry(exc)
    claims_data = report.data
    logger.info("Querying and parsing complete for %s", logging_id)

    # Save the HTML
    pacer_file = PacerHtmlFiles(
        content_object=d, upload_type=UPLOAD_TYPE.CLAIMS_REGISTER
    )
    pacer_file.filepath.save(
        "random.html",  # We only care about the ext w/UUIDFileSystemStorage
        ContentFile(report.response.text),
    )

    if not claims_data:
        logger.info("No valid claims data for %s", logging_id)
        return data

    # Merge the contents into CL
    add_bankruptcy_data_to_docket(d, claims_data)
    add_claims_to_docket(d, claims_data["claims"], tag_names)
    logger.info("Created/updated claims data for %s", logging_id)
    return data


@app.task(
    bind=True,
    max_retries=15,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
def make_attachment_pq_object(
    self: Task,
    attachment_report: AttachmentPage,
    rd_pk: int,
    user_pk: int,
) -> int:
    """Create an item in the processing queue for an attachment page.

    This is a helper shim to convert attachment page results into processing
    queue objects that can be processed by our standard pipeline.

    :param self: The celery task
    :param attachment_report: An AttachmentPage object that's already queried
    a page and populated its data attribute.
    :param rd_pk: The RECAP document that the attachment page is associated
    with
    :param user_pk: The user to associate with the ProcessingQueue object when
    it's created.
    :return: The pk of the ProcessingQueue object that's created.
    """
    rd = RECAPDocument.objects.get(pk=rd_pk)
    user = User.objects.get(pk=user_pk)
    pq = ProcessingQueue(
        court_id=rd.docket_entry.docket.court_id,
        uploader=user,
        upload_type=UPLOAD_TYPE.ATTACHMENT_PAGE,
        pacer_case_id=rd.docket_entry.docket.pacer_case_id,
    )
    pq.filepath_local.save(
        "attachment_page.html", ContentFile(attachment_report.response.text)
    )

    return pq.pk


@app.task(
    bind=True,
    max_retries=15,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
def download_pacer_pdf_by_rd(
    self: Task,
    rd_pk: int,
    pacer_case_id: str,
    pacer_doc_id: int,
    cookies: RequestsCookieJar,
) -> Optional[FreeOpinionReport]:
    """Using a RECAPDocument object ID, download the PDF if it doesn't already
    exist.

    :param self: The celery task
    :param rd_pk: The PK of the RECAPDocument to download
    :param pacer_case_id: The internal PACER case ID number
    :param pacer_doc_id: The internal PACER document ID to download
    :param cookies: A requests.cookies.RequestsCookieJar with the cookies of a
    logged-in PACER user.
    :return: requests.Response object usually containing a PDF, or None if that
    wasn't possible.
    """
    rd = RECAPDocument.objects.get(pk=rd_pk)
    pacer_court_id = map_cl_to_pacer_id(rd.docket_entry.docket.court_id)
    s = PacerSession(cookies=cookies)
    report = FreeOpinionReport(pacer_court_id, s)
    try:
        r = report.download_pdf(pacer_case_id, pacer_doc_id)
    except HTTPError as exc:
        if exc.response.status_code in [
            HTTP_500_INTERNAL_SERVER_ERROR,
            HTTP_504_GATEWAY_TIMEOUT,
        ]:
            msg = "Ran into HTTPError while getting PDF: %s."
            if self.request.retries == self.max_retries:
                logger.error(msg, exc.response.status_code)
                self.request.chain = None
                return
            logger.info(msg + " Retrying.", exc.response.status_code)
            raise self.retry(exc)
        else:
            logger.error(
                "Ran into unknown HTTPError while getting PDF: %s. "
                "Aborting.",
                exc.response.status_code,
            )
            self.request.chain = None
            return
    except requests.RequestException as exc:
        logger.warning(
            "Unable to get PDF for %s in %s", pacer_doc_id, pacer_case_id
        )
        if self.request.retries == self.max_retries:
            self.request.chain = None
            return
        raise self.retry(exc=exc)
    return r


def update_rd_metadata(
    self: Task,
    rd_pk: int,
    response: Optional[Response],
    court_id: str,
    pacer_case_id: str,
    pacer_doc_id: str,
    document_number: str,
    attachment_number: int,
) -> Tuple[bool, str]:
    """After querying PACER and downloading a document, save it to the DB.

    :param self: The celery task
    :param rd_pk: The primary key of the RECAPDocument to work on
    :param response: A requests.Response object containing the PDF data.
    :param court_id: A CourtListener court ID to use for file names.
    :param pacer_case_id: The pacer_case_id to use in error logs.
    :param pacer_doc_id: The pacer_doc_id to use in error logs.
    :param document_number: The docket entry number for use in file names.
    :param attachment_number: The attachment number (if applicable) for use in
    file names.
    :return: A two-tuple of a boolean indicating success and a corresponding
    error/success message string.
    """
    rd = RECAPDocument.objects.get(pk=rd_pk)
    if response is None:
        msg = (
            "Unable to get PDF for RECAP Document '%s' "
            "at '%s' with doc id '%s'" % (rd_pk, court_id, pacer_doc_id)
        )
        logger.error(msg)
        self.request.chain = None
        return False, msg

    file_name = get_document_filename(
        court_id, pacer_case_id, document_number, attachment_number
    )
    cf = ContentFile(response.content)
    rd.filepath_local.save(file_name, cf, save=False)
    rd.file_size = rd.filepath_local.size
    rd.is_available = True  # We've got the PDF.
    rd.date_upload = rd.date_upload or now()

    # request.content is sometimes a str, sometimes unicode, so
    # force it all to be bytes, pleasing hashlib.
    rd.sha1 = sha1(force_bytes(response.content))
    with NamedTemporaryFile(
        prefix="rd_for_page_size_",
        suffix=".pdf",
        buffering=0,
    ) as tmp:
        tmp.write(rd.filepath_local.read())
        rd.page_count = get_page_count(tmp.name, "pdf")

    # Save and extract, skipping OCR.
    rd.save()

    # Make sure we mark the docket as needing upload
    mark_ia_upload_needed(rd.docket_entry.docket, save_docket=True)
    return True, "Saved item successfully"


def add_tags(rd: RECAPDocument, tag_name: str) -> None:
    """Add tags to a tree of objects starting with the RECAPDocument

    Adds the tag to the RECAPDocument, Docket Entry, and Docket.

    :param rd: The RECAPDocument where we begin the chain
    :param tag_name: The name of the tag to add
    :return None
    """
    if tag_name is not None:
        tag, _ = Tag.objects.get_or_create(name=tag_name)
        tag.tag_object(rd.docket_entry.docket)
        tag.tag_object(rd.docket_entry)
        tag.tag_object(rd)


@app.task(
    bind=True,
    max_retries=3,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
@transaction.atomic
def get_pacer_doc_by_rd(
    self: Task,
    rd_pk: int,
    cookies: RequestsCookieJar,
    tag: Optional[str] = None,
) -> Optional[int]:
    """A simple method for getting the PDF associated with a RECAPDocument.

    :param self: The bound celery task
    :param rd_pk: The PK for the RECAPDocument object
    :param cookies: The cookies of a logged in PACER session
    :param tag: The name of a tag to apply to any modified items
    :return: The RECAPDocument PK
    """
    rd = RECAPDocument.objects.get(pk=rd_pk)

    if rd.is_available:
        add_tags(rd, tag)
        self.request.chain = None
        return

    pacer_case_id = rd.docket_entry.docket.pacer_case_id
    r = download_pacer_pdf_by_rd(
        rd.pk, pacer_case_id, rd.pacer_doc_id, cookies
    )
    court_id = rd.docket_entry.docket.court_id
    success, msg = update_rd_metadata(
        self,
        rd_pk,
        r,
        court_id,
        pacer_case_id,
        rd.pacer_doc_id,
        rd.document_number,
        rd.attachment_number,
    )

    if success is False:
        self.request.chain = None
        return

    add_tags(rd, tag)
    return rd.pk


@app.task(
    bind=True,
    max_retries=15,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
def get_pacer_doc_by_rd_and_description(
    self: Task,
    rd_pk: int,
    description_re: re.Pattern,
    cookies: RequestsCookieJar,
    fallback_to_main_doc: bool = False,
    tag: Optional[List[str]] = None,
) -> None:
    """Using a RECAPDocument object ID and a description of a document, get the
    document from PACER.

    This function was originally meant to get civil cover sheets, but can be
    repurposed as needed.

    :param self: The celery task
    :param rd_pk: The PK of a RECAPDocument object to use as a source.
    :param description_re: A compiled regular expression to search against the
    description provided by the attachment page.
    :param cookies: A requests.cookies.RequestsCookieJar with the cookies of a
    logged-in PACER user.
    :param fallback_to_main_doc: Should we grab the main doc if none of the
    attachments match the regex?
    :param tag: A tag name to apply to any downloaded content.
    :return: None
    """
    rd = RECAPDocument.objects.get(pk=rd_pk)
    att_report = get_attachment_page_by_rd(self, rd_pk, cookies)

    att_found = None
    for attachment in att_report.data.get("attachments", []):
        if description_re.search(attachment["description"]):
            att_found = attachment.copy()
            document_type = RECAPDocument.ATTACHMENT
            break

    if not att_found:
        if fallback_to_main_doc:
            logger.info(
                "Falling back to main document for pacer_doc_id: %s"
                % rd.pacer_doc_id
            )
            att_found = att_report.data
            document_type = RECAPDocument.PACER_DOCUMENT
        else:
            msg = "Aborting. Did not find civil cover sheet for %s." % rd
            logger.error(msg)
            self.request.chain = None
            return

    if not att_found.get("pacer_doc_id"):
        logger.warning("No pacer_doc_id for document (is it sealed?)")
        self.request.chain = None
        return

    # Try to find the attachment already in the collection
    rd, _ = RECAPDocument.objects.get_or_create(
        docket_entry=rd.docket_entry,
        attachment_number=att_found.get("attachment_number"),
        document_number=rd.document_number,
        pacer_doc_id=att_found["pacer_doc_id"],
        document_type=document_type,
        defaults={"date_upload": now()},
    )
    # Replace the description if we have description data.
    # Else fallback on old.
    rd.description = att_found.get("description", "") or rd.description
    if tag is not None:
        tag, _ = Tag.objects.get_or_create(name=tag)
        tag.tag_object(rd)

    if rd.is_available:
        # Great. Call it a day.
        rd.save()
        return

    pacer_case_id = rd.docket_entry.docket.pacer_case_id
    r = download_pacer_pdf_by_rd(
        rd.pk, pacer_case_id, att_found["pacer_doc_id"], cookies
    )
    court_id = rd.docket_entry.docket.court_id
    success, msg = update_rd_metadata(
        self,
        rd_pk,
        r,
        court_id,
        pacer_case_id,
        rd.pacer_doc_id,
        rd.document_number,
        rd.attachment_number,
    )

    if success is False:
        return

    # Skip OCR for now. It'll happen in a second step.
    extract_recap_pdf(rd.pk, skip_ocr=True)
    add_items_to_solr([rd.pk], "search.RECAPDocument")


@app.task(
    bind=True,
    max_retries=15,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
def get_pacer_doc_id_with_show_case_doc_url(
    self: Task,
    rd_pk: int,
    cookies: RequestsCookieJar,
) -> None:
    """use the show_case_doc URL to get pacer_doc_id values.

    :param self: The celery task
    :param rd_pk: The pk of the RECAPDocument you want to get.
    :param cookies: A requests.cookies.RequestsCookieJar with the cookies of a
    logged-in PACER user.
    """
    rd = RECAPDocument.objects.get(pk=rd_pk)
    d = rd.docket_entry.docket
    s = PacerSession(cookies=cookies)
    pacer_court_id = map_cl_to_pacer_id(d.court_id)
    report = ShowCaseDocApi(pacer_court_id, s)
    last_try = self.request.retries == self.max_retries
    try:
        if rd.document_type == rd.ATTACHMENT:
            report.query(
                d.pacer_case_id, rd.document_number, rd.attachment_number
            )
        else:
            report.query(d.pacer_case_id, rd.document_number)
    except (RequestException, ReadTimeoutError) as exc:
        msg = "Unable to get PDF for %s"
        if last_try:
            logger.error(msg, rd)
            return
        logger.info(msg + " Retrying.", rd)
        raise self.retry(exc=exc)
    except HTTPError as exc:
        status_code = exc.response.status_code
        if status_code in [
            HTTP_500_INTERNAL_SERVER_ERROR,
            HTTP_504_GATEWAY_TIMEOUT,
        ]:
            msg = "Got HTTPError with status code %s."
            if last_try:
                logger.error(msg + " Aborting.", status_code)
                return

            logger.info(msg + " Retrying", status_code)
            raise self.retry(exc)
        else:
            msg = "Ran into unknown HTTPError. %s. Aborting."
            logger.error(msg, status_code)
            return
    try:
        pacer_doc_id = report.data
    except ParsingException:
        logger.error("Unable to get redirect for %s" % rd)
        return
    else:
        rd.pacer_doc_id = pacer_doc_id
        rd.save()
        logger.info("Successfully saved pacer_doc_id to rd %s" % rd_pk)
