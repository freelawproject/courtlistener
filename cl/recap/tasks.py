# coding=utf-8
import hashlib
import logging
import os
from datetime import timedelta

from celery.canvas import chain
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from django.utils.timezone import now
from juriscraper.lib.string_utils import CaseNameTweaker
from juriscraper.pacer import DocketReport, AttachmentPage, DocketHistoryReport

from cl.celery import app
from cl.lib.import_lib import get_candidate_judges
from cl.lib.pacer import map_cl_to_pacer_id, normalize_attorney_contact, \
    normalize_attorney_role, get_blocked_status
from cl.lib.recap_utils import get_document_filename
from cl.lib.utils import remove_duplicate_dicts
from cl.people_db.models import Party, PartyType, Attorney, \
    AttorneyOrganization, AttorneyOrganizationAssociation, Role
from cl.recap.models import ProcessingQueue, PacerHtmlFiles, APPELLATE_DOCKET, \
    APPELLATE_ATTACHMENT_PAGE, DOCKET_HISTORY_REPORT, PDF, ATTACHMENT_PAGE, \
    DOCKET
from cl.scrapers.tasks import get_page_count, extract_recap_pdf
from cl.search.models import Docket, RECAPDocument, DocketEntry
from cl.search.tasks import add_or_update_recap_document, \
    add_or_update_recap_docket

logger = logging.getLogger(__name__)
cnt = CaseNameTweaker()


def process_recap_upload(pq):
    """Process an item uploaded from an extension or API user.

    Uploaded objects can take a variety of forms, and we'll need to process them
    accordingly.
    """
    if pq.upload_type == DOCKET:
        chain(process_recap_docket.s(pq.pk),
              add_or_update_recap_docket.s()).apply_async()
    elif pq.upload_type == ATTACHMENT_PAGE:
        process_recap_attachment.delay(pq.pk)
    elif pq.upload_type == PDF:
        process_recap_pdf.delay(pq.pk)
    elif pq.upload_type == DOCKET_HISTORY_REPORT:
        chain(process_recap_docket_history_report.s(pq.pk),
              add_or_update_recap_docket.s()).apply_async()
    elif pq.upload_type == APPELLATE_DOCKET:
        process_recap_appellate_docket.delay(pq.pk)
    elif pq.upload_type == APPELLATE_ATTACHMENT_PAGE:
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
            # No Docket and no RECAPDocument. Do a retry. Hopefully the docket
            # will be in place soon (it could be in a different upload task that
            # hasn't yet been processed).
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
                # If we're here, we've got the docket and docket entry, but
                # were unable to find the document by pacer_doc_id. This happens
                # when pacer_doc_id is missing, for example. ∴, try to get the
                # document from the docket entry.
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
                        date_upload=timezone.now(),
                        document_type=document_type,
                    )

    rd.document_number = pq.document_number
    rd.attachment_number = pq.attachment_number

    # Do the file, finally.
    content = pq.filepath_local.read()
    new_sha1 = hashlib.sha1(content).hexdigest()
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

        rd.ocr_status = None
        rd.is_available = True
        rd.sha1 = new_sha1

    if not pq.debug:
        try:
            rd.save()
        except IntegrityError:
            msg = "Duplicate key on unique_together constraint"
            mark_pq_status(pq, msg, pq.PROCESSING_FAILED)
            rd.filepath_local.delete(save=False)
            return None

    if not existing_document and not pq.debug:
        extract_recap_pdf(rd.pk)
        add_or_update_recap_document([rd.pk], force_commit=False)

    mark_pq_successful(pq, d_id=rd.docket_entry.docket_id,
                       de_id=rd.docket_entry_id, rd_id=rd.pk)
    return rd


