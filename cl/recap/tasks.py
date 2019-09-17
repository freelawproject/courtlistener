# coding=utf-8
import logging
import os

from celery.canvas import chain
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.utils.timezone import now
from juriscraper.lib.string_utils import CaseNameTweaker
from juriscraper.pacer import AppellateDocketReport, AttachmentPage, \
    DocketHistoryReport, DocketReport

from cl.alerts.tasks import enqueue_docket_alert, send_docket_alert
from cl.celery import app
from cl.corpus_importer.utils import mark_ia_upload_needed
from cl.lib.crypto import sha1
from cl.lib.filesizes import convert_size_to_bytes
from cl.lib.model_helpers import make_docket_number_core
from cl.lib.pacer import map_cl_to_pacer_id
from cl.lib.recap_utils import get_document_filename
from cl.recap.mergers import add_docket_entries, add_parties_and_attorneys, \
    update_docket_appellate_metadata, update_docket_metadata, \
    process_orphan_documents
from cl.recap.models import PacerHtmlFiles, ProcessingQueue, UPLOAD_TYPE, \
    FjcIntegratedDatabase
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
        chain(process_recap_docket.s(pq.pk),
              add_or_update_recap_docket.s()).apply_async()
    elif pq.upload_type == UPLOAD_TYPE.ATTACHMENT_PAGE:
        process_recap_attachment.delay(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.PDF:
        process_recap_pdf.delay(pq.pk)
    elif pq.upload_type == UPLOAD_TYPE.DOCKET_HISTORY_REPORT:
        chain(process_recap_docket_history_report.s(pq.pk),
              add_or_update_recap_docket.s()).apply_async()
    elif pq.upload_type == UPLOAD_TYPE.APPELLATE_DOCKET:
        chain(process_recap_appellate_docket.s(pq.pk),
              add_or_update_recap_docket.s()).apply_async()
    elif pq.upload_type == UPLOAD_TYPE.APPELLATE_ATTACHMENT_PAGE:
        process_recap_appellate_attachment.delay(pq.pk)


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
        pq.error_message = 'Successful debugging upload! Nice work.'
    else:
        pq.error_message = 'Successful upload! Nice work.'
    pq.status = pq.PROCESSING_SUCCESSFUL
    pq.docket_id = d_id
    pq.docket_entry_id = de_id
    pq.recap_document_id = rd_id
    pq.save()


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


@app.task(bind=True, max_retries=2, interval_start=5 * 60,
          interval_step=10 * 60)
def process_recap_pdf(self, pk):
    """Process an uploaded PDF from the RECAP API endpoint.

    :param pk: The PK of the processing queue item you want to work on.
    :return: A RECAPDocument object that was created or updated.
    """
    """Save a RECAP PDF to the database."""
    pq = ProcessingQueue.objects.get(pk=pk)
    mark_pq_status(pq, '', pq.PROCESSING_IN_PROGRESS)

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
            rd = RECAPDocument.objects.get(
                pacer_doc_id=pq.pacer_doc_id,
            )
    except (RECAPDocument.DoesNotExist, RECAPDocument.MultipleObjectsReturned):
        try:
            d = Docket.objects.get(pacer_case_id=pq.pacer_case_id,
                                   court_id=pq.court_id)
        except Docket.DoesNotExist as exc:
            # No Docket and no RECAPDocument. Do a retry. Hopefully
            # the docket will be in place soon (it could be in a
            # different upload task that hasn't yet been processed).
            logger.warning("Unable to find docket for processing queue '%s'. "
                           "Retrying if max_retries is not exceeded." % pq)
            error_message = "Unable to find docket for item."
            if (self.request.retries == self.max_retries) or pq.debug:
                mark_pq_status(pq, error_message, pq.PROCESSING_FAILED)
                return None
            else:
                mark_pq_status(pq, error_message, pq.QUEUED_FOR_RETRY)
                raise self.retry(exc=exc)
        except Docket.MultipleObjectsReturned:
            msg = "Too many dockets found when trying to save '%s'" % pq
            mark_pq_status(pq, msg, pq.PROCESSING_FAILED)
            return None
        else:
            # Got the Docket, attempt to get/create the DocketEntry, and then
            # create the RECAPDocument
            try:
                de = DocketEntry.objects.get(docket=d,
                                             entry_number=pq.document_number)
            except DocketEntry.DoesNotExist as exc:
                logger.warning("Unable to find docket entry for processing "
                               "queue '%s'. Retrying if max_retries is not "
                               "exceeded." % pq)
                pq.error_message = "Unable to find docket entry for item."
                if (self.request.retries == self.max_retries) or pq.debug:
                    pq.status = pq.PROCESSING_FAILED
                    pq.save()
                    return None
                else:
                    pq.status = pq.QUEUED_FOR_RETRY
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
                except (RECAPDocument.DoesNotExist,
                        RECAPDocument.MultipleObjectsReturned):
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
    existing_document = all([
        rd.sha1 == new_sha1,
        rd.is_available,
        rd.filepath_local and os.path.isfile(rd.filepath_local.path)
    ])
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
            extension = rd.filepath_local.path.split('.')[-1]
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
            mark_pq_status(pq, msg, pq.PROCESSING_FAILED)
            rd.filepath_local.delete(save=False)
            return None

    if not existing_document and not pq.debug:
        extract_recap_pdf(rd.pk)
        add_items_to_solr([rd.pk], 'search.RECAPDocument')

    mark_pq_successful(pq, d_id=rd.docket_entry.docket_id,
                       de_id=rd.docket_entry_id, rd_id=rd.pk)
    changed = mark_ia_upload_needed(rd.docket_entry.docket)
    if changed:
        rd.docket_entry.docket.save()
    return rd


def find_docket_object(court_id, pacer_case_id, docket_number):
    """Attempt to find the docket based on the parsed docket data. If cannot be
    found, create a new docket. If multiple are found, return all of them.

    :param court_id: The CourtListener court_id to lookup
    :param pacer_case_id: The PACER case ID for the docket
    :param docket_number: The docket number to lookup.
    :returns a tuple. The first item is either a QuerySet of all the items
    found if more than one is identified or just the docket found if only one
    is identified. The second item in the tuple is the count of items found
    (this number is zero if we had to create a new docket item).
    """
    # Attempt several lookups of decreasing specificity. Note that
    # pacer_case_id is required for Docket and Docket History uploads.
    d = None
    docket_number_core = make_docket_number_core(docket_number)
    for kwargs in [{'pacer_case_id': pacer_case_id,
                    'docket_number_core': docket_number_core},
                   {'pacer_case_id': pacer_case_id},
                   {'pacer_case_id': None,
                    'docket_number_core': docket_number_core}]:
        ds = Docket.objects.filter(court_id=court_id, **kwargs)
        count = ds.count()
        if count == 0:
            continue  # Try a looser lookup.
        if count == 1:
            d = ds[0]
            break  # Nailed it!
        elif count > 1:
            return ds, count  # Problems. Let caller decide what to do.

    if d is None:
        # Couldn't find a docket. Make a new one.
        d = Docket(
            source=Docket.RECAP,
            pacer_case_id=pacer_case_id,
            court_id=court_id,
        )
        return d, 0

    return d, 1


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
    mark_pq_status(pq, '', pq.PROCESSING_IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s" % (pq.debug, pq))

    report = DocketReport(map_cl_to_pacer_id(pq.court_id))
    text = pq.filepath_local.read().decode('utf-8')

    if 'History/Documents' in text:
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
        mark_pq_status(pq, msg, pq.INVALID_CONTENT)
        self.request.chain = None
        return None

    # Merge the contents of the docket into CL.
    d, docket_count = find_docket_object(pq.court_id, pq.pacer_case_id,
                                         data['docket_number'])
    if docket_count > 1:
        logger.info("Found %s dockets during lookup. Choosing oldest." %
                    docket_count)
        d = d.earliest('date_created')

    d.add_recap_source()
    update_docket_metadata(d, data)
    if not d.pacer_case_id:
        d.pacer_case_id = pq.pacer_case_id

    if pq.debug:
        mark_pq_successful(pq, d_id=d.pk)
        self.request.chain = None
        return {'docket_pk': d.pk, 'content_updated': False}

    d.save()

    # Add the HTML to the docket in case we need it someday.
    pacer_file = PacerHtmlFiles(content_object=d,
                                upload_type=UPLOAD_TYPE.DOCKET)
    pacer_file.filepath.save(
        'docket.html',  # We only care about the ext w/UUIDFileSystemStorage
        ContentFile(text),
    )

    rds_created, content_updated = add_docket_entries(
        d, data['docket_entries'])
    add_parties_and_attorneys(d, data['parties'])
    process_orphan_documents(rds_created, pq.court_id, d.date_filed)
    if content_updated and docket_count > 0:
        newly_enqueued = enqueue_docket_alert(d.pk)
        if newly_enqueued:
            send_docket_alert(d.pk, start_time)
    mark_pq_successful(pq, d_id=d.pk)
    return {
        'docket_pk': d.pk,
        'content_updated': bool(rds_created or content_updated),
    }


@app.task(bind=True, max_retries=3, interval_start=5 * 60,
          interval_step=5 * 60)
def process_recap_attachment(self, pk, tag_names=None):
    """Process an uploaded attachment page from the RECAP API endpoint.

    :param pk: The primary key of the processing queue item you want to work on
    :param tag_names: A list of tag names to add to all items created or
    modified in this function.
    :return: None
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    mark_pq_status(pq, '', pq.PROCESSING_IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s" % (pq.debug, pq))

    att_page = AttachmentPage(map_cl_to_pacer_id(pq.court_id))
    with open(pq.filepath_local.path) as f:
        text = f.read().decode('utf-8')
    att_page._parse_text(text)
    att_data = att_page.data
    logger.info("Parsing completed for item %s" % pq)

    if att_data == {}:
        # Bad attachment page.
        msg = "Not a valid attachment page upload."
        mark_pq_status(pq, msg, pq.INVALID_CONTENT)
        self.request.chain = None
        return None

    if pq.pacer_case_id in ['undefined', 'null']:
        # Bad data from the client. Fix it with parsed data.
        pq.pacer_case_id = att_data.get('pacer_case_id')
        pq.save()

    # Merge the contents of the data into CL.
    try:
        params = {
            'pacer_doc_id': att_data['pacer_doc_id'],
            'docket_entry__docket__court': pq.court,
        }
        if pq.pacer_case_id:
            params['docket_entry__docket__pacer_case_id'] = pq.pacer_case_id
        main_rd = RECAPDocument.objects.get(**params)
    except RECAPDocument.MultipleObjectsReturned:
        # Unclear how to proceed and we don't want to associate this data with
        # the wrong case. We must punt.
        msg = "Too many documents found when attempting to associate " \
              "attachment data"
        mark_pq_status(pq, msg, pq.PROCESSING_FAILED)
        return None
    except RECAPDocument.DoesNotExist as exc:
        msg = "Could not find docket to associate with attachment metadata"
        if (self.request.retries == self.max_retries) or pq.debug:
            mark_pq_status(pq, msg, pq.PROCESSING_FAILED)
            return None
        else:
            mark_pq_status(pq, msg, pq.QUEUED_FOR_RETRY)
            raise self.retry(exc=exc)

    # We got the right item. Update/create all the attachments for
    # the docket entry.
    de = main_rd.docket_entry
    if att_data['document_number'] is None:
        # Bankruptcy attachment page. Use the document number from the Main doc
        att_data['document_number'] = main_rd.document_number

    rds_created = []
    if not pq.debug:
        # Save the old HTML to the docket entry.
        pacer_file = PacerHtmlFiles(content_object=de,
                                    upload_type=UPLOAD_TYPE.ATTACHMENT_PAGE)
        pacer_file.filepath.save(
            'attachment_page.html',  # Irrelevant b/c UUIDFileSystemStorage
            ContentFile(text),
        )

        # Create/update the attachment items.
        tags = []
        if tag_names:
            for tag_name in tag_names:
                tag, _ = Tag.objects.get_or_create(name=tag_name)
                tags.append(tag)
        for attachment in att_data['attachments']:
            if all([attachment['attachment_number'],
                    # Missing on sealed items.
                    attachment.get('pacer_doc_id', False),
                    # Missing on some restricted docs (see Juriscraper)
                    attachment['page_count'] is not None,
                    attachment['description']]):
                rd, created = RECAPDocument.objects.update_or_create(
                    docket_entry=de,
                    document_number=att_data['document_number'],
                    attachment_number=attachment['attachment_number'],
                    document_type=RECAPDocument.ATTACHMENT,
                )
                if created:
                    rds_created.append(rd)
                needs_save = False
                for field in ['description', 'pacer_doc_id']:
                    if attachment[field]:
                        setattr(rd, field, attachment[field])
                        needs_save = True

                # Only set page_count and file_size if they're blank, in case
                # we got the real value by measuring.
                if rd.page_count is None:
                    rd.page_count = attachment['page_count']
                if rd.file_size is None and attachment['file_size_str']:
                    try:
                        rd.file_size = convert_size_to_bytes(
                            attachment['file_size_str'])
                    except ValueError:
                        pass

                if needs_save:
                    rd.save()
                if tags:
                    for tag in tags:
                        tag.tag_object(rd)

                # Do *not* do this async — that can cause race conditions.
                add_items_to_solr([rd.pk], 'search.RECAPDocument')

    mark_pq_successful(pq, d_id=de.docket_id, de_id=de.pk)
    process_orphan_documents(rds_created, pq.court_id,
                             main_rd.docket_entry.docket.date_filed)
    changed = mark_ia_upload_needed(de.docket)
    if changed:
        de.docket.save()


@app.task(bind=True, max_retries=3, interval_start=5 * 60,
          interval_step=5 * 60)
def process_recap_docket_history_report(self, pk):
    """Process the docket history report.

    :param pk: The primary key of the processing queue item you want to work on
    :returns: A dict indicating whether the docket needs Solr re-indexing.
    """
    start_time = now()
    pq = ProcessingQueue.objects.get(pk=pk)
    mark_pq_status(pq, '', pq.PROCESSING_IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s" % (pq.debug, pq))

    report = DocketHistoryReport(map_cl_to_pacer_id(pq.court_id))
    with open(pq.filepath_local.path) as f:
        text = f.read().decode('utf-8')
    report._parse_text(text)
    data = report.data
    logger.info("Parsing completed for item %s" % pq)

    if data == {}:
        # Bad docket history page.
        msg = "Not a valid docket history page upload."
        mark_pq_status(pq, msg, pq.INVALID_CONTENT)
        self.request.chain = None
        return None

    # Merge the contents of the docket into CL.
    d, docket_count = find_docket_object(pq.court_id, pq.pacer_case_id,
                                         data['docket_number'])
    if docket_count > 1:
        logger.info("Found %s dockets during lookup. Choosing oldest." %
                    docket_count)
        d = d.earliest('date_created')

    d.add_recap_source()
    update_docket_metadata(d, data)

    if pq.debug:
        mark_pq_successful(pq, d_id=d.pk)
        self.request.chain = None
        return {'docket_pk': d.pk, 'content_updated': False}

    try:
        d.save()
    except IntegrityError as exc:
        logger.warning("Race condition experienced while attempting docket "
                       "save.")
        error_message = "Unable to save docket due to IntegrityError."
        if self.request.retries == self.max_retries:
            mark_pq_status(pq, error_message, pq.PROCESSING_FAILED)
            self.request.chain = None
            return None
        else:
            mark_pq_status(pq, error_message, pq.QUEUED_FOR_RETRY)
            raise self.retry(exc=exc)

    # Add the HTML to the docket in case we need it someday.
    pacer_file = PacerHtmlFiles(content_object=d,
                                upload_type=UPLOAD_TYPE.DOCKET_HISTORY_REPORT)
    pacer_file.filepath.save(
        # We only care about the ext w/UUIDFileSystemStorage
        'docket_history.html',
        ContentFile(text),
    )

    rds_created, content_updated = add_docket_entries(
        d, data['docket_entries'])
    process_orphan_documents(rds_created, pq.court_id, d.date_filed)
    if content_updated and docket_count > 0:
        newly_enqueued = enqueue_docket_alert(d.pk)
        if newly_enqueued:
            send_docket_alert(d.pk, start_time)
    mark_pq_successful(pq, d_id=d.pk)
    return {
        'docket_pk': d.pk,
        'content_updated': bool(rds_created or content_updated),
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
    mark_pq_status(pq, '', pq.PROCESSING_IN_PROGRESS)
    logger.info("Processing Appellate RECAP item"
                " (debug is: %s): %s" % (pq.debug, pq))

    report = AppellateDocketReport(map_cl_to_pacer_id(pq.court_id))
    text = pq.filepath_local.read().decode('utf-8')

    report._parse_text(text)
    data = report.data
    logger.info("Parsing completed of item %s" % pq)

    if data == {}:
        # Not really a docket. Some sort of invalid document (see Juriscraper).
        msg = "Not a valid docket upload."
        mark_pq_status(pq, msg, pq.INVALID_CONTENT)
        self.request.chain = None
        return None

    # Merge the contents of the docket into CL.
    d, docket_count = find_docket_object(pq.court_id, pq.pacer_case_id,
                                         data['docket_number'])
    if docket_count > 1:
        logger.info("Found %s dockets during lookup. Choosing oldest." %
                    docket_count)
        d = d.earliest('date_created')

    d.add_recap_source()
    update_docket_metadata(d, data)
    d, og_info = update_docket_appellate_metadata(d, data)
    if not d.pacer_case_id:
        d.pacer_case_id = pq.pacer_case_id

    if pq.debug:
        mark_pq_successful(pq, d_id=d.pk)
        self.request.chain = None
        return {'docket_pk': d.pk, 'content_updated': False}

    if og_info is not None:
        og_info.save()
        d.originating_court_information = og_info
    d.save()

    # Add the HTML to the docket in case we need it someday.
    pacer_file = PacerHtmlFiles(content_object=d,
                                upload_type=UPLOAD_TYPE.APPELLATE_DOCKET)
    pacer_file.filepath.save(
        'docket.html',  # We only care about the ext w/UUIDFileSystemStorage
        ContentFile(text),
    )

    rds_created, content_updated = add_docket_entries(
        d, data['docket_entries'])
    add_parties_and_attorneys(d, data['parties'])
    process_orphan_documents(rds_created, pq.court_id, d.date_filed)
    if content_updated and docket_count > 0:
        newly_enqueued = enqueue_docket_alert(d.pk)
        if newly_enqueued:
            send_docket_alert(d.pk, start_time)
    mark_pq_successful(pq, d_id=d.pk)
    return {
        'docket_pk': d.pk,
        'content_updated': bool(rds_created or content_updated),
    }


@app.task(bind=True, max_retries=3, interval_start=5 * 60,
          interval_step=5 * 60)
def process_recap_appellate_attachment(self, pk):
    """Process the appellate attachment pages.

    For now, this is a stub until we can get the parser working properly in
    Juriscraper.
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    msg = "Appellate attachment pages not yet supported. Coming soon."
    mark_pq_status(pq, msg, pq.PROCESSING_FAILED)
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
    case_name = idb_row.plaintiff + ' v. ' + idb_row.defendant
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
        jurisdiction_type=idb_row.get_jurisdiction_display() or '',
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
    d.jurisdiction_type = d.jurisdiction_type or \
                          idb_row.get_jurisdiction_display()
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

    d = Docket.objects.get(pk=data['pass_through'])
    d.docket_number = data['docket_number']
    d.pacer_case_id = data['pacer_case_id']
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
