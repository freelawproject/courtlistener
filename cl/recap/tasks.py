# coding=utf-8
import logging
import os
from zipfile import ZipFile

import requests
from celery.canvas import chain
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.utils.timezone import now
from juriscraper.lib.string_utils import CaseNameTweaker
from juriscraper.pacer import (
    AppellateDocketReport,
    AttachmentPage,
    DocketHistoryReport,
    DocketReport,
    ClaimsRegister,
)
from requests import HTTPError

from cl.alerts.tasks import enqueue_docket_alert, send_docket_alert
from cl.celery import app
from cl.corpus_importer.tasks import (
    download_pacer_pdf_by_rd,
    update_rd_metadata,
    get_pacer_case_id_and_title,
    get_docket_by_pacer_case_id,
    get_attachment_page_by_rd,
)
from cl.corpus_importer.utils import mark_ia_upload_needed
from cl.custom_filters.templatetags.text_filters import oxford_join
from cl.lib.crypto import sha1
from cl.lib.filesizes import convert_size_to_bytes
from cl.lib.pacer import map_cl_to_pacer_id
from cl.lib.pacer_session import get_pacer_cookie_from_cache
from cl.lib.recap_utils import get_document_filename
from cl.recap.mergers import (
    add_docket_entries,
    add_parties_and_attorneys,
    update_docket_appellate_metadata,
    update_docket_metadata,
    process_orphan_documents,
    find_docket_object,
    add_bankruptcy_data_to_docket,
    add_claims_to_docket,
    add_tags_to_objs,
    merge_attachment_page_data,
    get_data_from_att_report,
)
from cl.recap.models import (
    PacerHtmlFiles,
    ProcessingQueue,
    UPLOAD_TYPE,
    FjcIntegratedDatabase,
    REQUEST_TYPE,
    PacerFetchQueue,
    PROCESSING_STATUS,
)
from cl.scrapers.tasks import extract_recap_pdf, get_page_count
from cl.search.models import Docket, DocketEntry, RECAPDocument, Tag
from cl.search.tasks import add_or_update_recap_docket, add_items_to_solr


logger = logging.getLogger(__name__)
cnt = CaseNameTweaker()