def add_attorney(atty, p, d):
    """Add/update an attorney.

    Given an attorney node, and a party and a docket object, add the attorney
    to the database or link the attorney to the new docket. Also add/update the
    attorney organization, and the attorney's role in the case.

    :param atty: A dict representing an attorney, as provided by Juriscraper.
    :param p: A Party object
    :param d: A Docket object
    :return: None if there's an error, or an Attorney object if not.
    """
    newest_docket_date = max([dt for dt in [d.date_filed, d.date_terminated,
                                            d.date_last_filing] if dt])
    atty_org_info, atty_info = normalize_attorney_contact(
        atty['contact'],
        fallback_name=atty['name'],
    )
    try:
        q = Q()
        fields = {
            ('phone', atty_info['phone']),
            ('fax', atty_info['fax']),
            ('email', atty_info['email']),
            ('contact_raw', atty['contact']),
            ('organizations__lookup_key', atty_org_info.get('lookup_key')),
        }
        for field, lookup in fields:
            if lookup:
                q |= Q(**{field: lookup})
        a, created = Attorney.objects.filter(
            Q(name=atty['name']) & q,
        ).distinct().get_or_create(
            defaults={
                'name': atty['name'],
                'date_sourced': newest_docket_date,
                'contact_raw': atty['contact'],
            },
        )
    except Attorney.MultipleObjectsReturned:
        logger.info("Got too many results for attorney: '%s'. Punting." % atty)
        return None

    # Associate the attorney with an org and update their contact info.
    if atty['contact']:
        if atty_org_info:
            logger.info("Adding organization information to '%s': '%s'" %
                        (atty['name'], atty_org_info))
            try:
                org = AttorneyOrganization.objects.get(
                    lookup_key=atty_org_info['lookup_key'],
                )
            except AttorneyOrganization.DoesNotExist:
                try:
                    org = AttorneyOrganization.objects.create(**atty_org_info)
                except IntegrityError:
                    # Race condition. Item was created after get. Try again.
                    org = AttorneyOrganization.objects.get(
                        lookup_key=atty_org_info['lookup_key'],
                    )

            # Add the attorney to the organization
            AttorneyOrganizationAssociation.objects.get_or_create(
                attorney=a,
                attorney_organization=org,
                docket=d,
            )

        docket_info_is_newer = (a.date_sourced <= newest_docket_date)
        if atty_info and docket_info_is_newer:
            logger.info("Updating atty info because %s is more recent than %s."
                        % (newest_docket_date, a.date_sourced))
            a.date_sourced = newest_docket_date
            a.contact_raw = atty['contact']
            a.email = atty_info['email']
            a.phone = atty_info['phone']
            a.fax = atty_info['fax']
            a.save()

    # Do roles
    atty_roles = [normalize_attorney_role(r) for r in atty['roles']]
    atty_roles = filter(lambda r: r['role'] is not None, atty_roles)
    atty_roles = remove_duplicate_dicts(atty_roles)
    if len(atty_roles) > 0:
        logger.info("Linking attorney '%s' to party '%s' via %s roles: %s" %
                    (atty['name'], p.name, len(atty_roles), atty_roles))
    else:
        logger.info("No role data parsed. Linking via 'UNKNOWN' role.")
        atty_roles = [{'role': Role.UNKNOWN, 'date_action': None}]

    # Delete the old roles, replace with new.
    Role.objects.filter(attorney=a, party=p, docket=d).delete()
    Role.objects.bulk_create([
        Role(attorney=a, party=p, docket=d, **atty_role) for
        atty_role in atty_roles
    ])
    return a


def find_docket_object(court_id, pacer_case_id, docket_number):
    """Attempt to find the docket based on the uploaded data. If cannot be
    found, create a new docket. If multiple are found, abort.
    """
    # Attempt several lookups of decreasing specificity. Note that pacer_case_id
    # is required for Docket and Docket History uploads.
    d = None
    for kwargs in [{'pacer_case_id': pacer_case_id,
                    'docket_number': docket_number},
                   {'pacer_case_id': pacer_case_id},
                   {'docket_number': docket_number,
                    'pacer_case_id': None}]:
        try:
            d = Docket.objects.get(court_id=court_id, **kwargs)
            break
        except Docket.DoesNotExist:
            continue
        except Docket.MultipleObjectsReturned:
            return None

    if d is None:
        # Couldn't find a docket. Make a new one.
        d = Docket(
            source=Docket.RECAP,
            pacer_case_id=pacer_case_id,
            court_id=court_id,
        )

    return d


def add_recap_source(d):
    # Add RECAP as a source if it's not already.
    if d.source in [Docket.DEFAULT, Docket.SCRAPER]:
        d.source = Docket.RECAP_AND_SCRAPER
    elif d.source == Docket.COLUMBIA:
        d.source = Docket.COLUMBIA_AND_RECAP
    elif d.source == Docket.COLUMBIA_AND_SCRAPER:
        d.source = Docket.COLUMBIA_AND_RECAP_AND_SCRAPER


