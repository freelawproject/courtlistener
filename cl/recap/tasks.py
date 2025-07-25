import asyncio
import concurrent.futures
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from http import HTTPStatus
from multiprocessing import process
from typing import Any
from zipfile import ZipFile

import requests
from asgiref.sync import async_to_sync, sync_to_async
from botocore import exceptions as botocore_exception
from celery import Task
from celery.canvas import chain
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile, File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models.fields.files import FieldFile
from django.utils.timezone import now
from juriscraper.lib.exceptions import PacerLoginException, ParsingException
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize
from juriscraper.pacer import (
    ACMSAttachmentPage,
    AcmsCaseSearch,
    ACMSDocketReport,
    AppellateDocketReport,
    CaseQuery,
    ClaimsRegister,
    DocketHistoryReport,
    DocketReport,
    PossibleCaseNumberApi,
    S3NotificationEmail,
)
from juriscraper.pacer.email import DocketType
from lxml.etree import ParserError
from redis import ConnectionError as RedisConnectionError
from requests import HTTPError
from requests.packages.urllib3.exceptions import ReadTimeoutError

from cl.alerts.tasks import enqueue_docket_alert, send_alert_and_webhook
from cl.alerts.utils import (
    set_skip_percolation_if_bankruptcy_data,
    set_skip_percolation_if_parties_data,
)
from cl.api.webhooks import send_recap_fetch_webhooks
from cl.celery_init import app
from cl.corpus_importer.tasks import (
    download_pacer_pdf_by_rd,
    download_pdf_by_magic_number,
    get_att_report_by_rd,
    get_document_number_for_appellate,
    is_docket_entry_sealed,
    is_pacer_doc_sealed,
    save_attachment_pq_from_text,
    update_rd_metadata,
)
from cl.corpus_importer.utils import (
    ais_appellate_court,
    is_appellate_court,
    is_bankruptcy_court,
    is_long_appellate_document_number,
    mark_ia_upload_needed,
    should_check_acms_court,
)
from cl.custom_filters.templatetags.text_filters import oxford_join
from cl.lib.filesizes import convert_size_to_bytes
from cl.lib.microservice_utils import microservice
from cl.lib.pacer import is_pacer_court_accessible, map_cl_to_pacer_id
from cl.lib.pacer_session import (
    ProxyPacerSession,
    SessionData,
    delete_pacer_cookie_from_cache,
    get_or_cache_pacer_cookies,
    get_pacer_cookie_from_cache,
)
from cl.lib.recap_utils import get_document_filename
from cl.lib.storage import RecapEmailSESStorage
from cl.lib.string_diff import find_best_match
from cl.recap.mergers import (
    add_bankruptcy_data_to_docket,
    add_claims_to_docket,
    add_docket_entries,
    add_parties_and_attorneys,
    add_tags_to_objs,
    find_docket_object,
    get_data_from_appellate_att_report,
    get_data_from_att_report,
    merge_attachment_page_data,
    merge_pacer_docket_into_cl_docket,
    process_orphan_documents,
    update_docket_appellate_metadata,
    update_docket_metadata,
)
from cl.recap.models import (
    PROCESSING_STATUS,
    REQUEST_TYPE,
    UPLOAD_TYPE,
    EmailProcessingQueue,
    FjcIntegratedDatabase,
    PacerFetchQueue,
    PacerHtmlFiles,
    ProcessingQueue,
)
from cl.recap.utils import (
    find_subdocket_atts_rds_from_data,
    find_subdocket_pdf_rds_from_data,
    get_court_id_from_fetch_queue,
    get_main_rds,
    sort_acms_docket_entries,
)
from cl.scrapers.tasks import (
    extract_recap_pdf,
    extract_recap_pdf_base,  # noqa: F401
)
from cl.search.models import Court, Docket, DocketEntry, RECAPDocument
from cl.search.tasks import index_docket_parties_in_es

logger = logging.getLogger(__name__)
cnt = CaseNameTweaker()