def process_recap_upload(pq):
    """Process an item uploaded from an extension or API user.

    Uploaded objects can take a variety of forms, and we'll need to
    process them accordingly.
    """
    if pq.upload_type == UPLOAD_TYPE.DOCKET:
        chain(
            process_recap_docket.s(pq.pk), add_or_update_recap_docket.s()
        ).apply_async()
    elif pq.upload_type == UPLOAD_TYPE.ATTACHMENT_PAGE:
        process_recap_attachment.delay(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.PDF:
        process_recap_pdf.delay(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.DOCKET_HISTORY_REPORT:
        chain(
            process_recap_docket_history_report.s(pq.pk),
            add_or_update_recap_docket.s(),
        ).apply_async()
    elif pq.upload_type == UPLOAD_TYPE.APPELLATE_DOCKET:
        chain(
            process_recap_appellate_docket.s(pq.pk),
            add_or_update_recap_docket.s(),
        ).apply_async()
    elif pq.upload_type == UPLOAD_TYPE.APPELLATE_ATTACHMENT_PAGE:
        process_recap_appellate_attachment.delay(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.CLAIMS_REGISTER:
        process_recap_claims_register.delay(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.DOCUMENT_ZIP:
        process_recap_zip.delay(pq.pk)


def do_pacer_fetch(fq):
    """Process a request made by a user to get an item from PACER.

    :param fq: The PacerFetchQueue item to process
    :return: None
    """
    result = None
    if fq.request_type == REQUEST_TYPE.DOCKET:
        # Request by docket_id
        court_id = fq.court_id or getattr(fq.docket, "court_id", None)
        kwargs = {
            # Universal params
            "court_id": court_id,
            "user_pk": fq.user_id,
            "docket_pk": fq.docket_id,
            # Scraping params
            "doc_num_start": fq.de_number_start,
            "doc_num_end": fq.de_number_end,
            "date_start": fq.de_date_start,
            "date_end": fq.de_date_end,
            "show_parties_and_counsel": fq.show_parties_and_counsel,
            "show_terminated_parties": fq.show_terminated_parties,
            "show_list_of_member_cases": fq.show_list_of_member_cases,
        }
        if (fq.docket_id and not fq.docket.pacer_case_id) or fq.docket_number:
            # We lack the pacer_case_id either on the docket or from the
            # submission. Look it up.
            docket_number = fq.docket_number or getattr(
                fq.docket, "docket_number", None
            )
            c = chain(
                get_pacer_case_id_and_title.si(
                    pass_through=None,
                    docket_number=docket_number,
                    court_id=court_id,
                    user_pk=fq.user_id,
                ),
                get_docket_by_pacer_case_id.s(**kwargs),
            )
        else:
            if fq.docket_id is not None and fq.docket.pacer_case_id:
                # We have the docket and its pacer_case_id
                kwargs.update(
                    {
                        "data": {"pacer_case_id": fq.docket.pacer_case_id},
                        "court_id": fq.docket.court_id,
                    }
                )
            elif fq.pacer_case_id:
                # We lack the docket, but have a pacer_case_id
                kwargs.update(
                    {"data": {"pacer_case_id": fq.pacer_case_id},}
                )
            c = chain(get_docket_by_pacer_case_id.si(**kwargs))
        c |= add_or_update_recap_docket.s()
        c |= mark_fq_successful.si(fq.pk)
        result = c.apply_async()
    elif fq.request_type == REQUEST_TYPE.PDF:
        # Request by recap_document_id
        rd_pk = fq.recap_document_id
        result = chain(
            fetch_pacer_doc_by_rd.si(rd_pk, fq.pk),
            extract_recap_pdf.si(rd_pk),
            add_items_to_solr.si([rd_pk], "search.RECAPDocument"),
            mark_fq_successful.si(fq.pk),
        ).apply_async()
    elif fq.request_type == REQUEST_TYPE.ATTACHMENT_PAGE:
        result = fetch_attachment_page.apply_async(args=(fq.pk,))
    return result


def mark_pq_successful(pq, d_id=None, de_id=None, rd_id=None):
    """Mark the processing queue item as successfully completed.

    :param pq: The ProcessingQueue object to manipulate
    :param d_id: The docket PK to associate with this upload. Either the docket
    that the RECAPDocument is associated with, or the docket that was uploaded.
    :param de_id: The docket entry to associate with this upload. Only applies
    to document uploads, which are associated with docket entries.
    :param rd_id: The RECAPDocument PK to associate with this upload. Only
    applies to document uploads (obviously).
    """
    # Ditch the original file
    pq.filepath_local.delete(save=False)
    if pq.debug:
        pq.error_message = "Successful debugging upload! Nice work."
    else:
        pq.error_message = "Successful upload! Nice work."
    pq.status = PROCESSING_STATUS.SUCCESSFUL
    pq.docket_id = d_id
    pq.docket_entry_id = de_id
    pq.recap_document_id = rd_id
    pq.save()
    return pq.status, pq.error_message


def mark_pq_status(pq, msg, status):
    """Mark the processing queue item as some process, and log the message.

    :param pq: The ProcessingQueue object to manipulate
    :param msg: The message to log and to save to pq's error_message field.
    :param status: A pq status code as defined on the ProcessingQueue model.
    """
    if msg:
        logger.info(msg)
    pq.error_message = msg
    pq.status = status
    pq.save()
    return pq.status, pq.error_message


@app.task(
    bind=True, max_retries=2, interval_start=5 * 60, interval_step=10 * 60
)
def process_recap_pdf(self, pk):
    """Process an uploaded PDF from the RECAP API endpoint.

    :param pk: The PK of the processing queue item you want to work on.
    :return: A RECAPDocument object that was created or updated.
    """
    """Save a RECAP PDF to the database."""
    pq = ProcessingQueue.objects.get(pk=pk)
    mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)

    if pq.attachment_number is None:
        document_type = RECAPDocument.PACER_DOCUMENT
    else:
        document_type = RECAPDocument.ATTACHMENT

    logger.info("Processing RECAP item (debug is: %s): %s " % (pq.debug, pq))
    try:
        if pq.pacer_case_id:
            rd = RECAPDocument.objects.get(
                docket_entry__docket__pacer_case_id=pq.pacer_case_id,
                pacer_doc_id=pq.pacer_doc_id,
            )
        else:
            # Sometimes we don't have the case ID from PACER. Try to make this
            # work anyway.
            rd = RECAPDocument.objects.get(pacer_doc_id=pq.pacer_doc_id,)
    except (RECAPDocument.DoesNotExist, RECAPDocument.MultipleObjectsReturned):
        try:
            d = Docket.objects.get(
                pacer_case_id=pq.pacer_case_id, court_id=pq.court_id
            )
        except Docket.DoesNotExist as exc:
            # No Docket and no RECAPDocument. Do a retry. Hopefully
            # the docket will be in place soon (it could be in a
            # different upload task that hasn't yet been processed).
            logger.warning(
                "Unable to find docket for processing queue '%s'. "
                "Retrying if max_retries is not exceeded." % pq
            )
            error_message = "Unable to find docket for item."
            if (self.request.retries == self.max_retries) or pq.debug:
                mark_pq_status(pq, error_message, PROCESSING_STATUS.FAILED)
                return None
            else:
                mark_pq_status(
                    pq, error_message, PROCESSING_STATUS.QUEUED_FOR_RETRY
                )
                raise self.retry(exc=exc)
        except Docket.MultipleObjectsReturned:
            msg = "Too many dockets found when trying to save '%s'" % pq
            mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
            return None

        # Got the Docket, attempt to get/create the DocketEntry, and then
        # create the RECAPDocument
        try:
            de = DocketEntry.objects.get(
                docket=d, entry_number=pq.document_number
            )
        except DocketEntry.DoesNotExist as exc:
            logger.warning(
                "Unable to find docket entry for processing "
                "queue '%s'. Retrying if max_retries is not "
                "exceeded." % pq
            )
            pq.error_message = "Unable to find docket entry for item."
            if (self.request.retries == self.max_retries) or pq.debug:
                pq.status = PROCESSING_STATUS.FAILED
                pq.save()
                return None
            else:
                pq.status = PROCESSING_STATUS.QUEUED_FOR_RETRY
                pq.save()
                raise self.retry(exc=exc)
        else:
            # If we're here, we've got the docket and docket
            # entry, but were unable to find the document by
            # pacer_doc_id. This happens when pacer_doc_id is
            # missing, for example. ∴, try to get the document
            # from the docket entry.
            try:
                rd = RECAPDocument.objects.get(
                    docket_entry=de,
                    document_number=pq.document_number,
                    attachment_number=pq.attachment_number,
                    document_type=document_type,
                )
            except (
                RECAPDocument.DoesNotExist,
                RECAPDocument.MultipleObjectsReturned,
            ):
                # Unable to find it. Make a new item.
                rd = RECAPDocument(
                    docket_entry=de,
                    pacer_doc_id=pq.pacer_doc_id,
                    date_upload=now(),
                    document_type=document_type,
                )

    rd.document_number = pq.document_number
    rd.attachment_number = pq.attachment_number

    # Do the file, finally.
    content = pq.filepath_local.read()
    new_sha1 = sha1(content)
    existing_document = all(
        [
            rd.sha1 == new_sha1,
            rd.is_available,
            rd.filepath_local and os.path.isfile(rd.filepath_local.path),
        ]
    )
    if not existing_document:
        # Different sha1, it wasn't available, or it's missing from disk. Move
        # the new file over from the processing queue storage.
        cf = ContentFile(content)
        file_name = get_document_filename(
            rd.docket_entry.docket.court_id,
            rd.docket_entry.docket.pacer_case_id,
            rd.document_number,
            rd.attachment_number,
        )
        if not pq.debug:
            rd.filepath_local.save(file_name, cf, save=False)

            # Do page count and extraction
            extension = rd.filepath_local.path.split(".")[-1]
            rd.page_count = get_page_count(rd.filepath_local.path, extension)
            rd.file_size = rd.filepath_local.size

        rd.ocr_status = None
        rd.is_available = True
        rd.sha1 = new_sha1

    if not pq.debug:
        try:
            rd.save()
        except (IntegrityError, ValidationError):
            msg = "Duplicate key on unique_together constraint"
            mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
            rd.filepath_local.delete(save=False)
            return None

    if not existing_document and not pq.debug:
        extract_recap_pdf(rd.pk)
        add_items_to_solr([rd.pk], "search.RECAPDocument")

    mark_pq_successful(
        pq,
        d_id=rd.docket_entry.docket_id,
        de_id=rd.docket_entry_id,
        rd_id=rd.pk,
    )
    mark_ia_upload_needed(rd.docket_entry.docket, save_docket=True)
    return rd


@app.task(bind=True, max_retries=5, ignore_result=True)
def process_recap_zip(self, pk):
    """Process a zip uploaded from a PACER district court

    The general process is to use our existing infrastructure. We open the zip,
    identify the documents inside, and then associate them with the rest of our
    collection.

    :param self: A celery task object
    :param pk: The PK of the ProcessingQueue object to process
    :return: A list of new PQ's that were created, one per PDF that was
    enqueued.
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)

    logger.info("Processing RECAP zip (debug is: %s): %s", pq.debug, pq)
    with ZipFile(pq.filepath_local.path, "r") as archive:
        # Security: Check for zip bombs.
        max_file_size = convert_size_to_bytes("200MB")
        for zip_info in archive.infolist():
            if zip_info.file_size < max_file_size:
                continue
            mark_pq_status(
                pq,
                "Zip too large; possible zip bomb. File in zip named %s "
                "would be %s bytes expanded."
                % (zip_info.filename, zip_info.file_size),
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
            new_pq = ProcessingQueue.objects.create(
                court=pq.court,
                uploader=pq.uploader,
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
            tasks.append(process_recap_pdf.delay(new_pq.pk))

        # At the end, mark the pq as successful and return the PQ
        mark_pq_status(
            pq,
            "Successfully created ProcessingQueue objects: %s"
            % oxford_join(new_pqs),
            PROCESSING_STATUS.SUCCESSFUL,
        )

        # Returning the tasks allows tests to wait() for the PDFs to complete
        # before checking assertions.
        return {
            "new_pqs": new_pqs,
            "tasks": tasks,
        }


@app.task(bind=True, max_retries=5, ignore_result=True)
def process_recap_docket(self, pk):
    """Process an uploaded docket from the RECAP API endpoint.

    :param pk: The primary key of the processing queue item you want to work
    on.
    :returns: A dict of the form:

        {
            // The PK of the docket that's created or updated
            'docket_pk': 22,
            // A boolean indicating whether a new docket entry or
            // recap document was created (implying a Solr needs
            // updating).
            'content_updated': True,
        }

    This value is a dict so that it can be ingested in a Celery chain.

    """
    start_time = now()
    pq = ProcessingQueue.objects.get(pk=pk)
    mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s" % (pq.debug, pq))

    report = DocketReport(map_cl_to_pacer_id(pq.court_id))
    text = pq.filepath_local.read().decode("utf-8")

    if "History/Documents" in text:
        # Prior to 1.1.8, we did not separate docket history reports into their
        # own upload_type. Alas, we still have some old clients around, so we
        # need to handle those clients here.
        pq.upload_type = UPLOAD_TYPE.DOCKET_HISTORY_REPORT
        pq.save()
        process_recap_docket_history_report(pk)
        self.request.chain = None
        return None

    report._parse_text(text)
    data = report.data
    logger.info("Parsing completed of item %s" % pq)

    if data == {}:
        # Not really a docket. Some sort of invalid document (see Juriscraper).
        msg = "Not a valid docket upload."
        mark_pq_status(pq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        self.request.chain = None
        return None

    # Merge the contents of the docket into CL.
    d, docket_count = find_docket_object(
        pq.court_id, pq.pacer_case_id, data["docket_number"]
    )
    if docket_count > 1:
        logger.info(
            "Found %s dockets during lookup. Choosing oldest." % docket_count
        )
        d = d.earliest("date_created")

    d.add_recap_source()
    update_docket_metadata(d, data)
    if not d.pacer_case_id:
        d.pacer_case_id = pq.pacer_case_id

    if pq.debug:
        mark_pq_successful(pq, d_id=d.pk)
        self.request.chain = None
        return {"docket_pk": d.pk, "content_updated": False}

    d.save()

    # Add the HTML to the docket in case we need it someday.
    pacer_file = PacerHtmlFiles(
        content_object=d, upload_type=UPLOAD_TYPE.DOCKET
    )
    pacer_file.filepath.save(
        "docket.html",  # We only care about the ext w/UUIDFileSystemStorage
        ContentFile(text),
    )

    rds_created, content_updated = add_docket_entries(
        d, data["docket_entries"]
    )
    add_parties_and_attorneys(d, data["parties"])
    process_orphan_documents(rds_created, pq.court_id, d.date_filed)
    if content_updated and docket_count > 0:
        newly_enqueued = enqueue_docket_alert(d.pk)
        if newly_enqueued:
            send_docket_alert(d.pk, start_time)
    mark_pq_successful(pq, d_id=d.pk)
    return {
        "docket_pk": d.pk,
        "content_updated": bool(rds_created or content_updated),
    }


@app.task(
    bind=True, max_retries=3, interval_start=5 * 60, interval_step=5 * 60
)
def process_recap_attachment(self, pk, tag_names=None):
    """Process an uploaded attachment page from the RECAP API endpoint.

    :param pk: The primary key of the processing queue item you want to work on
    :param tag_names: A list of tag names to add to all items created or
    modified in this function.
    :return: Tuple indicating the status of the processing and a related
    message
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s" % (pq.debug, pq))

    with open(pq.filepath_local.path) as f:
        text = f.read().decode("utf-8")
    att_data = get_data_from_att_report(text, pq.court_id)
    logger.info("Parsing completed for item %s" % pq)

    if att_data == {}:
        # Bad attachment page.
        msg = "Not a valid attachment page upload."
        self.request.chain = None
        return mark_pq_status(pq, msg, PROCESSING_STATUS.INVALID_CONTENT)

    if pq.pacer_case_id in ["undefined", "null"]:
        # Bad data from the client. Fix it with parsed data.
        pq.pacer_case_id = att_data.get("pacer_case_id")
        pq.save()

    try:
        rds_affected, de = merge_attachment_page_data(
            pq.court,
            pq.pacer_case_id,
            att_data["pacer_doc_id"],
            att_data["document_number"],
            text,
            att_data["attachments"],
            pq.debug,
        )
    except RECAPDocument.MultipleObjectsReturned:
        msg = (
            "Too many documents found when attempting to associate "
            "attachment data"
        )
        return mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
    except RECAPDocument.DoesNotExist as exc:
        msg = "Could not find docket to associate with attachment metadata"
        if (self.request.retries == self.max_retries) or pq.debug:
            return mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
        else:
            mark_pq_status(pq, msg, PROCESSING_STATUS.QUEUED_FOR_RETRY)
            raise self.retry(exc=exc)

    add_tags_to_objs(tag_names, rds_affected)
    return mark_pq_successful(pq, d_id=de.docket_id, de_id=de.pk)


@app.task(
    bind=True, max_retries=3, interval_start=5 * 60, interval_step=5 * 60
)
def process_recap_claims_register(self, pk):
    """Merge bankruptcy claims registry HTML into RECAP

    :param pk: The primary key of the processing queue item you want to work on
    :type pk: int
    :return: None
    :rtype: None
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    if pq.debug:
        # Proper debugging not supported on this endpoint. Just abort.
        mark_pq_successful(pq)
        self.request.chain = None
        return None

    mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s" % (pq.debug, pq))

    with open(pq.filepath_local.path) as f:
        text = f.read().decode("utf-8")
    report = ClaimsRegister(map_cl_to_pacer_id(pq.court_id))
    report._parse_text(text)
    data = report.data
    logger.info("Parsing completed for item %s" % pq)

    if not data:
        # Bad HTML
        msg = "Not a valid claims registry page or other parsing failure"
        mark_pq_status(pq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        self.request.chain = None
        return None

    # Merge the contents of the docket into CL.
    d, docket_count = find_docket_object(
        pq.court_id, pq.pacer_case_id, data["docket_number"]
    )
    if docket_count > 1:
        logger.info(
            "Found %s dockets during lookup. Choosing oldest." % docket_count
        )
        d = d.earliest("date_created")

    # Merge the contents into CL
    d.add_recap_source()
    update_docket_metadata(d, data)

    try:
        d.save()
    except IntegrityError as exc:
        logger.warning(
            "Race condition experienced while attempting docket save."
        )
        error_message = "Unable to save docket due to IntegrityError."
        if self.request.retries == self.max_retries:
            mark_pq_status(pq, error_message, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return None
        else:
            mark_pq_status(
                pq, error_message, PROCESSING_STATUS.QUEUED_FOR_RETRY
            )
            raise self.retry(exc=exc)

    add_bankruptcy_data_to_docket(d, data)
    add_claims_to_docket(d, data["claims"])
    logger.info("Created/updated claims data for %s", pq)

    # Add the HTML to the docket in case we need it someday.
    pacer_file = PacerHtmlFiles(
        content_object=d, upload_type=UPLOAD_TYPE.CLAIMS_REGISTER
    )
    pacer_file.filepath.save(
        # We only care about the ext w/UUIDFileSystemStorage
        "claims_registry.html",
        ContentFile(text),
    )

    mark_pq_successful(pq, d_id=d.pk)
    return {"docket_pk": d.pk}


@app.task(
    bind=True, max_retries=3, interval_start=5 * 60, interval_step=5 * 60
)
def process_recap_docket_history_report(self, pk):
    """Process the docket history report.

    :param pk: The primary key of the processing queue item you want to work on
    :returns: A dict indicating whether the docket needs Solr re-indexing.
    """
    start_time = now()
    pq = ProcessingQueue.objects.get(pk=pk)
    mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s" % (pq.debug, pq))

    with open(pq.filepath_local.path) as f:
        text = f.read().decode("utf-8")
    report = DocketHistoryReport(map_cl_to_pacer_id(pq.court_id))
    report._parse_text(text)
    data = report.data
    logger.info("Parsing completed for item %s" % pq)

    if data == {}:
        # Bad docket history page.
        msg = "Not a valid docket history page upload."
        mark_pq_status(pq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        self.request.chain = None
        return None

    # Merge the contents of the docket into CL.
    d, docket_count = find_docket_object(
        pq.court_id, pq.pacer_case_id, data["docket_number"]
    )
    if docket_count > 1:
        logger.info(
            "Found %s dockets during lookup. Choosing oldest." % docket_count
        )
        d = d.earliest("date_created")

    d.add_recap_source()
    update_docket_metadata(d, data)

    if pq.debug:
        mark_pq_successful(pq, d_id=d.pk)
        self.request.chain = None
        return {"docket_pk": d.pk, "content_updated": False}

    try:
        d.save()
    except IntegrityError as exc:
        logger.warning(
            "Race condition experienced while attempting docket save."
        )
        error_message = "Unable to save docket due to IntegrityError."
        if self.request.retries == self.max_retries:
            mark_pq_status(pq, error_message, PROCESSING_STATUS.FAILED)
            self.request.chain = None
            return None
        else:
            mark_pq_status(
                pq, error_message, PROCESSING_STATUS.QUEUED_FOR_RETRY
            )
            raise self.retry(exc=exc)

    # Add the HTML to the docket in case we need it someday.
    pacer_file = PacerHtmlFiles(
        content_object=d, upload_type=UPLOAD_TYPE.DOCKET_HISTORY_REPORT
    )
    pacer_file.filepath.save(
        # We only care about the ext w/UUIDFileSystemStorage
        "docket_history.html",
        ContentFile(text),
    )

    rds_created, content_updated = add_docket_entries(
        d, data["docket_entries"]
    )
    process_orphan_documents(rds_created, pq.court_id, d.date_filed)
    if content_updated and docket_count > 0:
        newly_enqueued = enqueue_docket_alert(d.pk)
        if newly_enqueued:
            send_docket_alert(d.pk, start_time)
    mark_pq_successful(pq, d_id=d.pk)
    return {
        "docket_pk": d.pk,
        "content_updated": bool(rds_created or content_updated),
    }


@app.task(bind=True, max_retries=3, ignore_result=True)
def process_recap_appellate_docket(self, pk):
    """Process an uploaded appellate docket from the RECAP API endpoint.

    :param pk: The primary key of the processing queue item you want to work
    on.
    :returns: A dict of the form:

        {
            // The PK of the docket that's created or updated
            'docket_pk': 22,
            // A boolean indicating whether a new docket entry or
            // recap document was created (implying a Solr needs
            // updating).
            'content_updated': True,
        }

    This value is a dict so that it can be ingested in a Celery chain.

    """
    start_time = now()
    pq = ProcessingQueue.objects.get(pk=pk)
    mark_pq_status(pq, "", PROCESSING_STATUS.IN_PROGRESS)
    logger.info(
        "Processing Appellate RECAP item"
        " (debug is: %s): %s" % (pq.debug, pq)
    )

    report = AppellateDocketReport(map_cl_to_pacer_id(pq.court_id))
    text = pq.filepath_local.read().decode("utf-8")

    report._parse_text(text)
    data = report.data
    logger.info("Parsing completed of item %s" % pq)

    if data == {}:
        # Not really a docket. Some sort of invalid document (see Juriscraper).
        msg = "Not a valid docket upload."
        mark_pq_status(pq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        self.request.chain = None
        return None

    # Merge the contents of the docket into CL.
    d, docket_count = find_docket_object(
        pq.court_id, pq.pacer_case_id, data["docket_number"]
    )
    if docket_count > 1:
        logger.info(
            "Found %s dockets during lookup. Choosing oldest." % docket_count
        )
        d = d.earliest("date_created")

    d.add_recap_source()
    update_docket_metadata(d, data)
    d, og_info = update_docket_appellate_metadata(d, data)
    if not d.pacer_case_id:
        d.pacer_case_id = pq.pacer_case_id

    if pq.debug:
        mark_pq_successful(pq, d_id=d.pk)
        self.request.chain = None
        return {"docket_pk": d.pk, "content_updated": False}

    if og_info is not None:
        og_info.save()
        d.originating_court_information = og_info
    d.save()

    # Add the HTML to the docket in case we need it someday.
    pacer_file = PacerHtmlFiles(
        content_object=d, upload_type=UPLOAD_TYPE.APPELLATE_DOCKET
    )
    pacer_file.filepath.save(
        "docket.html",  # We only care about the ext w/UUIDFileSystemStorage
        ContentFile(text),
    )

    rds_created, content_updated = add_docket_entries(
        d, data["docket_entries"]
    )
    add_parties_and_attorneys(d, data["parties"])
    process_orphan_documents(rds_created, pq.court_id, d.date_filed)
    if content_updated and docket_count > 0:
        newly_enqueued = enqueue_docket_alert(d.pk)
        if newly_enqueued:
            send_docket_alert(d.pk, start_time)
    mark_pq_successful(pq, d_id=d.pk)
    return {
        "docket_pk": d.pk,
        "content_updated": bool(rds_created or content_updated),
    }


@app.task(
    bind=True, max_retries=3, interval_start=5 * 60, interval_step=5 * 60
)
def process_recap_appellate_attachment(self, pk):
    """Process the appellate attachment pages.

    For now, this is a stub until we can get the parser working properly in
    Juriscraper.
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    msg = "Appellate attachment pages not yet supported. Coming soon."
    mark_pq_status(pq, msg, PROCESSING_STATUS.FAILED)
    return None


@app.task
def create_new_docket_from_idb(idb_pk):
    """Create a new docket for the IDB item found. Populate it with all
    applicable fields.

    :param idb_pk: An FjcIntegratedDatabase object pk with which to create a
    Docket.
    :return Docket: The created Docket object.
    """
    idb_row = FjcIntegratedDatabase.objects.get(pk=idb_pk)
    case_name = idb_row.plaintiff + " v. " + idb_row.defendant
    d = Docket.objects.create(
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
    d.save()
    logger.info("Created docket %s for IDB row: %s", d.pk, idb_row)
    return d.pk


@app.task
def merge_docket_with_idb(d_pk, idb_pk):
    """Merge an existing docket with an idb_row.

    :param d_pk: A Docket object pk to update.
    :param idb_pk: A FjcIntegratedDatabase object pk to use as a source for
    updates.
    :return None
    """
    d = Docket.objects.get(pk=d_pk)
    idb_row = FjcIntegratedDatabase.objects.get(pk=idb_pk)
    d.add_idb_source()
    d.idb_data = idb_row
    d.date_filed = d.date_filed or idb_row.date_filed
    d.date_terminated = d.date_terminated or idb_row.date_terminated
    d.nature_of_suit = d.nature_of_suit or idb_row.get_nature_of_suit_display()
    d.jurisdiction_type = (
        d.jurisdiction_type or idb_row.get_jurisdiction_display()
    )
    d.save()


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


@app.task(
    bind=True,
    max_retries=3,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
@transaction.atomic
def fetch_pacer_doc_by_rd(self, rd_pk, fq_pk):
    """Fetch a PACER PDF by rd_pk

    This is very similar to get_pacer_doc_by_rd, except that it manages
    status as it proceeds and it gets the cookie info from redis.

    :param rd_pk: The PK of the RECAP Document to get.
    :param fq_pk: The PK of the RECAP Fetch Queue to update.
    :return: The RECAPDocument PK
    """
    rd = RECAPDocument.objects.get(pk=rd_pk)
    fq = PacerFetchQueue.objects.get(pk=fq_pk)
    fq.status = PROCESSING_STATUS.IN_PROGRESS
    fq.save()

    if rd.is_available:
        fq.status = PROCESSING_STATUS.SUCCESSFUL
        fq.message = "PDF already marked as 'is_available'. Doing nothing."
        fq.save()
        self.request.chain = None
        return

    cookies = get_pacer_cookie_from_cache(fq.user_id)
    if not cookies:
        fq.status = PROCESSING_STATUS.FAILED
        fq.message = "Unable to find cached cookies. Aborting request."
        fq.save()
        self.request.chain = None
        return

    pacer_case_id = rd.docket_entry.docket.pacer_case_id
    try:
        r = download_pacer_pdf_by_rd(
            rd.pk, pacer_case_id, rd.pacer_doc_id, cookies
        )
    except (requests.RequestException, HTTPError):
        fq.status = PROCESSING_STATUS.FAILED
        fq.message = "Failed to get PDF from network."
        fq.save()
        self.request.chain = None
        return

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
        fq.status = PROCESSING_STATUS.FAILED
        fq.message = msg
        fq.save()
        self.request.chain = None
        return

    return rd.pk


@app.task(
    bind=True,
    max_retries=3,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
@transaction.atomic
def fetch_attachment_page(self, fq_pk):
    """Fetch a PACER attachment page by rd_pk

    This is very similar to process_recap_attachment, except that it manages
    status as it proceeds and it gets the cookie info from redis.

    :param fq_pk: The PK of the RECAP Fetch Queue to update.
    :return: None
    """
    fq = PacerFetchQueue.objects.get(pk=fq_pk)
    fq.status = PROCESSING_STATUS.IN_PROGRESS
    fq.save()

    rd = fq.recap_document
    if not rd.pacer_doc_id:
        msg = (
            "Unable to get attachment page: Unknown pacer_doc_id for "
            "RECAP Document object %s" % rd.pk
        )
        mark_fq_status(fq, msg, PROCESSING_STATUS.NEEDS_INFO)
        return

    cookies = get_pacer_cookie_from_cache(fq.user_id)
    if not cookies:
        msg = "Unable to find cached cookies. Aborting request."
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        return

    try:
        r = get_attachment_page_by_rd(rd.pk, cookies)
    except (requests.RequestException, HTTPError):
        msg = "Failed to get attachment page from network."
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        return

    text = r.response.text
    att_data = get_data_from_att_report(text, rd.docket_entry.docket.court_id,)

    if att_data == {}:
        msg = "Not a valid attachment page upload"
        mark_fq_status(fq, msg, PROCESSING_STATUS.INVALID_CONTENT)
        return

    try:
        merge_attachment_page_data(
            rd.docket_entry.docket.court,
            rd.docket_entry.docket.pacer_case_id,
            att_data["pacer_doc_id"],
            att_data["document_number"],
            text,
            att_data["attachments"],
        )
    except RECAPDocument.MultipleObjectsReturned:
        msg = (
            "Too many documents found when attempting to associate "
            "attachment data"
        )
        mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
        return
    except RECAPDocument.DoesNotExist as exc:
        msg = "Could not find docket to associate with attachment metadata"
        if self.request.retries == self.max_retries:
            mark_fq_status(fq, msg, PROCESSING_STATUS.FAILED)
            return
        else:
            mark_fq_status(fq, msg, PROCESSING_STATUS.QUEUED_FOR_RETRY)
            raise self.retry(exc=exc)
    msg = "Successfully completed fetch and save."
    mark_fq_status(fq, msg, PROCESSING_STATUS.SUCCESSFUL)


@app.task
def mark_fq_successful(fq_pk):
    fq = PacerFetchQueue.objects.get(pk=fq_pk)
    fq.status = PROCESSING_STATUS.SUCCESSFUL
    fq.date_completed = now()
    fq.message = "Successfully completed fetch and save."
    fq.save()


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