def update_docket_metadata(d, docket_data):
    """Update the Docket object with the data from Juriscraper.

    Works on either docket history report or docket report results.
    """
    d.docket_number = docket_data['docket_number'] or d.docket_number
    d.date_filed = docket_data['date_filed'] or d.date_filed
    d.date_last_filing = docket_data.get('date_last_filing') or d.date_last_filing
    d.date_terminated = docket_data['date_terminated'] or d.date_terminated
    if d.case_name == "Unknown Case Title" or not d.case_name:
        d.case_name = docket_data['case_name'] or d.case_name
        d.case_name_short = cnt.make_case_name_short(d.case_name) or d.case_name_short
    d.cause = docket_data.get('cause') or d.cause
    d.nature_of_suit = docket_data.get('nature_of_suit') or d.nature_of_suit
    d.jury_demand = docket_data.get('jury_demand') or d.jury_demand
    d.jurisdiction_type = docket_data.get('jurisdiction') or d.jurisdiction_type
    judges = get_candidate_judges(docket_data.get('assigned_to_str'), d.court_id,
                                  docket_data['date_filed'])
    if judges is not None and len(judges) == 1:
        d.assigned_to = judges[0]
    d.assigned_to_str = docket_data.get('assigned_to_str') or ''
    judges = get_candidate_judges(docket_data.get('referred_to_str'), d.court_id,
                                  docket_data['date_filed'])
    if judges is not None and len(judges) == 1:
        d.referred_to = judges[0]
    d.referred_to_str = docket_data.get('referred_to_str') or ''
    d.blocked, d.date_blocked = get_blocked_status(d)
    return d


def add_docket_entries(d, docket_entries, pq):
    """Update or create the docket entries and documents."""
    rds_created = []
    needs_solr_update = False
    for docket_entry in docket_entries:
        try:
            de, de_created = DocketEntry.objects.get_or_create(
                docket=d,
                entry_number=docket_entry['document_number'],
            )
        except DocketEntry.MultipleObjectsReturned:
            logger.error(
                "Multiple docket entries found for document entry number '%s' "
                "while processing '%s'" % (docket_entry['document_number'], pq)
            )
            continue

        de.description = docket_entry['description'] or de.description
        de.date_filed = docket_entry['date_filed'] or de.date_filed
        de.save()

        if de_created:
            needs_solr_update = True

        # Then make the RECAPDocument object. Try to find it. If we do, update
        # the pacer_doc_id field if it's blank. If we can't find it, create it
        # or throw an error.
        params = {
            'docket_entry': de,
            # No attachments when uploading dockets.
            'document_type': RECAPDocument.PACER_DOCUMENT,
            'document_number': docket_entry['document_number'],
        }
        try:
            rd = RECAPDocument.objects.get(**params)
        except RECAPDocument.DoesNotExist:
            try:
                rd = RECAPDocument.objects.create(
                    pacer_doc_id=docket_entry['pacer_doc_id'],
                    is_available=False,
                    **params
                )
            except ValidationError:
                # Happens from race conditions.
                continue
            rds_created.append(rd)
        except RECAPDocument.MultipleObjectsReturned:
            logger.error(
                "Multiple recap documents found for document entry number'%s' "
                "while processing '%s'" % (docket_entry['document_number'], pq)
            )
            continue
        else:
            rd.pacer_doc_id = rd.pacer_doc_id or docket_entry['pacer_doc_id']
            rd.description = docket_entry.get('short_description') or rd.description

    return rds_created, needs_solr_update