async def process_recap_upload(pq: ProcessingQueue) -> None:
    """Process an item uploaded from an extension or API user.

    Uploaded objects can take a variety of forms, and we'll need to
    process them accordingly.
    """
    if pq.upload_type == UPLOAD_TYPE.DOCKET:
        docket = await process_recap_docket(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.ATTACHMENT_PAGE:
        sub_docket_att_page_pks = await find_subdocket_att_page_rds(pq.pk)
        for pq_pk in sub_docket_att_page_pks:
            await process_recap_attachment(pq_pk)
    elif pq.upload_type == UPLOAD_TYPE.PDF:
        sub_docket_pdf_pks = await find_subdocket_pdf_rds(pq.pk)
        for pq_pk in sub_docket_pdf_pks:
            await process_recap_pdf(pq_pk)
    elif pq.upload_type == UPLOAD_TYPE.DOCKET_HISTORY_REPORT:
        docket = await process_recap_docket_history_report(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.APPELLATE_DOCKET:
        docket = await process_recap_appellate_docket(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.APPELLATE_ATTACHMENT_PAGE:
        await process_recap_appellate_attachment(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.CLAIMS_REGISTER:
        await process_recap_claims_register(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.DOCUMENT_ZIP:
        await process_recap_zip(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.CASE_QUERY_PAGE:
        docket = await process_case_query_page(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.APPELLATE_CASE_QUERY_PAGE:
        await sync_to_async(process_recap_appellate_case_query_page)(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.CASE_QUERY_RESULT_PAGE:
        await sync_to_async(process_recap_case_query_result_page)(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.APPELLATE_CASE_QUERY_RESULT_PAGE:
        await sync_to_async(process_recap_appellate_case_query_result_page)(
            pq.pk
        )
    elif pq.upload_type == UPLOAD_TYPE.ACMS_ATTACHMENT_PAGE:
        await process_recap_acms_appellate_attachment(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.ACMS_DOCKET_JSON:
        docket = await process_recap_acms_docket(pq.pk)


def do_pacer_fetch(fq: PacerFetchQueue):
    """Process a request made by a user to get an item from PACER.

    :param fq: The PacerFetchQueue item to process
    :return: None
    """
    result = None
    match fq.request_type:
        case REQUEST_TYPE.DOCKET:
            court_id = get_court_id_from_fetch_queue(fq)
            c = (
                chain(fetch_appellate_docket.si(fq.pk))
                if is_appellate_court(court_id)
                else chain(fetch_docket.si(fq.pk))
            )
            c = c | mark_fq_successful.si(fq.pk)
        case REQUEST_TYPE.ATTACHMENT_PAGE:
            c = chain(
                fetch_attachment_page.si(fq.pk),
                replicate_fq_att_page_to_subdocket_rds.s(),
            )
        case REQUEST_TYPE.PDF:
            rd_pk = fq.recap_document_id
            c = chain(
                fetch_pacer_doc_by_rd.si(rd_pk, fq.pk),
                extract_recap_pdf.si(rd_pk),
                mark_fq_successful.si(fq.pk),
            )
        case _:
            raise NotImplementedError(
                f"Unsupported request_type: {fq.request_type}"
            )

    result = c.apply_async(queue=settings.CELERY_PACER_FETCH_QUEUE)
    return result


async def mark_pq_successful(pq: ProcessingQueue) -> tuple[int, str]:
    """Mark the processing queue item as successfully completed.

    :param pq: The ProcessingQueue object to manipulate
    :return: A two tuple, the PQ status, the PQ error message.
    """
    # Ditch the original file
    await sync_to_async(pq.filepath_local.delete)(save=False)
    message = "Successful upload! Nice work."
    if pq.debug:
        message = "Successful debugging upload! Nice work."
    return await mark_pq_status(pq, message, PROCESSING_STATUS.SUCCESSFUL)


async def associate_related_instances(
    pq: ProcessingQueue | EmailProcessingQueue,
    d_id: int | None = None,
    de_id: int | None = None,
    rd_id: int | list[int] | None = None,
) -> None:
    """Associate the related upload instances.

    :param pq: The ProcessingQueue or EmailProcessingQueue object to manipulate
    :param d_id: The docket PK to associate with this upload. Either the docket
    that the RECAPDocument is associated with, or the docket that was uploaded.
    :param de_id: The docket entry to associate with this upload. Only applies
    to document uploads, which are associated with docket entries.
    :param rd_id: The RECAPDocument PK to associate with this upload. Only
    applies to document uploads (obviously). If the pq is a EmailProcessingQueue
    this param accepts a list of RDs Pks.
    :return: None
    """

    if isinstance(pq, EmailProcessingQueue):
        await pq.recap_documents.aadd(*rd_id)
    else:
        pq.docket_id = d_id
        pq.docket_entry_id = de_id
        pq.recap_document_id = rd_id
        await pq.asave()


async def mark_pq_status(
    pq: ProcessingQueue,
    msg: str,
    status: int,
    message_property_name: str = "error_message",
) -> tuple[int, str]:
    """Mark the processing queue item as some process, and log the message.

    :param pq: The ProcessingQueue object to manipulate
    :param msg: The message to log and to save to pq's error_message field.
    :param status: A pq status code as defined on the ProcessingQueue model.
    :param message_property_name: The message property to attach the msg argument to.
    :return: A two tuple, the PQ status, the PQ error message.
    """
    if msg:
        logger.info(msg)
    setattr(pq, message_property_name, msg)
    pq.status = status
    await pq.asave()
    return pq.status, getattr(pq, message_property_name)


async def process_recap_pdf(pk):
    """Process an uploaded PDF from the RECAP API endpoint.

    :param pk: The PK of the processing queue item you want to work on.
    :return: A RECAPDocument object that was created or updated.
    """
    """Save a RECAP PDF to the database."""
    pq = await ProcessingQueue.objects.aget(pk=pk)
    await mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    court_id = pq.court_id
    document_type = (
        RECAPDocument.PACER_DOCUMENT
        if not pq.attachment_number  # This check includes attachment_number set to None or 0
        else RECAPDocument.ATTACHMENT
    )
    # Set attachment_number to None if it is 0
    pq.attachment_number = (
        None if not pq.attachment_number else pq.attachment_number
    )

    logger.info("Processing RECAP item (debug is: %s): %s", pq.debug, pq)
    try:
        # Attempt to get RECAPDocument instance.
        # It is possible for this instance to not have a document yet,
        # so the document_type field will have a default value,
        # which is why we do not use it to retrieve the RECAPDocument.
        if pq.pacer_case_id:
            rd = await RECAPDocument.objects.aget(
                docket_entry__docket__pacer_case_id=pq.pacer_case_id,
                pacer_doc_id=pq.pacer_doc_id,
            )
        else:
            # Sometimes we don't have the case ID from PACER. Try to make this
            # work anyway.
            rd = await RECAPDocument.objects.aget(pacer_doc_id=pq.pacer_doc_id)
    except (RECAPDocument.DoesNotExist, RECAPDocument.MultipleObjectsReturned):
        # Try again but this time using Docket and Docket Entry to get
        # the RECAPDocument instance. If not found, we create a new one.
        retries = 5
        while True:
            try:
                d = await Docket.objects.aget(
                    pacer_case_id=pq.pacer_case_id, court_id=court_id
                )
            except Docket.DoesNotExist:
                # No Docket and no RECAPDocument. Do a retry. Hopefully
                # the docket will be in place soon (it could be in a
                # different upload task that hasn't yet been processed).
                logger.warning(
                    "Unable to find docket for processing queue '%s'. "
                    "Retrying if max_retries is not exceeded.",
                    pq,
                )
                error_message = "Unable to find docket for item."
                if retries > 0:
                    retries -= 1
                    await mark_pq_status(
                        pq, error_message, PROCESSING_STATUS.QUEUED_FOR_RETRY
                    )
                    await asyncio.sleep(1)
                    continue
                await mark_pq_status(
                    pq, error_message, PROCESSING_STATUS.FAILED
                )
                return None
            except Docket.MultipleObjectsReturned:
                msg = f"Too many dockets found when trying to save '{pq}'"
                await mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
                return None
            else:
                break

        # Got the Docket, attempt to get/create the DocketEntry, and then
        # get/create the RECAPDocument
        retries = 5
        while True:
            try:
                de = await DocketEntry.objects.aget(
                    docket=d, entry_number=pq.document_number
                )
            except DocketEntry.DoesNotExist:
                logger.warning(
                    "Unable to find docket entry for processing queue '%s'.",
                    pq,
                )
                msg = "Unable to find docket entry for item."
                if retries > 0:
                    retries -= 1
                    await mark_pq_status(
                        pq, msg, PROCESSING_STATUS.QUEUED_FOR_RETRY
                    )
                    await asyncio.sleep(1)
                    continue
                await mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
                return None
            else:
                # If we're here, we've got the docket and docket
                # entry, but were unable to find the document by
                # pacer_doc_id. This happens when pacer_doc_id is
                # missing, for example. ∴, try to get the document
                # from the docket entry.
                try:
                    rd = await RECAPDocument.objects.aget(
                        docket_entry=de,
                        document_number=pq.document_number,
                        attachment_number=pq.attachment_number,
                        document_type=document_type,
                    )
                except RECAPDocument.DoesNotExist:
                    # Unable to find it. Make a new item.
                    rd = RECAPDocument(
                        docket_entry=de,
                        pacer_doc_id=pq.pacer_doc_id,
                        document_type=document_type,
                    )
                except RECAPDocument.MultipleObjectsReturned:
                    # Multiple RECAPDocuments exist for this docket entry,
                    # which is unexpected. Ideally, we should not create a new
                    # RECAPDocument when multiples exist. However, since this
                    # behavior has been in place for years, we're retaining it
                    # for now. We've added Sentry logging to capture these
                    # cases for future debugging.
                    logger.error(
                        "Multiple RECAPDocuments returned when processing pdf upload"
                    )
                    rd = RECAPDocument(
                        docket_entry=de,
                        pacer_doc_id=pq.pacer_doc_id,
                        document_type=document_type,
                    )
                break

    # document_number field is a CharField in RECAPDocument and a
    # BigIntegerField in ProcessingQueue. To prevent the ES signal
    # processor fields tracker from detecting it as a value change, it should
    # be converted to a string.
    # Avoid updating the document_number from the PQ if this upload belongs
    # to a court that doesn't use regular numbering. See issue:
    # https://github.com/freelawproject/courtlistener/issues/2877
    if not await ais_appellate_court(
        court_id
    ) or not is_long_appellate_document_number(rd.document_number):
        rd.document_number = str(pq.document_number)
    # We update attachment_number and document_type in case the
    # RECAPDocument didn't have the actual document yet.
    rd.attachment_number = pq.attachment_number
    rd.document_type = document_type

    # Do the file, finally.
    try:
        with pq.filepath_local.open("rb") as f:
            new_sha1 = hashlib.file_digest(f, "sha1").hexdigest()
    except OSError as exc:
        msg = f"Internal processing error ({exc.errno}: {exc.strerror})."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
        return None

    existing_document = all(
        [
            rd.sha1 == new_sha1,
            rd.is_available,
            rd.filepath_local,
        ]
    )
    if not existing_document:
        # Different sha1, it wasn't available, or it's missing from disk. Move
        # the new file over from the processing queue storage.
        docket_entry = await DocketEntry.objects.aget(id=rd.docket_entry_id)
        docket = await Docket.objects.aget(id=docket_entry.docket_id)
        file_name = get_document_filename(
            docket.court_id,
            docket.pacer_case_id,
            rd.document_number,
            rd.attachment_number,
        )
        if not pq.debug:
            with pq.filepath_local.open("rb") as f:
                await sync_to_async(rd.filepath_local.save)(
                    file_name, File(f), save=False
                )

            # Do page count and extraction
            response = await microservice(
                service="page-count",
                item=rd,
            )
            if response.is_success:
                rd.page_count = int(response.text)
                assert isinstance(rd.page_count, (int | type(None))), (
                    "page_count must be an int or None."
                )
            rd.file_size = rd.filepath_local.size

        rd.ocr_status = None
        rd.is_available = True
        rd.sha1 = new_sha1
        rd.date_upload = now()

    if not pq.debug:
        try:
            await rd.asave()
        except (IntegrityError, ValidationError):
            msg = "Failed to save RECAPDocument (unique_together constraint or doc type issue)"
            await mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
            rd.filepath_local.delete(save=False)
            return None

    if not existing_document and not pq.debug:
        await sync_to_async(
            chain(
                extract_recap_pdf.si(rd.pk),
            ).apply_async
        )()

    if not pq.debug:
        de = await DocketEntry.objects.aget(recap_documents=rd)
        await associate_related_instances(
            pq,
            d_id=de.docket_id,
            de_id=de.pk,
            rd_id=rd.pk,
        )
        await mark_pq_successful(pq)
        docket = await Docket.objects.aget(id=de.docket_id)
        await mark_ia_upload_needed(docket, save_docket=True)
    return rd


async def process_recap_zip(pk: int) -> dict[str, list[int] | list[Task]]:
    """Process a zip uploaded from a PACER district court

    The general process is to use our existing infrastructure. We open the zip,
    identify the documents inside, and then associate them with the rest of our
    collection.

    :param self: A celery task object
    :param pk: The PK of the ProcessingQueue object to process
    :return: A list of new PQ's that were created, one per PDF that was
    enqueued.
    """
    pq = await ProcessingQueue.objects.aget(pk=pk)
    await mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)

    logger.info("Processing RECAP zip (debug is: %s): %s", pq.debug, pq)
    with pq.filepath_local.open("rb") as zip_bytes:
        with ZipFile(zip_bytes, "r") as archive:
            # Security: Check for zip bombs.
            max_file_size = convert_size_to_bytes("200MB")
            for zip_info in archive.infolist():
                if zip_info.file_size < max_file_size:
                    continue
                await mark_pq_status(
                    pq,
                    f"Zip too large; possible zip bomb. File in zip named {zip_info.filename} "
                    f"would be {zip_info.file_size} bytes expanded.",
                    PROCESSING_STATUS.INVALID_CONTENT,
                )
                return {"new_pqs": [], "tasks": []}

            # For each document in the zip, create a new PQ
            new_pqs = []
            tasks = []
            for file_name in archive.namelist():
                file_content = archive.read(file_name)
                f = SimpleUploadedFile(file_name, file_content)

                file_name = file_name.split(".pdf")[0]
                if "-" in file_name:
                    doc_num, att_num = file_name.split("-")
                    if att_num == "main":
                        att_num = None
                else:
                    doc_num = file_name
                    att_num = None

                if att_num:
                    # An attachment, ∴ nuke the pacer_doc_id value, since it
                    # corresponds to the main doc only.
                    pacer_doc_id = ""
                else:
                    pacer_doc_id = pq.pacer_doc_id

                # Create a new PQ and enqueue it for processing
                new_pq = await ProcessingQueue.objects.acreate(
                    court_id=pq.court_id,
                    uploader_id=pq.uploader_id,
                    pacer_case_id=pq.pacer_case_id,
                    pacer_doc_id=pacer_doc_id,
                    document_number=doc_num,
                    attachment_number=att_num,
                    filepath_local=f,
                    status=PROCESSING_STATUS.ENQUEUED,
                    upload_type=UPLOAD_TYPE.PDF,
                    debug=pq.debug,
                )
                new_pqs.append(new_pq.pk)
                await process_recap_pdf(new_pq.pk)

            # At the end, mark the pq as successful and return the PQ
            await mark_pq_status(
                pq,
                f"Successfully created ProcessingQueue objects: {oxford_join(new_pqs)}",
                PROCESSING_STATUS.SUCCESSFUL,
            )

            # Returning the tasks allows tests to wait() for the PDFs to complete
            # before checking assertions.
            return {
                "new_pqs": new_pqs,
                "tasks": tasks,
            }


def parse_docket_text(court_id, text):
    report = DocketReport(court_id)
    report._parse_text(text)
    return report.data


async def process_recap_docket(pk):
    """Process an uploaded docket from the RECAP API endpoint.

    :param pk: The primary key of the processing queue item you want to work
    on.
    :returns: A dict of the form:

        {
            // The PK of the docket that's created or updated
            'docket_pk': 22,
            // A boolean indicating whether a new docket entry or
            // recap document was created
            'content_updated': True,
        }

    This value is a dict so that it can be ingested in a Celery chain.

    """
    start_time = now()
    pq = await ProcessingQueue.objects.aget(pk=pk)
    await mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s", pq.debug, pq)

    try:
        text = pq.filepath_local.read().decode()
    except OSError as exc:
        msg = f"Internal processing error ({exc.errno}: {exc.strerror})."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
        return None

    try:
        if process.current_process().daemon:
            data = parse_docket_text(map_cl_to_pacer_id(pq.court_id), text)
        else:
            with concurrent.futures.ProcessPoolExecutor() as pool:
                data = await asyncio.get_running_loop().run_in_executor(
                    pool,
                    parse_docket_text,
                    map_cl_to_pacer_id(pq.court_id),
                    text,
                )
    except Exception as e:
        logging.exception(e)
        await mark_pq_status(
            pq,
            f"We encountered a parsing error while processing this item: {e}",
            PROCESSING_STATUS.FAILED,
        )
        return None
    logger.info("Parsing completed of item %s", pq)

    if data == {}:
        # Not really a docket. Some sort of invalid document (see Juriscraper).
        msg = "Not a valid docket upload."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        return None

    # Merge the contents of the docket into CL.
    d = await find_docket_object(
        pq.court_id,
        pq.pacer_case_id,
        data["docket_number"],
        data.get("federal_defendant_number"),
        data.get("federal_dn_judge_initials_assigned"),
        data.get("federal_dn_judge_initials_referred"),
    )

    d.add_recap_source()
    await update_docket_metadata(d, data)
    if not d.pacer_case_id:
        d.pacer_case_id = pq.pacer_case_id

    if pq.debug:
        await associate_related_instances(pq, d_id=d.pk)
        await mark_pq_successful(pq)
        return {"docket_pk": d.pk, "content_updated": False}

    # Skip the percolator request for this save if parties data will be merged
    # afterward.
    set_skip_percolation_if_parties_data(data["parties"], d)
    await d.asave()

    # Add the HTML to the docket in case we need it someday.
    pacer_file = await PacerHtmlFiles.objects.acreate(
        content_object=d, upload_type=UPLOAD_TYPE.DOCKET
    )
    await sync_to_async(pacer_file.filepath.save)(
        "docket.html",  # We only care about the ext w/S3PrivateUUIDStorageTest
        ContentFile(text.encode()),
    )

    # Merge parties before adding docket entries, so they can access parties'
    # data when the RECAPDocuments are percolated.
    await sync_to_async(add_parties_and_attorneys)(d, data["parties"])
    if data["parties"]:
        # Index or re-index parties only if the docket has parties.
        await sync_to_async(index_docket_parties_in_es.delay)(d.pk)

    items_returned, rds_created, content_updated = await add_docket_entries(
        d, data["docket_entries"]
    )
    await process_orphan_documents(rds_created, pq.court_id, d.date_filed)
    if content_updated:
        newly_enqueued = enqueue_docket_alert(d.pk)
        if newly_enqueued:
            await sync_to_async(send_alert_and_webhook.delay)(d.pk, start_time)
    await associate_related_instances(pq, d_id=d.pk)
    await mark_pq_successful(pq)
    return {
        "docket_pk": d.pk,
        "content_updated": bool(rds_created or content_updated),
    }


async def get_att_data_from_pq(
    pq: ProcessingQueue,
) -> tuple[ProcessingQueue, dict, str | None]:
    """Extract attachment data from a ProcessingQueue object.

    :param pq: The ProcessingQueue object.
    :return: A tuple containing the updated pq, att_data, and text.
    """
    try:
        with pq.filepath_local.open("rb") as file:
            text = file.read().decode("utf-8")
    except OSError as exc:
        msg = f"Internal processing error ({exc.errno}: {exc.strerror})."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
        return pq, {}, None

    att_data = get_data_from_att_report(text, pq.court_id)
    if not att_data:
        msg = "Not a valid attachment page upload."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        return pq, {}, None

    if pq.pacer_case_id in ["undefined", "null"]:
        pq.pacer_case_id = att_data.get("pacer_case_id")
        await pq.asave()

    return pq, att_data, text


async def find_subdocket_att_page_rds(
    pk: int,
) -> list[int]:
    """Look for RECAP Documents that belong to subdockets, and create a PQ
    object for each additional attachment page that requires processing.

    :param pk: Primary key of the processing queue item.
    :return: A list of ProcessingQueue pks to process.
    """

    pq = await ProcessingQueue.objects.aget(pk=pk)
    pq, att_data, text = await get_att_data_from_pq(pq)
    if not att_data:
        # Bad attachment page.
        return []

    pacer_doc_id = att_data["pacer_doc_id"]
    main_rds = get_main_rds(pq.court_id, pacer_doc_id).exclude(
        docket_entry__docket__pacer_case_id=pq.pacer_case_id
    )
    pqs_to_process_pks = [
        pq.pk
    ]  # Add the original pq to the list of pqs to process
    original_file_content = text.encode("utf-8")
    original_file_name = pq.filepath_local.name

    pqs_to_create = []
    async for main_rd in main_rds:
        main_pacer_case_id = main_rd.docket_entry.docket.pacer_case_id
        # Create additional pqs for each subdocket case found.
        pqs_to_create.append(
            ProcessingQueue(
                uploader_id=pq.uploader_id,
                pacer_doc_id=pacer_doc_id,
                pacer_case_id=main_pacer_case_id,
                court_id=pq.court_id,
                upload_type=UPLOAD_TYPE.ATTACHMENT_PAGE,
                filepath_local=ContentFile(
                    original_file_content, name=original_file_name
                ),
            )
        )

    if pqs_to_create:
        pqs_created = await ProcessingQueue.objects.abulk_create(pqs_to_create)
        pqs_to_process_pks.extend([pq.pk for pq in pqs_created])

    return pqs_to_process_pks


async def find_subdocket_pdf_rds(
    pk: int,
) -> list[int]:
    """Look for RECAP Documents that belong to subdockets, and create a PQ
    object for each additional PDF upload that requires processing.

    :param pk: Primary key of the processing queue item.
    :return: A list of ProcessingQueue pks to process.
    """

    pq = await ProcessingQueue.objects.aget(pk=pk)
    main_rds = get_main_rds(pq.court_id, pq.pacer_doc_id).exclude(
        is_available=True
    )
    pqs_to_process_pks = [
        pq.pk
    ]  # Add the original pq to the list of pqs to process

    if await ais_appellate_court(pq.court_id):
        # Abort the process for appellate documents. Subdockets cannot be found
        # in appellate cases.
        return pqs_to_process_pks

    if pq.pacer_case_id:
        # If pq already has a pacer_case_id, exclude it from the queryset.
        main_rds = main_rds.exclude(
            docket_entry__docket__pacer_case_id=pq.pacer_case_id
        )

    pdf_binary_content = pq.filepath_local.read()

    pqs_to_create = []
    main_rds = [rd async for rd in main_rds]
    for i, main_rd in enumerate(main_rds):
        if i == 0 and not pq.pacer_case_id:
            # If the original PQ does not have a pacer_case_id,
            # assign it a pacer_case_id from one of the matched RDs
            # to ensure the RD lookup in process_recap_pdf succeeds.
            pq.pacer_case_id = main_rd.docket_entry.docket.pacer_case_id
            await pq.asave()
            continue

        main_pacer_case_id = main_rd.docket_entry.docket.pacer_case_id
        # Create additional pqs for each subdocket case found.
        pqs_to_create.append(
            ProcessingQueue(
                uploader_id=pq.uploader_id,
                pacer_doc_id=pq.pacer_doc_id,
                pacer_case_id=main_pacer_case_id,
                document_number=pq.document_number,
                attachment_number=pq.attachment_number,
                court_id=pq.court_id,
                upload_type=UPLOAD_TYPE.PDF,
                filepath_local=ContentFile(
                    pdf_binary_content, name=pq.filepath_local.name
                ),
            )
        )

    if pqs_to_create:
        pqs_created = await ProcessingQueue.objects.abulk_create(pqs_to_create)
        pqs_to_process_pks.extend([pq.pk for pq in pqs_created])

    return pqs_to_process_pks


async def process_recap_attachment(
    pk: int,
    tag_names: list[str] | None = None,
    document_number: int | None = None,
) -> tuple[int, str, list[RECAPDocument]]:
    """Process an uploaded attachment page from the RECAP API endpoint.

    :param pk: The primary key of the processing queue item you want to work on
    :param tag_names: A list of tag names to add to all items created or
    modified in this function.
    :param document_number: The main RECAP document number. If provided use it
    to merge the attachments instead of using the one from the attachment page.
    :return: Tuple indicating the status of the processing and a related
    message
    """

    pq = await ProcessingQueue.objects.aget(pk=pk)
    await mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s", pq.debug, pq)

    pq, att_data, text = await get_att_data_from_pq(pq)
    if not att_data:
        # Bad attachment page.
        return pq.status, pq.error_message, []

    if document_number is None:
        document_number = att_data["document_number"]
    try:
        court = await Court.objects.aget(id=pq.court_id)
        rds_affected, de = await merge_attachment_page_data(
            court,
            pq.pacer_case_id,
            att_data["pacer_doc_id"],
            document_number,
            text,
            att_data["attachments"],
            pq.debug,
        )
    except RECAPDocument.MultipleObjectsReturned:
        msg = (
            "Too many documents found when attempting to associate "
            "attachment data"
        )
        pq_status, msg = await mark_pq_status(
            pq, msg, PROCESSING_STATUS.FAILED
        )
        return pq_status, msg, []
    except RECAPDocument.DoesNotExist:
        msg = "Could not find docket to associate with attachment metadata"
        pq_status, msg = await mark_pq_status(
            pq, msg, PROCESSING_STATUS.FAILED
        )
        return pq_status, msg, []

    await add_tags_to_objs(tag_names, rds_affected)
    await associate_related_instances(pq, d_id=de.docket_id, de_id=de.pk)
    pq_status, msg = await mark_pq_successful(pq)

    return pq_status, msg, rds_affected


def parse_claims_register_text(court_id, text):
    report = ClaimsRegister(court_id)
    report._parse_text(text)
    return report.data


async def process_recap_claims_register(pk):
    """Merge bankruptcy claims registry HTML into RECAP

    :param pk: The primary key of the processing queue item you want to work on
    :type pk: int
    :return: None
    :rtype: None
    """
    pq = await ProcessingQueue.objects.aget(pk=pk)
    if pq.debug:
        # Proper debugging not supported on this endpoint. Just abort.
        await mark_pq_successful(pq)
        return None

    await mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s", pq.debug, pq)

    try:
        text = pq.filepath_local.read().decode()
    except OSError as exc:
        msg = f"Internal processing error ({exc.errno}: {exc.strerror})."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
        return None

    try:
        if process.current_process().daemon:
            data = parse_claims_register_text(
                map_cl_to_pacer_id(pq.court_id), text
            )
        else:
            with concurrent.futures.ProcessPoolExecutor() as pool:
                data = await asyncio.get_running_loop().run_in_executor(
                    pool,
                    parse_claims_register_text,
                    map_cl_to_pacer_id(pq.court_id),
                    text,
                )
    except Exception as e:
        logging.exception(e)
        await mark_pq_status(
            pq,
            f"We encountered a parsing error while processing this item: {e}",
            PROCESSING_STATUS.FAILED,
        )
        return None
    logger.info("Parsing completed for item %s", pq)

    if not data:
        # Bad HTML
        msg = "Not a valid claims registry page or other parsing failure"
        await mark_pq_status(pq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        return None

    # Merge the contents of the docket into CL.
    d = await find_docket_object(
        pq.court_id,
        pq.pacer_case_id,
        data["docket_number"],
        data.get("federal_defendant_number"),
        data.get("federal_dn_judge_initials_assigned"),
        data.get("federal_dn_judge_initials_referred"),
    )

    # Merge the contents into CL
    d.add_recap_source()
    await update_docket_metadata(d, data)

    # Skip the percolator request for this save if bankruptcy data will
    # be merged afterward.
    set_skip_percolation_if_bankruptcy_data(data, d)

    retries = 5
    while True:
        try:
            await d.asave()
        except IntegrityError:
            logger.warning(
                "Race condition experienced while attempting docket save."
            )
            error_message = "Unable to save docket due to IntegrityError."
            if retries > 0:
                retries -= 1
                await mark_pq_status(
                    pq, error_message, PROCESSING_STATUS.QUEUED_FOR_RETRY
                )
                await asyncio.sleep(1)
                continue
            await mark_pq_status(pq, error_message, PROCESSING_STATUS.FAILED)
            return None
        else:
            break

    await sync_to_async(add_bankruptcy_data_to_docket)(d, data)
    await sync_to_async(add_claims_to_docket)(d, data["claims"])
    logger.info("Created/updated claims data for %s", pq)

    # Add the HTML to the docket in case we need it someday.
    pacer_file = await PacerHtmlFiles.objects.acreate(
        content_object=d, upload_type=UPLOAD_TYPE.CLAIMS_REGISTER
    )
    await sync_to_async(pacer_file.filepath.save)(
        # We only care about the ext w/S3PrivateUUIDStorageTest
        "claims_registry.html",
        ContentFile(text.encode()),
    )
    await associate_related_instances(pq, d_id=d.pk)
    await mark_pq_successful(pq)
    return {"docket_pk": d.pk}


def parse_docket_history_text(court_id, text):
    report = DocketHistoryReport(court_id)
    report._parse_text(text)
    return report.data


async def process_recap_docket_history_report(pk):
    """Process the docket history report.

    :param pk: The primary key of the processing queue item you want to work on
    :returns: A dict indicating whether the docket needs re-indexing.
    """
    start_time = now()
    pq = await ProcessingQueue.objects.aget(pk=pk)
    await mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s", pq.debug, pq)

    try:
        text = pq.filepath_local.read().decode()
    except OSError as exc:
        msg = f"Internal processing error ({exc.errno}: {exc.strerror})."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
        return None

    try:
        if process.current_process().daemon:
            data = parse_docket_history_text(
                map_cl_to_pacer_id(pq.court_id), text
            )
        else:
            with concurrent.futures.ProcessPoolExecutor() as pool:
                data = await asyncio.get_running_loop().run_in_executor(
                    pool,
                    parse_docket_history_text,
                    map_cl_to_pacer_id(pq.court_id),
                    text,
                )
    except Exception as e:
        logging.exception(e)
        await mark_pq_status(
            pq,
            f"We encountered a parsing error while processing this item: {e}",
            PROCESSING_STATUS.FAILED,
        )
        return None
    logger.info("Parsing completed for item %s", pq)

    if data == {}:
        # Bad docket history page.
        msg = "Not a valid docket history page upload."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        return None

    # Merge the contents of the docket into CL.
    d = await find_docket_object(
        pq.court_id,
        pq.pacer_case_id,
        data["docket_number"],
        data.get("federal_defendant_number"),
        data.get("federal_dn_judge_initials_assigned"),
        data.get("federal_dn_judge_initials_referred"),
    )

    d.add_recap_source()
    await update_docket_metadata(d, data)

    if pq.debug:
        await associate_related_instances(pq, d_id=d.pk)
        await mark_pq_successful(pq)
        return {"docket_pk": d.pk, "content_updated": False}

    retries = 5
    while True:
        try:
            await d.asave()
        except IntegrityError:
            logger.warning(
                "Race condition experienced while attempting docket save."
            )
            error_message = "Unable to save docket due to IntegrityError."
            if retries > 0:
                retries -= 1
                await mark_pq_status(
                    pq, error_message, PROCESSING_STATUS.QUEUED_FOR_RETRY
                )
                await asyncio.sleep(1)
                continue
            await mark_pq_status(pq, error_message, PROCESSING_STATUS.FAILED)
            return None
        else:
            break

    # Add the HTML to the docket in case we need it someday.
    pacer_file = await PacerHtmlFiles.objects.acreate(
        content_object=d, upload_type=UPLOAD_TYPE.DOCKET_HISTORY_REPORT
    )
    await sync_to_async(pacer_file.filepath.save)(
        # We only care about the ext w/S3PrivateUUIDStorageTest
        "docket_history.html",
        ContentFile(text.encode()),
    )

    items_returned, rds_created, content_updated = await add_docket_entries(
        d, data["docket_entries"]
    )
    await process_orphan_documents(rds_created, pq.court_id, d.date_filed)
    if content_updated:
        newly_enqueued = enqueue_docket_alert(d.pk)
        if newly_enqueued:
            await sync_to_async(send_alert_and_webhook.delay)(d.pk, start_time)
    await associate_related_instances(pq, d_id=d.pk)
    await mark_pq_successful(pq)
    return {
        "docket_pk": d.pk,
        "content_updated": bool(rds_created or content_updated),
    }


def parse_case_query_page_text(court_id, text):
    report = CaseQuery(court_id)
    report._parse_text(text)
    return report.data


async def process_case_query_page(pk):
    """Process the case query (iquery.pl) page.

    :param pk: The primary key of the processing queue item you want to work on
    :returns: A dict indicating whether the docket needs re-indexing.
    """

    pq = await ProcessingQueue.objects.aget(pk=pk)
    await mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s", pq.debug, pq)

    try:
        text = pq.filepath_local.read().decode()
    except OSError as exc:
        msg = f"Internal processing error ({exc.errno}: {exc.strerror})."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
        return None

    try:
        if process.current_process().daemon:
            data = parse_case_query_page_text(
                map_cl_to_pacer_id(pq.court_id), text
            )
        else:
            with concurrent.futures.ProcessPoolExecutor() as pool:
                data = await asyncio.get_running_loop().run_in_executor(
                    pool,
                    parse_case_query_page_text,
                    map_cl_to_pacer_id(pq.court_id),
                    text,
                )
    except Exception as e:
        logging.exception(e)
        await mark_pq_status(
            pq,
            f"We encountered a parsing error while processing this item: {e}",
            PROCESSING_STATUS.FAILED,
        )
        return None
    logger.info("Parsing completed for item %s", pq)

    if data == {}:
        # Bad docket iquery page.
        msg = "Not a valid case query page upload."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        return None

    # Merge the contents of the docket into CL.
    d = await find_docket_object(
        pq.court_id,
        pq.pacer_case_id,
        data["docket_number"],
        data.get("federal_defendant_number"),
        data.get("federal_dn_judge_initials_assigned"),
        data.get("federal_dn_judge_initials_referred"),
    )
    current_case_name = d.case_name
    d.add_recap_source()
    await update_docket_metadata(d, data)

    # Update the docket if the case name has changed and contains
    # docket entries
    content_updated = False
    if current_case_name != d.case_name and d.pk:
        if await d.docket_entries.aexists():
            content_updated = True

    if pq.debug:
        await associate_related_instances(pq, d_id=d.pk)
        await mark_pq_successful(pq)
        return {"docket_pk": d.pk, "content_updated": False}

    # Skip the percolator request for this save if bankruptcy data will
    # be merged afterward.
    set_skip_percolation_if_bankruptcy_data(data, d)

    retries = 5
    while True:
        try:
            await d.asave()
            await sync_to_async(add_bankruptcy_data_to_docket)(d, data)
        except IntegrityError:
            logger.warning(
                "Race condition experienced while attempting docket save."
            )
            error_message = "Unable to save docket due to IntegrityError."
            if retries > 0:
                retries -= 1
                await mark_pq_status(
                    pq, error_message, PROCESSING_STATUS.QUEUED_FOR_RETRY
                )
                await asyncio.sleep(1)
                continue
            await mark_pq_status(pq, error_message, PROCESSING_STATUS.FAILED)
            return None
        else:
            break

    # Add the HTML to the docket in case we need it someday.
    pacer_file = await PacerHtmlFiles.objects.acreate(
        content_object=d, upload_type=UPLOAD_TYPE.CASE_QUERY_PAGE
    )
    await sync_to_async(pacer_file.filepath.save)(
        # We only care about the ext w/S3PrivateUUIDStorageTest
        "case_report.html",
        ContentFile(text.encode()),
    )
    await associate_related_instances(pq, d_id=d.pk)
    await mark_pq_successful(pq)
    return {
        "docket_pk": d.pk,
        "content_updated": content_updated,
    }


def parse_appellate_text(court_id, text):
    report = AppellateDocketReport(court_id)
    report._parse_text(text)
    return report.data


def parse_acms_attachment_json(court_id, json):
    report = ACMSAttachmentPage(court_id)
    report._parse_text(json)
    return report.data


def parse_acms_json(court_id, json):
    report = ACMSDocketReport(court_id)
    report._parse_text(json)
    return report.data


async def process_recap_appellate_docket(pk):
    """Process an uploaded appellate docket from the RECAP API endpoint.

    :param pk: The primary key of the processing queue item you want to work
    on.
    :returns: A dict of the form:

        {
            // The PK of the docket that's created or updated
            'docket_pk': 22,
            // A boolean indicating whether a new docket entry or
            // recap document was created
            'content_updated': True,
        }

    This value is a dict so that it can be ingested in a Celery chain.
    """
    start_time = now()
    pq = await ProcessingQueue.objects.aget(pk=pk)
    await mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info(
        "Processing Appellate RECAP item (debug is: %s): %s", pq.debug, pq
    )

    try:
        text = pq.filepath_local.read().decode()
    except OSError as exc:
        msg = f"Internal processing error ({exc.errno}: {exc.strerror})."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
        return None

    try:
        if process.current_process().daemon:
            data = parse_appellate_text(map_cl_to_pacer_id(pq.court_id), text)
        else:
            with concurrent.futures.ProcessPoolExecutor() as pool:
                data = await asyncio.get_running_loop().run_in_executor(
                    pool,
                    parse_appellate_text,
                    map_cl_to_pacer_id(pq.court_id),
                    text,
                )
    except Exception as e:
        logging.exception(e)
        await mark_pq_status(
            pq,
            f"We encountered a parsing error while processing this item: {e}",
            PROCESSING_STATUS.FAILED,
        )
        return None
    logger.info("Parsing completed of item %s", pq)

    if data == {}:
        # Not really a docket. Some sort of invalid document (see Juriscraper).
        msg = "Not a valid docket upload."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        return None

    # Merge the contents of the docket into CL.
    d = await find_docket_object(
        pq.court_id,
        pq.pacer_case_id,
        data["docket_number"],
        data.get("federal_defendant_number"),
        data.get("federal_dn_judge_initials_assigned"),
        data.get("federal_dn_judge_initials_referred"),
    )

    d.add_recap_source()
    await update_docket_metadata(d, data)
    d, og_info = await update_docket_appellate_metadata(d, data)
    if not d.pacer_case_id:
        d.pacer_case_id = pq.pacer_case_id

    if pq.debug:
        await associate_related_instances(pq, d_id=d.pk)
        await mark_pq_successful(pq)
        return {"docket_pk": d.pk, "content_updated": False}

    if og_info is not None:
        await og_info.asave()
        d.originating_court_information = og_info

    # Skip the percolator request for this save if parties data will be merged
    # afterward.
    set_skip_percolation_if_parties_data(data["parties"], d)
    await d.asave()

    # Add the HTML to the docket in case we need it someday.
    pacer_file = await PacerHtmlFiles.objects.acreate(
        content_object=d, upload_type=UPLOAD_TYPE.APPELLATE_DOCKET
    )
    await sync_to_async(pacer_file.filepath.save)(
        "docket.html",  # We only care about the ext w/S3PrivateUUIDStorageTest
        ContentFile(text.encode()),
    )

    # Merge parties before adding docket entries, so they can access parties'
    # data when the RECAPDocuments are percolated.
    await sync_to_async(add_parties_and_attorneys)(d, data["parties"])
    if data["parties"]:
        # Index or re-index parties only if the docket has parties.
        await sync_to_async(index_docket_parties_in_es.delay)(d.pk)

    items_returned, rds_created, content_updated = await add_docket_entries(
        d, data["docket_entries"]
    )
    await process_orphan_documents(rds_created, pq.court_id, d.date_filed)
    if content_updated:
        newly_enqueued = enqueue_docket_alert(d.pk)
        if newly_enqueued:
            await sync_to_async(send_alert_and_webhook.delay)(d.pk, start_time)
    await associate_related_instances(pq, d_id=d.pk)
    await mark_pq_successful(pq)
    return {
        "docket_pk": d.pk,
        "content_updated": bool(rds_created or content_updated),
    }


async def process_recap_acms_docket(pk):
    """Process uploaded ACMS appellate docket JSON from the RECAP API endpoint.

    :param pk: The primary key of the processing queue item you want to work
    on.
    :returns: A dict of the form:

        {
            // The PK of the docket that's created or updated
            'docket_pk': 22,
            // A boolean indicating whether a new docket entry or
            // recap document was created.
            'content_updated': True,
        }

    This value is a dict so that it can be ingested in a Celery chain.

    """
    start_time = now()
    pq = await ProcessingQueue.objects.aget(pk=pk)
    await mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info("Processing ACMS RECAP item (debug is: %s): %s", pq.debug, pq)

    try:
        text = pq.filepath_local.read().decode()
    except OSError as exc:
        msg = f"Internal processing error ({exc.errno}: {exc.strerror})."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
        return None

    try:
        if process.current_process().daemon:
            data = parse_acms_json(map_cl_to_pacer_id(pq.court_id), text)
        else:
            with concurrent.futures.ProcessPoolExecutor() as pool:
                data = await asyncio.get_running_loop().run_in_executor(
                    pool,
                    parse_acms_json,
                    map_cl_to_pacer_id(pq.court_id),
                    text,
                )
    except Exception as e:
        logging.exception(e)
        await mark_pq_status(
            pq,
            f"We encountered a parsing error while processing this item: {e}",
            PROCESSING_STATUS.FAILED,
        )
        return None
    logger.info("Parsing completed of item %s", pq)

    if data == {}:
        # Not really a docket. Some sort of invalid document (see Juriscraper).
        msg = "Not a valid docket upload."
        await mark_pq_status(pq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        return None

    # Merge the contents of the docket into CL.
    d = await find_docket_object(
        pq.court_id,
        pq.pacer_case_id,
        data["docket_number"],
        data.get("federal_defendant_number"),
        data.get("federal_dn_judge_initials_assigned"),
        data.get("federal_dn_judge_initials_referred"),
    )

    d.add_recap_source()
    await update_docket_metadata(d, data)
    d, og_info = await update_docket_appellate_metadata(d, data)
    if not d.pacer_case_id:
        d.pacer_case_id = pq.pacer_case_id

    if pq.debug:
        await associate_related_instances(pq, d_id=d.pk)
        await mark_pq_successful(pq)
        return {"docket_pk": d.pk, "content_updated": False}

    if og_info is not None:
        await og_info.asave()
        d.originating_court_information = og_info

    # Skip the percolator request for this save if parties data will be merged
    # afterward.
    set_skip_percolation_if_parties_data(data["parties"], d)
    await d.asave()

    pacer_file = await PacerHtmlFiles.objects.acreate(
        content_object=d, upload_type=UPLOAD_TYPE.ACMS_DOCKET_JSON
    )
    await sync_to_async(pacer_file.filepath.save)(
        "docket.json",  # We only care about the ext w/S3PrivateUUIDStorageTest
        ContentFile(text.encode()),
    )

    # Merge parties before adding docket entries, so they can access parties'
    # data when the RECAPDocuments are percolated.
    await sync_to_async(add_parties_and_attorneys)(d, data["parties"])

    # Sort docket entries to ensure consistent ordering
    data["docket_entries"] = sort_acms_docket_entries(data["docket_entries"])
    des_returned, rds_created, content_updated = await add_docket_entries(
        d, data["docket_entries"]
    )
    await process_orphan_documents(rds_created, pq.court_id, d.date_filed)
    if content_updated:
        newly_enqueued = enqueue_docket_alert(d.pk)
        if newly_enqueued:
            await sync_to_async(send_alert_and_webhook.delay)(d.pk, start_time)
    await associate_related_instances(pq, d_id=d.pk)
    await mark_pq_successful(pq)
    return {
        "docket_pk": d.pk,
        "content_updated": bool(rds_created or content_updated),
    }


async def process_recap_acms_appellate_attachment(
    pk: int,
) -> tuple[int, str, list[RECAPDocument]] | None:
    """Process an uploaded appellate attachment page.
    :param pk: The primary key of the processing queue item you want to work on
    :return: Tuple indicating the status of the processing, a related
    message and the recap documents affected.
    """
    pq = await ProcessingQueue.objects.aget(pk=pk)
    await mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s", pq.debug, pq)

    try:
        text = pq.filepath_local.read().decode()
    except OSError as exc:
        msg = f"Internal processing error ({exc.errno}: {exc.strerror})."
        pq_status, msg = await mark_pq_status(
            pq, msg, PROCESSING_STATUS.FAILED
        )
        return pq_status, msg, []

    try:
        if process.current_process().daemon:
            # yyy
            data = parse_acms_attachment_json(
                map_cl_to_pacer_id(pq.court_id), text
            )
        else:
            with concurrent.futures.ProcessPoolExecutor() as pool:
                data = await asyncio.get_running_loop().run_in_executor(
                    pool,
                    parse_acms_attachment_json,
                    map_cl_to_pacer_id(pq.court_id),
                    text,
                )
    except Exception as e:
        logging.exception(e)
        await mark_pq_status(
            pq,
            f"We encountered a parsing error while processing this item: {e}",
            PROCESSING_STATUS.FAILED,
        )
        return None
    logger.info("Parsing completed of item %s", pq)

    if data == {}:
        # Not really a docket. Some sort of invalid document (see Juriscraper).
        msg = "Not a valid acms appellate attachment page upload."
        await mark_pq_status(pq, text, PROCESSING_STATUS.INVALID_CONTENT)
        return None

    if pq.pacer_case_id in ["undefined", "null"]:
        # Bad data from the client. Fix it with parsed data.
        pq.pacer_case_id = data.get("pacer_case_id")
        await pq.asave()

    try:
        court = await Court.objects.aget(id=pq.court_id)
        rds_affected, de = await merge_attachment_page_data(
            court,
            pq.pacer_case_id,
            data["pacer_doc_id"],
            data["entry_number"],
            text,
            data["attachments"],
            pq.debug,
            True,
        )
    except RECAPDocument.MultipleObjectsReturned:
        msg = (
            "Too many documents found when attempting to associate "
            "attachment data"
        )
        pq_status, msg = await mark_pq_status(
            pq, msg, PROCESSING_STATUS.FAILED
        )
        return pq_status, msg, []
    except RECAPDocument.DoesNotExist as exc:
        msg = "Could not find docket to associate with attachment metadata"
        pq_status, msg = await mark_pq_status(
            pq, msg, PROCESSING_STATUS.FAILED
        )
        return pq_status, msg, []

    await associate_related_instances(pq, d_id=de.docket_id, de_id=de.pk)
    pq_status, msg = await mark_pq_successful(pq)
    return pq_status, msg, rds_affected


async def process_recap_appellate_attachment(
    pk: int,
) -> tuple[int, str, list[RECAPDocument]] | None:
    """Process an uploaded appellate attachment page.

    :param self: The Celery task
    :param pk: The primary key of the processing queue item you want to work on
    :return: Tuple indicating the status of the processing, a related
    message and the recap documents affected.
    """

    pq = await ProcessingQueue.objects.aget(pk=pk)
    await mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s", pq.debug, pq)

    try:
        text = pq.filepath_local.read().decode()
    except OSError as exc:
        msg = f"Internal processing error ({exc.errno}: {exc.strerror})."
        pq_status, msg = await mark_pq_status(
            pq, msg, PROCESSING_STATUS.FAILED
        )
        return pq_status, msg, []

    att_data = get_data_from_appellate_att_report(text, pq.court_id)
    logger.info("Parsing completed for item %s", pq)

    if att_data == {}:
        # Bad attachment page.
        msg = "Not a valid appellate attachment page upload."
        pq_status, msg = await mark_pq_status(
            pq, msg, PROCESSING_STATUS.INVALID_CONTENT
        )
        return pq_status, msg, []

    if pq.pacer_case_id in ["undefined", "null"]:
        # Bad data from the client. Fix it with parsed data.
        pq.pacer_case_id = att_data.get("pacer_case_id")
        await pq.asave()

    try:
        court = await Court.objects.aget(id=pq.court_id)
        rds_affected, de = await merge_attachment_page_data(
            court,
            pq.pacer_case_id,
            att_data["pacer_doc_id"],
            None,  # Appellate attachments don't contain a document_number
            text,
            att_data["attachments"],
            pq.debug,
        )
    except RECAPDocument.MultipleObjectsReturned:
        msg = (
            "Too many documents found when attempting to associate "
            "attachment data"
        )
        pq_status, msg = await mark_pq_status(
            pq, msg, PROCESSING_STATUS.FAILED
        )
        return pq_status, msg, []
    except RECAPDocument.DoesNotExist:
        msg = "Could not find docket to associate with attachment metadata"
        pq_status, msg = await mark_pq_status(
            pq, msg, PROCESSING_STATUS.FAILED
        )
        return pq_status, msg, []

    await associate_related_instances(pq, d_id=de.docket_id, de_id=de.pk)
    pq_status, msg = await mark_pq_successful(pq)
    return pq_status, msg, rds_affected


@app.task(bind=True)
def process_recap_appellate_case_query_page(self, pk):
    """Process the appellate case query pages.

    For now, this is a stub until we can get the parser working properly in
    Juriscraper.
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    msg = "Appellate case query pages not yet supported. Coming soon."
    async_to_sync(mark_pq_status)(pq, msg, PROCESSING_STATUS.FAILED)
    return None


@app.task(bind=True)
def process_recap_case_query_result_page(self, pk):
    """Process case query result pages.

    For now, this is a stub until we can get the parser working properly in
    Juriscraper.
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    msg = "Case query result pages not yet supported. Coming soon."
    async_to_sync(mark_pq_status)(pq, msg, PROCESSING_STATUS.FAILED)
    return None


@app.task(bind=True)
def process_recap_appellate_case_query_result_page(self, pk):
    """Process case query result pages.

    For now, this is a stub until we can get the parser working properly in
    Juriscraper.
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    msg = "Appellate case query result pages not yet supported. Coming soon."
    async_to_sync(mark_pq_status)(pq, msg, PROCESSING_STATUS.FAILED)
    return None


@app.task
def create_new_docket_from_idb(idb_row):
    """Create a new docket for the IDB item found. Populate it with all
    applicable fields.

    :param idb_row: An FjcIntegratedDatabase object with which to create a
    Docket.
    :return Docket: The created Docket object.
    """
    case_name = f"{idb_row.plaintiff} v. {idb_row.defendant}"
    d = Docket(
        source=Docket.IDB,
        court=idb_row.district,
        idb_data=idb_row,
        date_filed=idb_row.date_filed,
        date_terminated=idb_row.date_terminated,
        case_name=case_name,
        case_name_short=cnt.make_case_name_short(case_name),
        docket_number_core=idb_row.docket_number,
        nature_of_suit=idb_row.get_nature_of_suit_display(),
        jurisdiction_type=idb_row.get_jurisdiction_display() or "",
    )
    try:
        d.save()
    except IntegrityError:
        # Happens when the IDB row is already associated with a docket. Remove
        # the other association and try again.
        Docket.objects.filter(idb_data=idb_row).update(
            date_modified=now(), idb_data=None
        )
        d.save()

    logger.info("Created docket %s for IDB row: %s", d.pk, idb_row)
    return d.pk


@app.task
def merge_docket_with_idb(d, idb_row):
    """Merge an existing docket with an idb_row.

    :param d: A Docket object pk to update.
    :param idb_row: A FjcIntegratedDatabase object to use as a source for
    updates.
    :return None
    """
    d.add_idb_source()
    d.idb_data = idb_row
    d.date_filed = d.date_filed or idb_row.date_filed
    d.date_terminated = d.date_terminated or idb_row.date_terminated
    d.nature_of_suit = d.nature_of_suit or idb_row.get_nature_of_suit_display()
    d.jurisdiction_type = (
        d.jurisdiction_type or idb_row.get_jurisdiction_display()
    )
    try:
        d.save()
    except IntegrityError:
        # Happens when the IDB row is already associated with a docket. Remove
        # the other association and try again.
        Docket.objects.filter(idb_data=idb_row).update(
            date_modified=now(), idb_data=None
        )
        d.save()


def do_heuristic_match(idb_row, ds):
    """Use cosine similarity of case names from the IDB to try to find a match
    out of several possibilities in the DB.

    :param idb_row: The FJC IDB row to match against
    :param ds: A list of Dockets that might match
    :returns: The best-matching Docket in ds if possible, else None
    """
    case_names = []
    for d in ds:
        case_name = harmonize(d.case_name)
        parts = case_name.lower().split(" v. ")
        if len(parts) == 1:
            case_names.append(case_name)
        elif len(parts) == 2:
            plaintiff, defendant = parts[0], parts[1]
            case_names.append(f"{plaintiff[0:30]} v. {defendant[0:30]}")
        elif len(parts) > 2:
            case_names.append(case_name)
    idb_case_name = harmonize(f"{idb_row.plaintiff} v. {idb_row.defendant}")
    results = find_best_match(case_names, idb_case_name, case_sensitive=False)
    if results["ratio"] > 0.65:
        logger.info(
            "Found good match by case name for %s: %s",
            idb_case_name,
            results["match_str"],
        )
        d = ds[results["match_index"]]
    else:
        logger.info(
            "No good match after office and case name filtering. Creating "
            "new item: %s",
            idb_row,
        )
        d = None
    return d


@app.task
def create_or_merge_from_idb_chunk(idb_chunk):
    """Take a chunk of IDB rows and either merge them into the Docket table or
    create new items for them in the docket table.

    :param idb_chunk: A list of FjcIntegratedDatabase PKs
    :type idb_chunk: list
    :return: None
    :rtype: None
    """
    for idb_pk in idb_chunk:
        idb_row = FjcIntegratedDatabase.objects.get(pk=idb_pk)
        ds = (
            Docket.objects.filter(
                docket_number_core=idb_row.docket_number,
                court=idb_row.district,
            )
            .exclude(docket_number__icontains="cr")
            .exclude(case_name__icontains="sealed")
            .exclude(case_name__icontains="suppressed")
            .exclude(case_name__icontains="search warrant")
        )
        count = ds.count()
        if count == 0:
            msg = "Creating new docket for IDB row: %s"
            logger.info(msg, idb_row)
            create_new_docket_from_idb(idb_row)
            continue
        elif count == 1:
            d = ds[0]
            msg = "Merging Docket %s with IDB row: %s"
            logger.info(msg, d, idb_row)
            merge_docket_with_idb(d, idb_row)
            continue

        msg = "Unable to merge. Got %s dockets for row: %s"
        logger.info(msg, count, idb_row)

        d = do_heuristic_match(idb_row, ds)
        if d is not None:
            merge_docket_with_idb(d, idb_row)
        else:
            create_new_docket_from_idb(idb_row)


@app.task
def update_docket_from_hidden_api(data):
    """Update the docket based on the result of a lookup in the hidden API.

    :param data: A dict as returned by get_pacer_case_id_and_title
    or None if looking up the item failed.
    :return None
    """
    if data is None:
        return None

    d = Docket.objects.get(pk=data["pass_through"])
    d.docket_number = data["docket_number"]
    d.pacer_case_id = data["pacer_case_id"]
    try:
        d.save()
    except IntegrityError:
        # This is a difficult spot. The IDB data has cases that are not in
        # PACER. For example, in IDB there are two rows for 6:92-cv-657 in
        # oked, but in PACER, there is just one. In IDB the two rows *are*
        # distinct, with different filing dates, for example. So what happens
        # is, we try to find the docket for the first one, get none, and start
        # creating it. Meanwhile, via a race condition, we try to get the
        # second one, fail, and then start creating *it*. The first finishes,
        # then the second tries to lookup the pacer_case_id. Unfortunately, b/c
        # there's only one item in PACER for the docket number looked up, that
        # is returned, and we get an integrity error since we can't have the
        # same pacer_case_id, docket_number pair in a single court. Solution?
        # Delete the second one, which was created via race condition, and
        # shouldn't have existed anyway.
        d.delete()


def fetch_pacer_doc_by_rd_base(
    self,
    rd_pk: int,
    fq_pk: int,
    magic_number: str | None = None,
    omit_page_count: bool = False,
) -> int | None:
    """Fetch a PACER PDF by rd_pk

    This is very similar to get_pacer_doc_by_rd, except that it manages
    status as it proceeds and it gets the cookie info from redis.

    :param self: The celery task.
    :param rd_pk: The PK of the RECAP Document to get.
    :param fq_pk: The PK of the RECAP Fetch Queue to update.
    :param magic_number: The magic number to fetch PACER documents for free
    this is an optional field, only used by RECAP Email documents
    :param omit_page_count: If true, omit requesting the page_count from doctor
    :return: The RECAPDocument PK
    """

    rd = RECAPDocument.objects.get(pk=rd_pk)
    fq = PacerFetchQueue.objects.get(pk=fq_pk)
    pacer_doc_id = rd.pacer_doc_id
    # Check court connectivity, if fails retry the task, hopefully, it'll be
    # retried in a different not blocked node
    if not is_pacer_court_accessible(rd.docket_entry.docket.court_id):
        if self.request.retries == self.max_retries:
            msg = f"Blocked by court: {rd.docket_entry.docket.court_id}"
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return None
        raise self.retry()

    mark_fq_status(fq, "", PROCESSING_STATUS.IN_PROGRESS)
    if rd.is_available:
        msg = "PDF already marked as 'is_available'. Doing nothing."
        mark_fq_status(fq, msg, PROCESSING_STATUS.SUCCESSFUL)
        self.request.chain = None
        return

    if not pacer_doc_id:
        msg = (
            "Missing 'pacer_doc_id' attribute. Without this attribute we "
            "cannot identify the document properly. Missing pacer_doc_id "
            "attributes usually indicate that the item may not have a "
            "document associated with it, or it may need to be updated via "
            "the docket report to acquire a pacer_doc_id. Aborting request."
        )
        mark_fq_status(fq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        self.request.chain = None
        return

    if rd.is_acms_document():
        msg = "ACMS documents are not currently supported"
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        return

    session_data = get_pacer_cookie_from_cache(fq.user_id)
    if not session_data:
        msg = "Unable to find cached cookies. Aborting request."
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        self.request.chain = None
        return

    pacer_case_id = rd.docket_entry.docket.pacer_case_id
    de_seq_num = rd.docket_entry.pacer_sequence_number
    try:
        r, r_msg = download_pacer_pdf_by_rd(
            rd.pk,
            pacer_case_id,
            pacer_doc_id,
            session_data,
            magic_number,
            de_seq_num=de_seq_num,
        )
    except (requests.RequestException, HTTPError):
        msg = "Failed to get PDF from network."
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        self.request.chain = None
        return
    except PacerLoginException as exc:
        msg = f"PacerLoginException while getting document for rd: {rd.pk}."
        if self.request.retries == self.max_retries:
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            delete_pacer_cookie_from_cache(fq.user_id)
            self.request.chain = None
            return None
        mark_fq_status(
            fq, f"{msg} Retrying.", PROCESSING_STATUS.QUEUED_FOR_RETRY
        )
        raise self.retry(exc=exc)

    court_id = rd.docket_entry.docket.court_id

    pdf_bytes = None
    if r:
        pdf_bytes = r.content
    success, msg = update_rd_metadata(
        self,
        rd_pk,
        pdf_bytes,
        r_msg,
        court_id,
        pacer_case_id,
        pacer_doc_id,
        rd.document_number,
        rd.attachment_number,
        omit_page_count=omit_page_count,
    )

    if success is False:
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        self.request.chain = None
        return

    # Logic to replicate the PDF sub-dockets matched by RECAPDocument
    subdocket_pqs_to_replicate = []
    if not is_appellate_court(court_id):
        subdocket_pqs_to_replicate = find_subdocket_pdf_rds_from_data(
            fq.user_id, court_id, pacer_doc_id, [pacer_case_id], pdf_bytes
        )
    if subdocket_pqs_to_replicate:
        # Wait for the transaction to be committed before triggering the task,
        # ensuring that all PQs already exist.
        transaction.on_commit(
            partial(
                replicate_fq_pdf_to_subdocket_rds.delay,
                subdocket_pqs_to_replicate,
            )
        )
    return rd.pk


@app.task(
    bind=True,
    autoretry_for=(RedisConnectionError, PacerLoginException),
    max_retries=5,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
@transaction.atomic
def fetch_pacer_doc_by_rd(
    self, rd_pk: int, fq_pk: int, magic_number: str | None = None
) -> int | None:
    """Celery task wrapper for fetch_pacer_doc_by_rd_base

    :param self: The celery task.
    :param rd_pk: The PK of the RECAP Document to get.
    :param fq_pk: The PK of the RECAP Fetch Queue to update.
    :param magic_number: The magic number to fetch PACER documents for free
    this is an optional field, only used by RECAP Email documents
    :return: The RECAPDocument PK
    """
    return fetch_pacer_doc_by_rd_base(self, rd_pk, fq_pk, magic_number)


@app.task(
    bind=True,
    autoretry_for=(RedisConnectionError, PacerLoginException),
    max_retries=5,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
@transaction.atomic
def fetch_pacer_doc_by_rd_and_mark_fq_completed(
    self,
    rd_pk: int,
    fq_pk: int,
    magic_number: str | None = None,
    omit_page_count: bool = False,
) -> None:
    """Celery task wrapper for fetch_pacer_doc_by_rd_base, which also marks
    the FQ as completed if the fetch is successful.

    :param self: The celery task.
    :param rd_pk: The PK of the RECAP Document to get.
    :param fq_pk: The PK of the RECAP Fetch Queue to update.
    :param magic_number: The magic number to fetch PACER documents for free
    this is an optional field, only used by RECAP Email documents
    :param omit_page_count: If true, omit requesting the page_count from doctor.
    :return: None
    """
    rd_pk = fetch_pacer_doc_by_rd_base(
        self, rd_pk, fq_pk, magic_number, omit_page_count=omit_page_count
    )
    if rd_pk:
        # Mark the FQ as completed if the RD pk is returned, since in any other
        # case, fetch_pacer_doc_by_rd_base will return None.
        fq = PacerFetchQueue.objects.get(pk=fq_pk)
        msg = "Successfully completed fetch and save."
        mark_fq_status(fq, msg, PROCESSING_STATUS.SUCCESSFUL)
    return None


@app.task(
    bind=True,
    autoretry_for=(RedisConnectionError, PacerLoginException, ParserError),
    max_retries=5,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
@transaction.atomic
def fetch_attachment_page(self: Task, fq_pk: int) -> list[int]:
    """Fetch a PACER attachment page by rd_pk

    This is very similar to process_recap_attachment, except that it manages
    status as it proceeds and it gets the cookie info from redis.

    :param self: The celery task
    :param fq_pk: The PK of the RECAP Fetch Queue to update.
    :return: A list of PQ IDs that require replication to sub-dockets.
    """

    fq = PacerFetchQueue.objects.get(pk=fq_pk)
    rd = fq.recap_document
    court_id = rd.docket_entry.docket.court_id
    pacer_case_id = rd.docket_entry.docket.pacer_case_id
    pacer_doc_id = rd.pacer_doc_id
    # Check court connectivity, if fails retry the task, hopefully, it'll be
    # retried in a different not blocked node
    if not is_pacer_court_accessible(court_id):
        if self.request.retries == self.max_retries:
            msg = f"Blocked by court: {court_id}"
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return []
        raise self.retry()

    mark_fq_status(fq, "", PROCESSING_STATUS.IN_PROGRESS)
    if not pacer_doc_id:
        msg = f"Unable to get attachment page: Unknown pacer_doc_id for RECAP Document object {rd.pk}"
        mark_fq_status(fq, msg, PROCESSING_STATUS.NEEDS_INFO)
        self.request.chain = None
        return []

    is_acms_case = rd.is_acms_document()
    if is_acms_case and not pacer_case_id:
        msg = f"Unable to complete purchase: Missing case_id for RECAP Document object {rd.pk}."
        mark_fq_status(fq, msg, PROCESSING_STATUS.NEEDS_INFO)
        self.request.chain = None
        return []

    session_data = get_pacer_cookie_from_cache(fq.user_id)
    if not session_data:
        msg = "Unable to find cached cookies. Aborting request."
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        self.request.chain = None
        return []

    try:
        r = get_att_report_by_rd(rd, session_data)
    except ParserError as exc:
        if self.request.retries == self.max_retries:
            msg = "ParserError while getting attachment page"
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return []
        raise self.retry(exc=exc)
    except HTTPError as exc:
        msg = "Failed to get attachment page from network."
        if exc.response.status_code in [
            HTTPStatus.INTERNAL_SERVER_ERROR,
            HTTPStatus.GATEWAY_TIMEOUT,
        ]:
            if self.request.retries == self.max_retries:
                mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
                self.request.chain = None
                return []
            logger.info(
                "Ran into HTTPError: %s. Retrying.", exc.response.status_code
            )
            raise self.retry(exc=exc)
        else:
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return []
    except requests.RequestException as exc:
        if self.request.retries == self.max_retries:
            msg = "Failed to get attachment page from network."
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return []
        logger.info("Ran into a RequestException. Retrying.")
        raise self.retry(exc=exc)
    except PacerLoginException as exc:
        msg = "PacerLoginException while getting attachment page"
        if self.request.retries == self.max_retries:
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            delete_pacer_cookie_from_cache(fq.user_id)
            self.request.chain = None
            return []
        mark_fq_status(
            fq, f"{msg} Retrying.", PROCESSING_STATUS.QUEUED_FOR_RETRY
        )
        raise self.retry(exc=exc)

    is_appellate = is_appellate_court(court_id)
    if not is_acms_case:
        text = r.response.text
        # Determine the appropriate parser function based on court jurisdiction
        # (appellate or district)
        att_data_parser = (
            get_data_from_appellate_att_report
            if is_appellate
            else get_data_from_att_report
        )
        att_data = att_data_parser(text, court_id)
    else:
        att_data = r.data
        text = json.dumps(r.data, default=str)

    if att_data == {}:
        msg = "Not a valid attachment page upload"
        mark_fq_status(fq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        self.request.chain = None
        return []

    if is_acms_case:
        document_number = att_data["entry_number"]
    elif is_appellate:
        # Appellate attachments don't contain a document_number
        document_number = None
    else:
        document_number = att_data["document_number"]

    try:
        async_to_sync(merge_attachment_page_data)(
            rd.docket_entry.docket.court,
            pacer_case_id,
            att_data["pacer_doc_id"],
            document_number,
            text,
            att_data["attachments"],
            is_acms_attachment=is_acms_case,
        )
    except RECAPDocument.MultipleObjectsReturned:
        msg = (
            "Too many documents found when attempting to associate "
            "attachment data"
        )
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        self.request.chain = None
        return []
    except RECAPDocument.DoesNotExist as exc:
        msg = "Could not find docket to associate with attachment metadata"
        if self.request.retries == self.max_retries:
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return []
        mark_fq_status(fq, msg, PROCESSING_STATUS.QUEUED_FOR_RETRY)
        raise self.retry(exc=exc)
    msg = "Successfully completed fetch and save."
    mark_fq_status(fq, msg, PROCESSING_STATUS.SUCCESSFUL)

    # Logic to replicate the attachment page to sub-dockets matched by RECAPDocument
    if is_appellate_court(court_id):
        # Subdocket replication for appellate courts is currently not supported.
        self.request.chain = None
        return []

    subdocket_pqs_to_replicate = find_subdocket_atts_rds_from_data(
        fq.user_id, court_id, pacer_doc_id, [pacer_case_id], text.encode()
    )
    if not subdocket_pqs_to_replicate:
        self.request.chain = None
        return []

    # Return PQ IDs to process attachment page replication for sub-dockets.
    return subdocket_pqs_to_replicate


@app.task(
    bind=True,
    ignore_result=True,
)
def replicate_fq_att_page_to_subdocket_rds(
    self: Task, pq_ids_to_process: list[int]
) -> None:
    """Replicate Attachment page to subdocket RECAPDocuments.

    :param self: The celery task
    :param pq_ids_to_process: A list of PQ IDs that require replication to sub-dockets.
    :return: None
    """

    for pq_pk in pq_ids_to_process:
        async_to_sync(process_recap_attachment)(pq_pk)


@app.task(
    bind=True,
    ignore_result=True,
)
def replicate_fq_pdf_to_subdocket_rds(
    self: Task, pq_ids_to_process: list[int]
) -> None:
    """Replicate a PDF to subdocket RECAPDocuments.

    :param self: The celery task
    :param pq_ids_to_process: A list of PQ IDs that require replication to sub-dockets.
    :return: None
    """

    for pq_pk in pq_ids_to_process:
        async_to_sync(process_recap_pdf)(pq_pk)


def get_fq_docket_kwargs(fq):
    """Gather the kwargs for the Juriscraper DocketReport from the fq object

    :param fq: The PacerFetchQueue object
    :return: A dict of the kwargs we can send to the DocketReport
    """
    return {
        "doc_num_start": fq.de_number_start,
        "doc_num_end": fq.de_number_end,
        "date_start": fq.de_date_start,
        "date_end": fq.de_date_end,
        "show_parties_and_counsel": fq.show_parties_and_counsel,
        "show_terminated_parties": fq.show_terminated_parties,
        "show_list_of_member_cases": fq.show_list_of_member_cases,
    }


def get_fq_appellate_docket_kwargs(fq: PacerFetchQueue):
    """Gather the kwargs for the Juriscraper AppellateDocketReport from the fq
    object

    :param fq: The PacerFetchQueue object
    :return: A dict of the kwargs we can send to the DocketReport
    """
    return {
        "show_docket_entries": True,
        "show_orig_docket": True,
        "show_prior_cases": True,
        "show_associated_cases": fq.show_list_of_member_cases,
        "show_panel_info": True,
        "show_party_atty_info": fq.show_parties_and_counsel,
        "show_caption": True,
        "date_start": fq.de_date_start,
        "date_end": fq.de_date_end,
    }


def fetch_pacer_case_id_and_title(s, fq, court_id):
    """Use PACER's hidden API to learn the pacer_case_id of a case

    :param s: A PacerSession object to use
    :param fq: The PacerFetchQueue object to use
    :param court_id: The CL ID of the court
    :return: A dict of the new information or an empty dict if it fails
    """

    if (fq.docket_id and not fq.docket.pacer_case_id) or fq.docket_number:
        # We lack the pacer_case_id either on the docket or from the
        # submission. Look it up.
        docket_number = fq.docket_number or getattr(
            fq.docket, "docket_number", None
        )

        report = PossibleCaseNumberApi(map_cl_to_pacer_id(court_id), s)
        report.query(docket_number)
        return report.data()
    return {}


def create_or_update_docket_data_from_fetch(
    fq: PacerFetchQueue,
    court_id: str,
    pacer_case_id: str | None,
    report: DocketReport | AppellateDocketReport | ACMSDocketReport,
    docket_data: dict[str, Any],
) -> dict[str, str | bool]:
    """Creates or updates docket data in the database from fetched data.

    :param fq: The PacerFetchQueue record associated with this fetch.
    :param court_id: The CL ID of the court.
    :param pacer_case_id: The pacer_case_id of the docket, if known.
    :param report: The BaseDocketReport object containing the fetched data.
    :param docket_data: A dictionary containing the parsed docket data.
    :return: a dict with information about the docket and the new data
    """
    if fq.docket_id:
        d = Docket.objects.get(pk=fq.docket_id)
    else:
        d = async_to_sync(find_docket_object)(
            court_id,
            pacer_case_id,
            docket_data["docket_number"],
            docket_data.get("federal_defendant_number"),
            docket_data.get("federal_dn_judge_initials_assigned"),
            docket_data.get("federal_dn_judge_initials_referred"),
        )
    rds_created, content_updated = merge_pacer_docket_into_cl_docket(
        d, pacer_case_id, docket_data, report, appellate=False
    )
    return {
        "docket_pk": d.pk,
        "content_updated": bool(rds_created or content_updated),
    }


def fetch_docket_by_pacer_case_id(
    session: SessionData,
    court_id: str,
    pacer_case_id: str,
    fq: PacerFetchQueue,
) -> dict[str, int | bool]:
    """Download the docket from PACER and merge it into CL

    :param session: A PacerSession object to work with
    :param court_id: The CL ID of the court
    :param pacer_case_id: The pacer_case_id of the docket, if known
    :param fq: The PacerFetchQueue object
    :return: a dict with information about the docket and the new data
    """
    report = DocketReport(map_cl_to_pacer_id(court_id), session)
    report.query(pacer_case_id, **get_fq_docket_kwargs(fq))

    docket_data = report.data
    if not docket_data:
        raise ParsingException("No data found in docket report.")
    return create_or_update_docket_data_from_fetch(
        fq, court_id, pacer_case_id, report, docket_data
    )


def purchase_appellate_docket_by_docket_number(
    session: SessionData,
    court_id: str,
    docket_number: str,
    fq: PacerFetchQueue,
    **kwargs,
) -> dict[str, int | bool]:
    """Purchases and processes an appellate docket from PACER by docket number.

    :param session: A PacerSession object to work with
    :param court_id: The CL ID of the court
    :param docket_number: The docket number of the appellate case.
    :param fq: The PacerFetchQueue object
    :return: a dict with information about the docket and the new data
    """
    acms_case_id = None

    if should_check_acms_court(court_id):
        acms_search = AcmsCaseSearch(court_id=court_id, pacer_session=session)
        acms_search.query(docket_number)
        acms_case_id = (
            acms_search.data["pcx_caseid"] if acms_search.data else None
        )

    pacer_court_id = map_cl_to_pacer_id(court_id)
    report_class = ACMSDocketReport if acms_case_id else AppellateDocketReport
    report = report_class(pacer_court_id, session)

    if acms_case_id:
        # ACMSDocketReport only accepts the case ID; filters are not currently
        # supported for ACMS docket reports.
        report.query(acms_case_id)
    else:
        report.query(docket_number, **kwargs)

    docket_data = report.data
    if not docket_data:
        raise ParsingException("No data found in docket report.")

    if acms_case_id:
        docket_data["docket_entries"] = sort_acms_docket_entries(
            docket_data["docket_entries"]
        )
    return create_or_update_docket_data_from_fetch(
        fq, court_id, None, report, docket_data
    )


@app.task(
    bind=True,
    autoretry_for=(PacerLoginException, RedisConnectionError),
    max_retries=5,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
def fetch_appellate_docket(self, fq_pk):
    """Fetches an appellate docket from PACER using the docket number
    associated with the provided Fetch Queue record to attempt the purchase.

    :param fq_pk: The PK of the Fetch Queue to update.
    :return: None
    """
    fq = PacerFetchQueue.objects.get(pk=fq_pk)
    court_id = fq.court_id or getattr(fq.docket, "court_id", None)

    # Check court connectivity, if fails retry the task, hopefully, it'll be
    # retried in a different not blocked node
    if not is_pacer_court_accessible(court_id):
        if self.request.retries == self.max_retries:
            msg = f"Blocked by court: {court_id}"
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return None
        raise self.retry()

    async_to_sync(mark_pq_status)(fq, "", PROCESSING_STATUS.IN_PROGRESS)

    session_data = get_pacer_cookie_from_cache(fq.user_id)
    if session_data is None:
        msg = f"Cookie cache expired before task could run for user: {fq.user_id}"
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        self.request.chain = None
        return None

    s = ProxyPacerSession(
        cookies=session_data.cookies, proxy=session_data.proxy_address
    )

    docket_number = fq.docket_number or getattr(
        fq.docket, "docket_number", None
    )
    start_time = now()
    try:
        result = purchase_appellate_docket_by_docket_number(
            session=s,
            court_id=court_id,
            docket_number=docket_number,
            fq=fq,
            **get_fq_appellate_docket_kwargs(fq),
        )
    except (requests.RequestException, ReadTimeoutError) as exc:
        msg = f"Network error while purchasing docket for fq: {fq_pk}."
        if self.request.retries == self.max_retries:
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return None
        mark_fq_status(
            fq, f"{msg}Retrying.", PROCESSING_STATUS.QUEUED_FOR_RETRY
        )
        raise self.retry(exc=exc)
    except PacerLoginException as exc:
        msg = (
            f"PacerLoginException while getting pacer_case_id for fq: {fq_pk}."
        )
        if self.request.retries == self.max_retries:
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return None
        mark_fq_status(
            fq, f"{msg} Retrying.", PROCESSING_STATUS.QUEUED_FOR_RETRY
        )
        raise self.retry(exc=exc)
    except ParsingException:
        msg = f"Unable to purchase docket for fq: {fq_pk}."
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        self.request.chain = None
        return None

    content_updated = result["content_updated"]
    d_pk = result["docket_pk"]
    if content_updated:
        newly_enqueued = enqueue_docket_alert(d_pk)
        if newly_enqueued:
            send_alert_and_webhook(d_pk, start_time)

    # Link docket to fq if not previously linked
    if not fq.docket_id:
        fq.docket_id = d_pk
        fq.save()

    return result


@app.task(
    bind=True,
    autoretry_for=(PacerLoginException, RedisConnectionError),
    max_retries=5,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
def fetch_docket(self, fq_pk):
    """Fetch a docket from PACER

    This mirrors code elsewhere that gets dockets, but manages status as it
    goes through the process.

    :param fq_pk: The PK of the RECAP Fetch Queue to update.
    :return: None
    """

    fq = PacerFetchQueue.objects.get(pk=fq_pk)
    court_id = fq.court_id or getattr(fq.docket, "court_id", None)
    # Check court connectivity, if fails retry the task, hopefully, it'll be
    # retried in a different not blocked node
    if not is_pacer_court_accessible(court_id):
        if self.request.retries == self.max_retries:
            msg = f"Blocked by court: {court_id}"
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return None
        raise self.retry()

    async_to_sync(mark_pq_status)(fq, "", PROCESSING_STATUS.IN_PROGRESS)

    session_data = get_pacer_cookie_from_cache(fq.user_id)
    if session_data is None:
        msg = f"Cookie cache expired before task could run for user: {fq.user_id}"
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        self.request.chain = None
        return None

    s = ProxyPacerSession(
        cookies=session_data.cookies, proxy=session_data.proxy_address
    )
    try:
        result = fetch_pacer_case_id_and_title(s, fq, court_id)
    except (requests.RequestException, ReadTimeoutError) as exc:
        msg = f"Network error getting pacer_case_id for fq: {fq_pk}."
        if self.request.retries == self.max_retries:
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return None
        mark_fq_status(
            fq, f"{msg} Retrying.", PROCESSING_STATUS.QUEUED_FOR_RETRY
        )
        raise self.retry(exc=exc)
    except PacerLoginException as exc:
        msg = (
            f"PacerLoginException while getting pacer_case_id for fq: {fq_pk}."
        )
        if self.request.retries == self.max_retries:
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return None
        mark_fq_status(
            fq, f"{msg} Retrying.", PROCESSING_STATUS.QUEUED_FOR_RETRY
        )
        raise self.retry(exc=exc)
    except ParsingException:
        msg = "Unable to parse pacer_case_id for docket."
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        self.request.chain = None
        return None

    # result can be one of three values:
    #   None       --> Sealed or missing case
    #   Empty dict --> Didn't run the pacer_case_id lookup (wasn't needed)
    #   Full dict  --> Ran the query, got back results

    if result is None:
        msg = "Cannot find case by docket number (perhaps it's sealed?)"
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        self.request.chain = None
        return None

    pacer_case_id = (
        getattr(fq, "pacer_case_id", None)
        or getattr(fq.docket, "pacer_case_id", None)
        or result.get("pacer_case_id")
    )

    if not pacer_case_id:
        msg = "Unable to determine pacer_case_id for docket."
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        self.request.chain = None
        return None

    start_time = now()
    try:
        result = fetch_docket_by_pacer_case_id(s, court_id, pacer_case_id, fq)
    except (requests.RequestException, ReadTimeoutError) as exc:
        msg = "Network error getting pacer_case_id for fq: %s."
        if self.request.retries == self.max_retries:
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return None
        mark_fq_status(
            fq, f"{msg}Retrying.", PROCESSING_STATUS.QUEUED_FOR_RETRY
        )
        raise self.retry(exc=exc)
    except ParsingException:
        msg = "Unable to parse pacer_case_id for docket."
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        self.request.chain = None
        return None

    content_updated = result["content_updated"]
    d_pk = result["docket_pk"]
    if content_updated:
        newly_enqueued = enqueue_docket_alert(d_pk)
        if newly_enqueued:
            send_alert_and_webhook(d_pk, start_time)

    # Link docket to fq if not previously linked
    if not fq.docket_id:
        fq.docket_id = d_pk
        fq.save()

    return result


@app.task
def mark_fq_successful(fq_pk):
    fq = PacerFetchQueue.objects.get(pk=fq_pk)
    msg = "Successfully completed fetch and save."
    mark_fq_status(fq, msg, PROCESSING_STATUS.SUCCESSFUL)


def mark_fq_status(fq, msg, status):
    """Update the PacerFetchQueue item with the status and message provided

    :param fq: The PacerFetchQueue item to update
    :param msg: The message to associate
    :param status: The status code to associate. If SUCCESSFUL, date_completed
    is set as well.
    :return: None
    """
    fq.message = msg
    fq.status = status
    if status == PROCESSING_STATUS.SUCCESSFUL:
        fq.date_completed = now()
    fq.save()
    send_recap_fetch_webhooks(fq)


def get_recap_email_recipients(
    email_recipients: list[str],
) -> list[str]:
    """Get the recap.email recipients from the email_recipients list.

    :param email_recipients: List of dicts that contains the notification
    email recipients in the format: "name": name, "email_addresses": [""]
    :return: List of recap.email addresses
    """

    # Select only @recap.email addresses
    recap_email_recipients = [
        recap_email.lower()
        for recap_email in email_recipients
        if "@recap.email" in recap_email
    ]
    return recap_email_recipients


def get_attachment_page_by_url(att_page_url: str, court_id: str) -> str | None:
    """Get the attachment page report for recap.email documents without being
    logged into PACER.

    :param att_page_url: The free look link url to the attachment page
    :param court_id: The court ID we're working with
    :return: The HTML page text or None if it's not a valid attachment page
    """

    logger.info(
        "Querying the email notice attachment page endpoint at URL: %s",
        att_page_url,
    )
    req_timeout = (60, 300)
    att_response = requests.get(att_page_url, timeout=req_timeout)
    att_data = get_data_from_att_report(att_response.text, court_id)
    if att_data == {}:
        msg = "Not a valid attachment page upload for recap.email"
        logger.warning(msg)
        return None
    return att_response.text


def set_rd_sealed_status(
    rd: RECAPDocument, magic_number: str | None, potentially_sealed: bool
) -> None:
    """Set RD is_sealed status according to the following conditions:

    If potentially_sealed is false, set as not sealed.
    If potentially_sealed is True and there magic_number, set as sealed.
    If potentially_sealed is True and no magic_number available, check on PACER
    if the document is sealed.

    :param rd: The RECAPDocument to set is sealed status.
    :param magic_number: The magic number if available.
    :param potentially_sealed: Weather the RD might be sealed or not.
    :return: None
    """

    rd.refresh_from_db()
    if not rd.pacer_doc_id:
        return

    if not potentially_sealed:
        rd.is_sealed = False
        rd.save()
        return

    rd.is_sealed = True
    if not magic_number and not is_pacer_doc_sealed(
        rd.docket_entry.docket.court.pk, rd.pacer_doc_id
    ):
        rd.is_sealed = False
    rd.save()


def save_pacer_doc_from_pq(
    self: Task,
    rd: RECAPDocument,
    fq: PacerFetchQueue,
    pq: ProcessingQueue,
    magic_number: str | None,
) -> int | None:
    """Save the PDF binary previously downloaded and stored in a PQ object to
    the corresponding RECAPDocument.

    :param self: The parent celery task
    :param rd: The RECAP Document to get.
    :param fq: The RECAP Fetch Queue to update.
    :param pq: The ProcessingQueue that contains the PDF document.
    :param magic_number: The magic number to fetch PACER documents for free.
    :return: The RECAPDocument PK
    """

    if rd.is_available:
        msg = "PDF already marked as 'is_available'. Doing nothing."
        mark_fq_status(fq, msg, PROCESSING_STATUS.SUCCESSFUL)
        return

    if pq.status == PROCESSING_STATUS.FAILED or not pq.filepath_local:
        set_rd_sealed_status(rd, magic_number, potentially_sealed=True)
        mark_fq_status(fq, pq.error_message, PROCESSING_STATUS.FAILED)
        return

    with pq.filepath_local.open(mode="rb") as local_path:
        pdf_bytes = local_path.read()

    mark_fq_status(fq, "", PROCESSING_STATUS.IN_PROGRESS)

    pacer_case_id = rd.docket_entry.docket.pacer_case_id
    court_id = rd.docket_entry.docket.court_id
    success, msg = update_rd_metadata(
        self,
        rd.pk,
        pdf_bytes,
        pq.error_message,
        court_id,
        pacer_case_id,
        rd.pacer_doc_id,
        rd.document_number,
        rd.attachment_number,
    )

    if success is False:
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        return

    msg = "Successfully completed fetch and save."
    mark_fq_status(fq, msg, PROCESSING_STATUS.SUCCESSFUL)
    set_rd_sealed_status(rd, magic_number, potentially_sealed=False)
    return rd.pk


def is_short_bankr_doc_id(pacer_doc_id: str | None, court_id: str) -> bool:
    """Check if the given pacer_doc_id is considered "short" in a bankruptcy
    court. This type of pacer_doc_id appears in bankruptcy NEFs, possibly when
    the document is sealed or unavailable at the time the email is delivered.
    We should avoid fetching these kinds of unavailable documents or
    attachment pages.

    :param pacer_doc_id: The pacer_doc_id.
    :param court_id: The court ID.
    :return: True if the document ID is 4 characters and belongs to a
    bankruptcy court, otherwise False.
    """

    return (
        pacer_doc_id is not None
        and len(pacer_doc_id) == 4
        and is_bankruptcy_court(court_id)
    )


def download_pacer_pdf_and_save_to_pq(
    court_id: str,
    session_data: SessionData,
    cutoff_date: datetime,
    magic_number: str | None,
    pacer_case_id: str,
    pacer_doc_id: str | None,
    user_pk: int,
    appellate: bool,
    attachment_number: int = None,
    de_seq_num: str | None = None,
    is_bankr_short_doc_id: bool = False,
) -> ProcessingQueue:
    """Try to download a PACER document from the notification via the magic
    link and store it in a ProcessingQueue object. So it can be copied to every
    Case/RECAPDocument (multi-docket NEFs). In case of a failure/retry in any
    following step, the one-look PACER document will be already stored in the
    PQ object. Increasing the reliability of saving PACER documents.

    :param court_id: A CourtListener court ID to query the free document.
    :param session_data: A SessionData object containing the session's cookies
    and proxy.
    :param cutoff_date: The datetime from which we should query
     ProcessingQueue objects. For the main RECAPDocument the datetime the
     EmailProcessingQueue was created. For attachments the datetime the
     attachment RECAPDocument was created.
    :param magic_number: The magic number to fetch PACER documents for free.
    :param pacer_case_id: The pacer_case_id to query the free document.
    :param pacer_doc_id: The pacer_doc_id to query the free document.
    :param user_pk: The user to associate with the ProcessingQueue object when
     it's created.
    :param appellate: Whether the download belongs to an appellate court.
    :param attachment_number: The RECAPDocument attachment_number in case the
     request belongs to an attachment document.
    :param de_seq_num: The sequential number assigned by the PACER system to
     identify the docket entry within a case.
    :param is_bankr_short_doc_id: A boolean indicating whether the pacer_doc_id
     is a bad short bankruptcy doc ID.
    :return: The ProcessingQueue object that's created or returned if existed.
    """

    # If pacer_doc_id is None, probably a minute entry, set it to ""
    if pacer_doc_id is None:
        pacer_doc_id = ""
    with transaction.atomic():
        (
            pq,
            created,
        ) = ProcessingQueue.objects.get_or_create(
            uploader_id=user_pk,
            pacer_doc_id=pacer_doc_id,
            pacer_case_id=pacer_case_id,
            court_id=court_id,
            upload_type=UPLOAD_TYPE.PDF,
            date_created__gt=cutoff_date,
        )
        if created and magic_number and not is_bankr_short_doc_id:
            response, r_msg = download_pdf_by_magic_number(
                court_id,
                pacer_doc_id,
                pacer_case_id,
                session_data,
                magic_number,
                appellate,
                de_seq_num,
            )
            if response:
                file_name = get_document_filename(
                    court_id,
                    pacer_case_id,
                    pacer_doc_id,
                    attachment_number,
                )
                cf = ContentFile(response.content)
                pq.filepath_local.save(file_name, cf, save=False)
                pq.save()
                return pq

        if is_bankr_short_doc_id:
            r_msg = "Invalid short pacer_doc_id for bankruptcy court."
        if not magic_number:
            r_msg = "No magic number available to download the document."
        if created:
            async_to_sync(mark_pq_status)(
                pq, r_msg, PROCESSING_STATUS.FAILED, "error_message"
            )
        # Return an existing PQ object after a retry or for multi-docket NEFs,
        # where the file is downloaded only once.
        return pq


def get_and_copy_recap_attachment_docs(
    self: Task,
    att_rds: list[RECAPDocument],
    court_id: str,
    magic_number: str | None,
    pacer_case_id: str,
    user_pk: int,
    de_seq_num: str | None = None,
) -> list[ProcessingQueue]:
    """Download and copy the corresponding PACER PDF to all the notification
    RECAPDocument attachments, including support for multi-docket NEFs.

    :param self: The parent celery task.
    :param att_rds: A list for RECAPDocument attachments to process.
    :param court_id: A CourtListener court ID to query the free document.
    :param magic_number: The magic number to fetch PACER documents for free.
    :param pacer_case_id: The pacer_case_id to query the free document.
    :param user_pk: The user to associate with the ProcessingQueue object.
    :param de_seq_num: The sequential number assigned by the PACER system to
     identify the docket entry within a case.
    :return: None
    """

    session_data = get_pacer_cookie_from_cache(user_pk)
    appellate = False
    unique_pqs = []
    for rd_att in att_rds:
        cutoff_date = rd_att.date_created
        pq = download_pacer_pdf_and_save_to_pq(
            court_id,
            session_data,
            cutoff_date,
            magic_number,
            pacer_case_id,
            rd_att.pacer_doc_id,
            user_pk,
            appellate,
            rd_att.attachment_number,
            de_seq_num=de_seq_num,
        )
        fq = PacerFetchQueue.objects.create(
            user_id=user_pk,
            request_type=REQUEST_TYPE.PDF,
            recap_document=rd_att,
        )
        save_pacer_doc_from_pq(self, rd_att, fq, pq, magic_number)
        if pq not in unique_pqs:
            unique_pqs.append(pq)

    return unique_pqs


@dataclass
class DocketUpdatedData:
    docket: Docket
    des_returned: list
    rds_updated: list
    rds_created: list
    content_updated: bool


def open_and_validate_email_notification(
    self: Task,
    epq: EmailProcessingQueue,
) -> tuple[dict[str, str | bool | list[DocketType]] | None, str]:
    """Open and read a recap.email notification from S3, then validate if it's
    a valid NEF or NDA.

    :param self: The Celery task
    :param epq: The EmailProcessingQueue object.
    :return: A two tuple of a dict containing the notification data if valid
    or None otherwise, the raw notification body to store in next steps.
    """

    message_id = epq.message_id
    bucket = RecapEmailSESStorage()
    # Try to read the file using utf-8.
    # If it fails fallback on iso-8859-1
    try:
        with bucket.open(message_id, "rb") as f:
            body = f.read().decode("utf-8")
    except UnicodeDecodeError:
        with bucket.open(message_id, "rb") as f:
            body = f.read().decode("iso-8859-1")
    except FileNotFoundError as exc:
        if self.request.retries == self.max_retries:
            msg = "File not found."
            async_to_sync(mark_pq_status)(
                epq, msg, PROCESSING_STATUS.FAILED, "status_message"
            )
            return None, ""
        else:
            # Do a retry. Hopefully the file will be in place soon.
            raise self.retry(exc=exc)

    report = S3NotificationEmail(map_cl_to_pacer_id(epq.court_id))
    report._parse_text(body)
    data = report.data
    if (
        data == {}
        or len(data["dockets"]) == 0
        or len(data["dockets"][0]["docket_entries"]) == 0
        or data["dockets"][0]["docket_entries"][0]["pacer_case_id"] is None
    ):
        msg = "Not a valid notification email. No message content."
        async_to_sync(mark_pq_status)(
            epq, msg, PROCESSING_STATUS.INVALID_CONTENT, "status_message"
        )
        data = None
    return data, body


def fetch_attachment_data(
    document_url: str,
    court_id: str,
    dockets_updated: list[DocketUpdatedData],
    user_pk: int,
) -> str:
    """Fetch the attachment page data for the main document in the
    recap.email notification.

    :param document_url: The document URL including the magic number to get the
     attachment page without being logged into PACER.
    :param court_id: The court ID we're working with.
    :param dockets_updated: A list of DocketUpdatedData containing the dockets
    to merge the attachments in.
    :param user_pk: The user to associate with the ProcessingQueue object.
    :return: The HTML page text.
    """
    session_data = get_pacer_cookie_from_cache(user_pk)
    # Try to fetch the attachment page without being logged into PACER using
    # the free look URL.
    att_report_text = get_attachment_page_by_url(document_url, court_id)
    if att_report_text is None:
        main_rd = (
            dockets_updated[0]
            .des_returned[0]
            .recap_documents.earliest("date_created")
        )
        # Get the attachment page being logged into PACER
        att_report = get_att_report_by_rd(main_rd, session_data)
        att_report_text = att_report.response.text

    return att_report_text


def merge_rd_attachments(
    att_report_text: str,
    dockets_updated: list[DocketUpdatedData],
    user_pk: int,
) -> list[RECAPDocument]:
    """Merge the attachment data into the dockets returned by the recap.email
    notification.

    :param att_report_text: The attachment page report text.
    :param dockets_updated: A list of DocketUpdatedData containing the dockets
    to merge the attachments in.
    :param user_pk: The user to associate with the ProcessingQueue object.
    :return: A list of RECAPDocuments modified or created during the process
    """

    all_attachment_rds = []
    for docket_entry in dockets_updated:
        # Merge the attachments for each docket/recap document
        main_rd_local = docket_entry.des_returned[0].recap_documents.earliest(
            "date_created"
        )
        pq_pk = save_attachment_pq_from_text(
            main_rd_local.pk,
            user_pk,
            att_report_text,
        )
        # Attachments for multi-docket NEFs are the same for every case
        # mentioned in the notification. The only difference between them is a
        # different document_number in every case for the main document the
        # attachments belong to. So we only query and parse the Attachment page
        # one time in PACER and provide the correct document_number to use for
        # every case when merging the attachments into each docket.
        main_rd_document_number = int(main_rd_local.document_number)
        pq_status, msg, rds_affected = async_to_sync(process_recap_attachment)(
            pq_pk, document_number=main_rd_document_number
        )
        all_attachment_rds += rds_affected
    return all_attachment_rds


def replicate_recap_email_to_subdockets(
    user_pk: int,
    court_id: str,
    pacer_doc_id: str,
    unique_case_ids: list[str],
    main_pdf_filepath: FieldFile,
    att_report_text: str | None,
    att_pqs: list[ProcessingQueue],
) -> None:
    """Replicate recap.email content to subdockets no mentioned in the
    email notification.

    - Replication of main PDF to subdockets.
    - Replication of attachment page to subdockets.
    - Replication of attachment PDFs to subdockets.

    :param user_pk: The User ID.
    :param court_id: The Court ID.
    :param pacer_doc_id: The PACER document ID from the main document.
    :param unique_case_ids: A list of unique PACER case IDs to exclude.
    :param main_pdf_filepath: The filepath to the main PDF document.
    :param att_report_text: The attachment page report text.
    :param att_pqs: A list of attachment PQ objects from attachments that require
    replication.

    :return: None
    """

    main_pdf_binary_content = (
        main_pdf_filepath.open(mode="rb").read() if main_pdf_filepath else None
    )
    subdocket_pdf_pqs_to_replicate = []
    # Replicate main PDF to subdockets not mentioned in the notification.
    if main_pdf_binary_content:
        subdocket_pdf_pqs_to_replicate.extend(
            find_subdocket_pdf_rds_from_data(
                user_pk,
                court_id,
                pacer_doc_id,
                unique_case_ids,
                main_pdf_binary_content,
            )
        )
    if subdocket_pdf_pqs_to_replicate:
        replicate_fq_pdf_to_subdocket_rds.delay(subdocket_pdf_pqs_to_replicate)

    # Replicate Attachments to subdockets not mentioned in the notification.
    subdocket_att_pqs_to_replicate = []
    if att_report_text:
        subdocket_att_pqs_to_replicate.extend(
            find_subdocket_atts_rds_from_data(
                user_pk,
                court_id,
                pacer_doc_id,
                unique_case_ids,
                att_report_text.encode(),
            )
        )
    if subdocket_att_pqs_to_replicate:
        replicate_fq_att_page_to_subdocket_rds.delay(
            subdocket_att_pqs_to_replicate
        )

    # Replicate attachments PDFs to subdockets not mentioned in the notification.
    all_pdf_atts_pqs_to_replicate = []
    for att_pq in att_pqs:
        pdf_binary_content_att = (
            att_pq.filepath_local.open(mode="rb").read()
            if att_pq.filepath_local
            else None
        )
        if pdf_binary_content_att:
            all_pdf_atts_pqs_to_replicate.extend(
                find_subdocket_pdf_rds_from_data(
                    user_pk,
                    court_id,
                    att_pq.pacer_doc_id,
                    unique_case_ids,
                    pdf_binary_content_att,
                )
            )
    if all_pdf_atts_pqs_to_replicate:
        replicate_fq_pdf_to_subdocket_rds.delay(all_pdf_atts_pqs_to_replicate)


@app.task(
    bind=True,
    autoretry_for=(
        botocore_exception.HTTPClientError,
        botocore_exception.ConnectionError,
        requests.ConnectionError,
        requests.RequestException,
        requests.ReadTimeout,
        PacerLoginException,
        RedisConnectionError,
    ),
    max_retries=10,
    retry_backoff=2 * 60,
    retry_backoff_max=60 * 60,
)
def process_recap_email(
    self: Task, epq_pk: int, user_pk: int
) -> list[int] | None:
    """Processes a recap.email when it comes in, fetches the free document and
    triggers docket alerts and webhooks.

    :param self: The task
    :param epq_pk: The EmailProcessingQueue object pk
    :param user_pk: The API user that sent this notification
    :return: An optional list to pass to the next task with recap documents pks
     that were downloaded
    """
    epq = EmailProcessingQueue.objects.get(pk=epq_pk)
    async_to_sync(mark_pq_status)(
        epq, "", PROCESSING_STATUS.IN_PROGRESS, "status_message"
    )
    data, body = open_and_validate_email_notification(self, epq)
    if data is None:
        self.request.chain = None
        return None

    dockets = data["dockets"]
    # Look for the main docket that has the valid magic number
    magic_number = pacer_doc_id = pacer_case_id = document_url = None
    for docket_data in dockets:
        docket_entry = docket_data["docket_entries"][0]
        if docket_entry["pacer_magic_num"] is not None:
            magic_number = docket_entry["pacer_magic_num"]
            pacer_doc_id = docket_entry["pacer_doc_id"]
            pacer_case_id = docket_entry["pacer_case_id"]
            document_url = docket_entry["document_url"]
            pacer_seq_no = docket_entry["pacer_seq_no"]
            break

    # Some notifications don't contain a magic number at all, assign the
    # pacer_doc_id, pacer_case_id and document_url from the first docket entry.
    if magic_number is None:
        pacer_doc_id = dockets[0]["docket_entries"][0]["pacer_doc_id"]
        pacer_case_id = dockets[0]["docket_entries"][0]["pacer_case_id"]
        document_url = dockets[0]["docket_entries"][0]["document_url"]
        pacer_seq_no = dockets[0]["docket_entries"][0]["pacer_seq_no"]

    start_time = now()
    # Ensures we have PACER cookies ready to go.
    cookies_data = get_or_cache_pacer_cookies(
        user_pk, settings.PACER_USERNAME, settings.PACER_PASSWORD
    )
    court_id = epq.court_id
    appellate = data["appellate"]
    bankr_short_doc_id = is_short_bankr_doc_id(pacer_doc_id, court_id)
    # Try to download and store the main pacer document into a PQ object for
    # its future processing.
    pq = download_pacer_pdf_and_save_to_pq(
        court_id,
        cookies_data,
        epq.date_created,
        magic_number,
        pacer_case_id,
        pacer_doc_id,
        user_pk,
        appellate,
        de_seq_num=pacer_seq_no,
        is_bankr_short_doc_id=bankr_short_doc_id,
    )
    is_potentially_sealed_entry = (
        is_docket_entry_sealed(epq.court_id, pacer_case_id, pacer_doc_id)
        if pq.status == PROCESSING_STATUS.FAILED
        and not appellate
        and not bankr_short_doc_id
        else False
    )
    if appellate:
        # Get the document number for appellate documents.
        appellate_doc_num = get_document_number_for_appellate(
            epq.court_id, pacer_doc_id, pq
        )
        if appellate_doc_num:
            data["dockets"][0]["docket_entries"][0]["document_number"] = (
                appellate_doc_num
            )

    unique_case_ids = []
    got_content_updated = False
    main_rds_available = []
    with transaction.atomic():
        # Add/update docket entries for each docket mentioned in the
        # notification.
        dockets_updated = []
        for docket_data in dockets:
            docket_entry = docket_data["docket_entries"][0]
            docket = async_to_sync(find_docket_object)(
                epq.court_id,
                docket_entry["pacer_case_id"],
                docket_data["docket_number"],
                docket_data.get("federal_defendant_number"),
                docket_data.get("federal_dn_judge_initials_assigned"),
                docket_data.get("federal_dn_judge_initials_referred"),
            )
            docket.add_recap_source()
            async_to_sync(update_docket_metadata)(docket, docket_data)

            if not docket.pacer_case_id:
                docket.pacer_case_id = docket_entry["pacer_case_id"]
            docket.save()
            unique_case_ids.append(docket.pacer_case_id)

            # Add the HTML to the docket in case we need it someday.
            pacer_file = PacerHtmlFiles(
                content_object=docket, upload_type=UPLOAD_TYPE.SES_EMAIL
            )
            pacer_file.filepath.save(
                "docket.txt",
                # We only care about the ext w/S3PrivateUUIDStorageTest
                ContentFile(body.encode()),
            )
            if is_potentially_sealed_entry:
                continue

            # Add docket entries for each docket
            if bankr_short_doc_id:
                # We don't want bad bankruptcy short pacer_doc_ids.
                # Set it to None
                for de in docket_data["docket_entries"]:
                    de["pacer_doc_id"] = None
            (
                (des_returned, rds_updated),
                rds_created,
                content_updated,
            ) = async_to_sync(add_docket_entries)(
                docket, docket_data["docket_entries"]
            )
            d_updated = DocketUpdatedData(
                docket=docket,
                des_returned=des_returned,
                rds_updated=rds_updated,
                rds_created=rds_created,
                content_updated=content_updated,
            )
            if content_updated:
                got_content_updated = True
            dockets_updated.append(d_updated)

            if bankr_short_doc_id:
                # Avoid storing the main PDF for bad bankruptcy short pacer_doc_ids
                # since there is no document to copy.
                continue

            for rd in rds_created:
                # Download and store the main PACER document and then
                # assign/copy it to each corresponding RECAPDocument.
                fq = PacerFetchQueue.objects.create(
                    user_id=user_pk,
                    request_type=REQUEST_TYPE.PDF,
                    recap_document=rd,
                )
                save_pacer_doc_from_pq(self, rd, fq, pq, magic_number)
                rd.refresh_from_db()
                main_rds_available.append(rd.is_available)

        # Get NEF attachments and merge them.
        all_attachment_rds = []
        att_pqs = []
        att_report_text = None
        # Avoid fetching and merging attachments for sealed docket entries and
        # main documents with bad bankruptcy short pacer_doc_ids.
        if (
            data["contains_attachments"] is True
            and not is_potentially_sealed_entry
            and not bankr_short_doc_id
        ):
            att_report_text = fetch_attachment_data(
                document_url, epq.court_id, dockets_updated, user_pk
            )
            all_attachment_rds = merge_rd_attachments(
                att_report_text,
                dockets_updated,
                user_pk,
            )
            att_pqs = get_and_copy_recap_attachment_docs(
                self,
                all_attachment_rds,
                epq.court_id,
                magic_number,
                pacer_case_id,
                user_pk,
                de_seq_num=pacer_seq_no,
            )

    # Replicate content to subdockets not mentioned in the notification.
    valid_att_data = (
        get_data_from_att_report(att_report_text, court_id)
        if att_report_text
        else None
    )
    content_to_replicate = any(main_rds_available + [valid_att_data])
    if (
        pacer_doc_id
        and content_to_replicate
        and got_content_updated
        and not is_appellate_court(court_id)
    ):
        replicate_recap_email_to_subdockets(
            user_pk,
            court_id,
            pacer_doc_id,
            unique_case_ids,
            pq.filepath_local,
            att_report_text,
            att_pqs,
        )

    # After properly copying the PDF to related RECAPDocuments,
    # mark the PQ object as successful and delete its filepath_local
    if pq.status != PROCESSING_STATUS.FAILED:
        async_to_sync(mark_pq_successful)(pq)

    for pq in att_pqs:
        if pq.status != PROCESSING_STATUS.FAILED:
            async_to_sync(mark_pq_successful)(pq)

    # Send docket alerts and webhooks for each docket updated.
    recap_email_recipients = get_recap_email_recipients(epq.destination_emails)
    all_created_rds = []
    all_updated_rds = []
    for docket_updated in dockets_updated:
        if docket_updated.content_updated:
            newly_enqueued = enqueue_docket_alert(docket_updated.docket.pk)
            if newly_enqueued:
                send_alert_and_webhook.delay(
                    docket_updated.docket.pk,
                    start_time,
                    recap_email_recipients,
                )
        else:
            # If the current docket entry was added previously, send the alert
            # only to the recap email user that triggered the new alert.
            des_pks = [de.pk for de in docket_updated.des_returned]
            send_alert_and_webhook.delay(
                docket_updated.docket.pk,
                start_time,
                recap_email_recipients,
                des_pks,
            )
        all_created_rds += docket_updated.rds_created
        all_updated_rds += docket_updated.rds_updated

    if not is_potentially_sealed_entry:
        rds_to_extract = (
            all_attachment_rds + all_created_rds
            if not bankr_short_doc_id
            else []
        )
        rds_updated_or_created = (
            all_attachment_rds + all_created_rds + all_updated_rds
        )
        async_to_sync(associate_related_instances)(
            epq,
            d_id=None,
            de_id=None,
            rd_id=[rd.pk for rd in rds_updated_or_created],
        )
        msg = "Successful upload! Nice work."
        status = PROCESSING_STATUS.SUCCESSFUL
    else:
        rds_to_extract = []
        msg = "Could not retrieve Docket Entry"
        status = PROCESSING_STATUS.FAILED

    async_to_sync(mark_pq_status)(epq, msg, status, "status_message")

    if not rds_to_extract:
        self.request.chain = None
    return [rd.pk for rd in rds_to_extract]


def do_recap_document_fetch(epq: EmailProcessingQueue, user: User) -> None:
    return chain(
        process_recap_email.si(epq.pk, user.pk),
        extract_recap_pdf.s(),
    ).apply_async()