def add_parties_and_attorneys(d, parties):
    """Add parties and attorneys from the docket data to the docket.

    :param d: The docket to update
    :param parties: The parties to update the docket with, with their associated
    attorney objects. This is typically the docket_data['parties'] field.
    :return: None
    """
    for party in parties:
        try:
            p = Party.objects.get(name=party['name'])
        except Party.DoesNotExist:
            try:
                p = Party.objects.create(
                    name=party['name'],
                    extra_info=party['extra_info'],
                )
            except IntegrityError:
                # Race condition. Object was created after our get and before
                # our create. Try to get it again.
                p = Party.objects.get(
                    name=party['name'],
                    extra_info=party['extra_info'],
                )
        except Party.MultipleObjectsReturned:
            continue
        else:
            if party['extra_info']:
                p.extra_info = party['extra_info']
                p.save()

        # If the party type doesn't exist, make a new one.
        if not p.party_types.filter(docket=d, name=party['type']).exists():
            PartyType.objects.create(docket=d, party=p, name=party['type'])

        # Attorneys
        for atty in party.get('attorneys', []):
            add_attorney(atty, p, d)


def process_orphan_documents(rds_created, court_id, docket_date):
    """After we finish processing a docket upload add any PDFs we already had
    for that docket that were lingering in our processing queue. This addresses
    the issue that arises when somebody (somehow) uploads a PDF without first
    uploading a docket.
    """
    pacer_doc_ids = [rd.pacer_doc_id for rd in rds_created]
    if docket_date:
        # If we get a date from the docket, set the cutoff to 30 days prior for
        # good measure.
        cutoff_date = docket_date - timedelta(days=30)
    else:
        # No date from docket. Limit ourselves to the last 180 days. This will
        # help prevent items with weird errors from plaguing us forever.
        cutoff_date = now() - timedelta(days=180)
    pqs = ProcessingQueue.objects.filter(
        pacer_doc_id__in=pacer_doc_ids,
        court_id=court_id,
        status=ProcessingQueue.PROCESSING_FAILED,
        upload_type=PDF,
        debug=False,
        date_modified__gt=cutoff_date,
    ).values_list('pk', flat=True)
    for pq in pqs:
        try:
            process_recap_pdf(pq)
        except:
            # We can ignore this. If we don't, we get all of the exceptions that
            # were previously raised for the processing queue items a second
            # time.
            pass


@app.task(bind=True, max_retries=5, ignore_result=True)
def process_recap_docket(self, pk):
    """Process an uploaded docket from the RECAP API endpoint.

    :param pk: The primary key of the processing queue item you want to work on.
    :returns: A dict of the form:

        {
            // The PK of the docket that's created or updated
            'docket_pk': 22,
            // A boolean indicating whether a new docket entry or recap document
            // was created (implying a Solr needs updating).
            'needs_solr_update': True,
        }

    This value is a dict so that it can be ingested in a Celery chain.
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    mark_pq_status(pq, '', pq.PROCESSING_IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s" % (pq.debug, pq))

    report = DocketReport(map_cl_to_pacer_id(pq.court_id))
    text = pq.filepath_local.read().decode('utf-8')

    if 'History/Documents' in text:
        # Prior to 1.1.8, we did not separate docket history reports into their
        # own upload_type. Alas, we still have some old clients around, so we
        # need to handle those clients here.
        pq.upload_type = DOCKET_HISTORY_REPORT
        pq.save()
        process_recap_docket_history_report(pk)
        self.request.callbacks = None
        return None

    report._parse_text(text)
    data = report.data
    logger.info("Parsing completed of item %s" % pq)

    if data == {}:
        # Not really a docket. Some sort of invalid document (see Juriscraper).
        msg = "Not a valid docket upload."
        mark_pq_status(pq, msg, pq.INVALID_CONTENT)
        self.request.callbacks = None
        return None

    # Merge the contents of the docket into CL.
    d = find_docket_object(pq.court_id, pq.pacer_case_id,
                           data['docket_number'])
    if d is None:
        msg = "Too many dockets found when trying to look up '%s'" % pq
        mark_pq_status(pq, msg, pq.PROCESSING_FAILED)
        self.request.callbacks = None
        return None

    add_recap_source(d)
    update_docket_metadata(d, data)

    if pq.debug:
        mark_pq_successful(pq, d_id=d.pk)
        self.request.callbacks = None
        return {'docket_pk': d.pk, 'needs_solr_update': False}

    d.save()

    # Add the HTML to the docket in case we need it someday.
    pacer_file = PacerHtmlFiles(content_object=d, upload_type=DOCKET)
    pacer_file.filepath.save(
        'docket.html',  # We only care about the ext w/UUIDFileSystemStorage
        ContentFile(text),
    )

    rds_created, needs_solr_update = add_docket_entries(d, data['docket_entries'], pq)
    add_parties_and_attorneys(d, data['parties'])
    process_orphan_documents(rds_created, pq.court_id, d.date_filed)
    mark_pq_successful(pq, d_id=d.pk)
    return {
        'docket_pk': d.pk,
        'needs_solr_update': bool(rds_created or needs_solr_update),
    }


@app.task(bind=True, max_retries=3, interval_start=5 * 60,
          interval_step=5 * 60)
def process_recap_attachment(self, pk):
    """Process an uploaded attachment page from the RECAP API endpoint.

    :param pk: The primary key of the processing queue item you want to work on
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
                                    upload_type=ATTACHMENT_PAGE)
        pacer_file.filepath.save(
            'attachment_page.html',  # Irrelevant b/c UUIDFileSystemStorage
            ContentFile(text),
        )

        # Create/update the attachment items.
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
                if needs_save:
                    rd.save()

                # Do *not* do this async — that can cause race conditions.
                add_or_update_recap_document([rd.pk], force_commit=False)

    mark_pq_successful(pq, d_id=de.docket_id, de_id=de.pk)
    process_orphan_documents(rds_created, pq.court_id,
                             main_rd.docket_entry.docket.date_filed)


@app.task(bind=True, max_retries=3, interval_start=5 * 60,
          interval_step=5 * 60)
def process_recap_docket_history_report(self, pk):
    """Process the docket history report.

    :param pk: The primary key of the processing queue item you want to work on
    :returns: A dict indicating whether the docket needs Solr re-indexing.
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    mark_pq_status(pq, '', pq.PROCESSING_IN_PROGRESS)
    logger.info("Processing RECAP item (debug is: %s): %s" % (pq.debug, pq))

    report = DocketHistoryReport(map_cl_to_pacer_id(pq.court_id))
    with open(pq.filepath_local.path) as f:
        text = f.read().decode('utf-8')
    report._parse_text(text)
    data = report.data
    logger.info("Parsing completed for item %s" % pq)

    # Merge the contents of the docket into CL.
    d = find_docket_object(pq.court_id, pq.pacer_case_id,
                           data['docket_number'])
    if d is None:
        msg = "Too many dockets found when trying to look up '%s'" % pq
        mark_pq_status(pq, msg, pq.PROCESSING_FAILED)
        self.request.callbacks = None
        return None

    add_recap_source(d)
    update_docket_metadata(d, data)

    if pq.debug:
        mark_pq_successful(pq, d_id=d.pk)
        self.request.callbacks = None
        return {'docket_pk': d.pk, 'needs_solr_update': False}

    try:
        d.save()
    except IntegrityError as exc:
        logger.warning("Race condition experienced while attempting docket "
                       "save.")
        error_message = "Unable to save docket due to IntegrityError."
        if self.request.retries == self.max_retries:
            mark_pq_status(pq, error_message, pq.PROCESSING_FAILED)
            self.request.callbacks = None
            return None
        else:
            mark_pq_status(pq, error_message, pq.QUEUED_FOR_RETRY)
            raise self.retry(exc=exc)

    # Add the HTML to the docket in case we need it someday.
    pacer_file = PacerHtmlFiles(content_object=d,
                                upload_type=DOCKET_HISTORY_REPORT)
    pacer_file.filepath.save(
        'docket_history.html',  # We only care about the ext w/UUIDFileSystemStorage
        ContentFile(text),
    )

    rds_created, needs_solr_update = add_docket_entries(d, data['docket_entries'], pq)
    process_orphan_documents(rds_created, pq.court_id, d.date_filed)
    mark_pq_successful(pq, d_id=d.pk)
    return {
        'docket_pk': d.pk,
        'needs_solr_update': bool(rds_created or needs_solr_update),
    }


@app.task(bind=True, max_retries=3, interval_start=5 * 60,
          interval_step=5 * 60)
def process_recap_appellate_docket(self, pk):
    """Process the appellate docket.

    For now, this is a stub until we can get the parser working properly in
    Juriscraper.
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    msg = "Appellate dockets not yet supported. Coming soon."
    mark_pq_status(pq, msg, pq.PROCESSING_FAILED)
    return None


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
