# coding=utf-8
import hashlib
import logging
import os
import re
from datetime import timedelta

from celery.canvas import chain
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Prefetch, Q
from django.utils.timezone import now
from juriscraper.lib.string_utils import CaseNameTweaker
from juriscraper.pacer import AppellateDocketReport, AttachmentPage, \
    DocketHistoryReport, DocketReport

from cl.alerts.tasks import enqueue_docket_alert, send_docket_alert
from cl.celery import app
from cl.corpus_importer.utils import mark_ia_upload_needed
from cl.lib.decorators import retry
from cl.lib.filesizes import convert_size_to_bytes
from cl.lib.import_lib import get_candidate_judges
from cl.lib.pacer import get_blocked_status, map_cl_to_pacer_id, \
    normalize_attorney_contact, normalize_attorney_role, map_pacer_to_cl_id
from cl.lib.recap_utils import get_document_filename
from cl.lib.string_utils import anonymize
from cl.lib.utils import remove_duplicate_dicts, previous_and_next
from cl.people_db.models import Attorney, AttorneyOrganization, \
    AttorneyOrganizationAssociation, CriminalComplaint, CriminalCount, \
    Party, PartyType, Role
from cl.recap.models import PacerHtmlFiles, ProcessingQueue, UPLOAD_TYPE, \
    FjcIntegratedDatabase
from cl.scrapers.tasks import extract_recap_pdf, get_page_count
from cl.search.models import Docket, DocketEntry, RECAPDocument, \
    OriginatingCourtInformation, Court, Tag
from cl.search.tasks import add_or_update_recap_docket, \
    add_or_update_recap_document

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
        add_or_update_recap_document([rd.pk], force_commit=False)

    mark_pq_successful(pq, d_id=rd.docket_entry.docket_id,
                       de_id=rd.docket_entry_id, rd_id=rd.pk)
    changed = mark_ia_upload_needed(rd.docket_entry.docket)
    if changed:
        rd.docket_entry.docket.save()
    return rd


def add_attorney(atty, p, d):
    """Add/update an attorney.

    Given an attorney node, and a party and a docket object, add the attorney
    to the database or link the attorney to the new docket. Also add/update the
    attorney organization, and the attorney's role in the case.

    :param atty: A dict representing an attorney, as provided by Juriscraper.
    :param p: A Party object
    :param d: A Docket object
    :return: None if there's an error, or an Attorney ID if not.
    """
    atty_org_info, atty_info = normalize_attorney_contact(
        atty['contact'],
        fallback_name=atty['name'],
    )

    # Try lookup by atty name in the docket.
    attys = Attorney.objects.filter(name=atty['name'],
                                    roles__docket=d).distinct()
    count = attys.count()
    if count == 0:
        # Couldn't find the attorney. Make one.
        a = Attorney.objects.create(
            name=atty['name'],
            contact_raw=atty['contact'],
        )
    elif count == 1:
        # Nailed it.
        a = attys[0]
    elif count >= 2:
        # Too many found, choose the most recent attorney.
        logger.info("Got too many results for atty: '%s'. Picking earliest." %
                    atty)
        a = attys.earliest('date_created')

    # Associate the attorney with an org and update their contact info.
    if atty['contact']:
        if atty_org_info:
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

        if atty_info:
            a.contact_raw = atty['contact']
            a.email = atty_info['email']
            a.phone = atty_info['phone']
            a.fax = atty_info['fax']
            a.save()

    # Do roles
    roles = atty['roles']
    if len(roles) == 0:
        roles = [{'role': Role.UNKNOWN, 'date_action': None}]

    # Delete the old roles, replace with new.
    Role.objects.filter(attorney=a, party=p, docket=d).delete()
    Role.objects.bulk_create([
        Role(attorney=a, party=p, docket=d, **atty_role) for
        atty_role in roles
    ])
    return a.pk


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
    for kwargs in [{'pacer_case_id': pacer_case_id,
                    'docket_number': docket_number},
                   {'pacer_case_id': pacer_case_id},
                   {'docket_number': docket_number,
                    'pacer_case_id': None}]:
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


def update_case_names(d, new_case_name):
    """Update the case name fields if applicable.

    This is a more complex than you'd think at first, and has resulted in at
    least two live bugs. The existing dockets and the new data can each have
    one of three values:

     - A valid case name
     - Unknown Case Title (UCT)
     - ""

    So here's a matrix for what to do:

                                       new_case_name
                       +------------+-----------------+-----------------+
                       |   x v. y   |      UCT        |      blank      |
             +---------+------------+-----------------+-----------------+
             | x v. y  |   Update   |    No update    |    No update    |
             +---------+------------+-----------------+-----------------+
      docket |  UCT    |   Update   |  Same/Whatever  |    No update    |
             +---------+------------+-----------------+-----------------+
             |  blank  |   Update   |     Update      |  Same/Whatever  |
             +---------+------------+-----------------+-----------------+

    :param d: The docket object to update or ignore
    :param new_case_name: The incoming case name
    :returns d
    """
    uct = "Unknown Case Title"
    if not new_case_name:
        return d
    if new_case_name == uct and d.case_name != "":
        return d

    d.case_name = new_case_name
    d.case_name_short = cnt.make_case_name_short(d.case_name)
    return d


def update_docket_metadata(d, docket_data):
    """Update the Docket object with the data from Juriscraper.

    Works on either docket history report or docket report (appellate
    or district) results.
    """
    d = update_case_names(d, docket_data['case_name'])
    mark_ia_upload_needed(d)
    d.docket_number = docket_data['docket_number'] or d.docket_number
    d.date_filed = docket_data['date_filed'] or d.date_filed
    d.date_last_filing = docket_data.get(
        'date_last_filing') or d.date_last_filing
    d.date_terminated = docket_data.get('date_terminated') or d.date_terminated
    d.cause = docket_data.get('cause') or d.cause
    d.nature_of_suit = docket_data.get('nature_of_suit') or d.nature_of_suit
    d.jury_demand = docket_data.get('jury_demand') or d.jury_demand
    d.jurisdiction_type = docket_data.get(
        'jurisdiction') or d.jurisdiction_type
    d.mdl_status = docket_data.get('mdl_status') or d.mdl_status
    judges = get_candidate_judges(docket_data.get('assigned_to_str'),
                                  d.court_id, docket_data['date_filed'])
    if judges is not None and len(judges) == 1:
        d.assigned_to = judges[0]
    d.assigned_to_str = docket_data.get('assigned_to_str') or ''
    judges = get_candidate_judges(docket_data.get('referred_to_str'),
                                  d.court_id, docket_data['date_filed'])
    if judges is not None and len(judges) == 1:
        d.referred_to = judges[0]
    d.referred_to_str = docket_data.get('referred_to_str') or ''
    d.blocked, d.date_blocked = get_blocked_status(d)

    return d


def update_docket_appellate_metadata(d, docket_data):
    """Update the metadata specific to appellate cases."""
    if not any([docket_data.get('originating_court_information'),
                docket_data.get('appeal_from'),
                docket_data.get('panel')]):
        # Probably not appellate.
        return d, None

    d.panel_str = ', '.join(docket_data.get(
        'panel', [])) or d.panel_str
    d.appellate_fee_status = docket_data.get(
        'fee_status', '') or d.appellate_fee_status
    d.appellate_case_type_information = docket_data.get(
        'case_type_information', '') or d.appellate_case_type_information
    d.appeal_from_str = docket_data.get(
        'appeal_from', '') or d.appeal_from_str

    # Do originating court information dict
    og_info = docket_data.get('originating_court_information')
    if not og_info:
        return d, None

    if og_info.get('court_id'):
        cl_id = map_pacer_to_cl_id(og_info['court_id'])
        if Court.objects.filter(pk=cl_id).exists():
            # Ensure the court exists. Sometimes PACER does weird things,
            # like in 14-1743 in CA3, where it says the court_id is 'uspci'.
            # If we don't do this check, the court ID could be invalid, and
            # our whole save of the docket fails.
            d.appeal_from_id = cl_id

    if d.originating_court_information:
        d_og_info = d.originating_court_information
    else:
        d_og_info = OriginatingCourtInformation()

    # Ensure we don't share A-Numbers, which can sometimes be in the docket
    # number field.
    docket_number = og_info.get('docket_number', '') or d_og_info.docket_number
    docket_number, _ = anonymize(docket_number)
    d_og_info.docket_number = docket_number
    d_og_info.court_reporter = og_info.get(
        'court_reporter', '') or d_og_info.court_reporter
    d_og_info.date_disposed = og_info.get(
        'date_disposed') or d_og_info.date_disposed
    d_og_info.date_filed = og_info.get(
        'date_filed') or d_og_info.date_filed
    d_og_info.date_judgment = og_info.get(
        'date_judgment') or d_og_info.date_judgment
    d_og_info.date_judgment_eod = og_info.get(
        'date_judgment_eod') or d_og_info.date_judgment_eod
    d_og_info.date_filed_noa = og_info.get(
        'date_filed_noa') or d_og_info.date_filed_noa
    d_og_info.date_received_coa = og_info.get(
        'date_received_coa') or d_og_info.date_received_coa
    d_og_info.assigned_to_str = og_info.get(
        'assigned_to') or d_og_info.assigned_to_str
    d_og_info.ordering_judge_str = og_info.get(
        'ordering_judge') or d_og_info.ordering_judge_str

    if not all([d.appeal_from_id, d_og_info.date_filed]):
        # Can't do judge lookups. Call it quits.
        return d, d_og_info

    if og_info.get('assigned_to'):
        judges = get_candidate_judges(og_info['assigned_to'], d.appeal_from_id,
                                      d_og_info.date_filed)
        if judges is not None and len(judges) == 1:
            d_og_info.assigned_to = judges[0]

    if og_info.get('ordering_judge'):
        judges = get_candidate_judges(og_info['ordering_judge'], d.appeal_from_id,
                                      d_og_info.date_filed)
        if judges is not None and len(judges) == 1:
            d_og_info.ordering_judge = judges[0]

    return d, d_og_info


def get_order_of_docket(docket_entries):
    """Determine whether the docket is ascending or descending or whether
    that is knowable.
    """
    order = None
    for _, de, nxt in previous_and_next(docket_entries):
        try:
            current_num = int(de['document_number'])
            nxt_num = int(de['document_number'])
        except (TypeError, ValueError):
            # One or the other can't be cast to an int. Continue until we have
            # two consecutive ints we can compare.
            continue

        if current_num == nxt_num:
            # Not sure if this is possible. No known instances in the wild.
            continue
        elif current_num < nxt_num:
            order = 'asc'
        elif current_num > nxt_num:
            order = 'desc'
        break
    return order


def make_recap_sequence_number(de):
    """Make a sequence number using a date and index.

    :param de: A docket entry provided as either a Juriscraper dict or
    DocketEntry object. Regardless of which is provided, there must be a
    key/attribute named recap_sequence_index, which will be used to populate
    the returned sequence number.
    :return a str to use as the recap_sequence_number
    """
    template = "%s.%03d"
    if type(de) == dict:
        return template % (de['date_filed'].isoformat(),
                           de['recap_sequence_index'])
    elif isinstance(de, DocketEntry):
        return template % (de.date_filed.isoformat(),
                           de.recap_sequence_index)


def calculate_recap_sequence_numbers(docket_entries):
    """Figure out the RECAP sequence number values for docket entries
    returned by a parser.

    Writ large, this is pretty simple, but for some items you need to perform
    disambiguation using neighboring docket entries. For example, if you get
    the following docket entries, you need to use the neighboring items to
    figure out which is first:

           Date     | No. |  Description
        2014-01-01  |     |  Some stuff
        2014-01-01  |     |  More stuff
        2014-01-02  |  1  |  Still more

    For those first two items, you have the date, but that's it. No numbers,
    no de_seqno, no nuthin'. The way to handle this is to start by ensuring
    that the docket is in ascending order and correct it if not. With that
    done, you can use the values of the previous items to sort out each item
    in turn.

    :param docket_entries: A list of docket entry dicts from juriscraper or
    another parser containing information about docket entries for a docket
    :return None, but sets the recap_sequence_number for all items.
    """
    # Determine the sort order of the docket entries and normalize it
    order = get_order_of_docket(docket_entries)
    if order == 'desc':
        docket_entries.reverse()

    # Assign sequence numbers
    for prev, de, _ in previous_and_next(docket_entries):
        if prev is not None and de['date_filed'] == prev['date_filed']:
            # Previous item has same date. Increment the sequence number.
            de['recap_sequence_index'] = prev['recap_sequence_index'] + 1
            de['recap_sequence_number'] = make_recap_sequence_number(de)
            continue
        else:
            # prev is None --> First item on the list; OR
            # current is different than previous --> Changed date.
            # Take same action: Reset the index & assign it.
            de['recap_sequence_index'] = 1
            de['recap_sequence_number'] = make_recap_sequence_number(de)
            continue

    # Cleanup
    [de.pop('recap_sequence_index', None) for de in docket_entries]


def normalize_long_description(docket_entry):
    """Ensure that the docket entry description is normalized

    This is important because the long descriptions from the DocketHistory
    report and the Docket report vary, with the latter appending something like
    "(Entered: 01/01/2014)" on the end of every entry. Having this value means
    that our merging algorithms fail since the *only* unique thing we have for
    a unnumbered minute entry is the description itself.

    :param docket_entry: The scraped dict from Juriscraper for the docket
    entry.
    :return None (the item is modified in place)
    """
    if not docket_entry.get('description'):
        return

    # Remove the entry info from the end of the long descriptions
    desc = docket_entry['description']
    desc = re.sub(r'(.*) \(Entered: .*\)$', r'\1', desc)

    # Remove any brackets around numbers (this happens on the DHR long
    # descriptions).
    desc = re.sub(r'\[(\d+)\]', r'\1', desc)

    docket_entry['description'] = desc


def merge_unnumbered_docket_entries(des):
    """Unnumbered docket entries come from many sources, with different data.
    This sometimes results in two docket entries when there should be one. The
    docket history report is the one source that sometimes has the long and
    the short descriptions. When this happens, we have an opportunity to put
    them back together again, deleting the duplicate items.

    :param des: A QuerySet of DocketEntries that we believe are the same.
    :return The winning DocketEntry
    """
    # Choose the earliest as the winner; delete the rest
    winner = des.earliest('date_created')
    des.exclude(pk=winner.pk).delete()
    return winner


def get_or_make_docket_entry(d, docket_entry):
    """Lookup or create a docket entry to match the one that was scraped.

    :param d: The docket we expect to find it in.
    :param docket_entry: The scraped dict from Juriscraper for the docket
    entry.
    :return Tuple of (de, de_created) or None, where:
     - de is the DocketEntry object
     - de_created is a boolean stating whether de was created or not
     - None is returned when things fail.
    """
    if docket_entry['document_number']:
        try:
            de, de_created = DocketEntry.objects.get_or_create(
                docket=d,
                entry_number=docket_entry['document_number'],
            )
        except DocketEntry.MultipleObjectsReturned:
            logger.error("Multiple docket entries found for document "
                         "entry number '%s' while processing '%s'",
                         docket_entry['document_number'], d)
            return None
    else:
        # Unnumbered entry. The only thing we can be sure we have is a
        # date. Try to find it by date and description (short or long)
        normalize_long_description(docket_entry)
        query = Q()
        if docket_entry.get('description'):
            query |= Q(description=docket_entry['description'])
        if docket_entry.get('short_description'):
            query |= Q(recap_documents__description=
                       docket_entry['short_description'])

        des = DocketEntry.objects.filter(
            query,
            docket=d,
            date_filed=docket_entry['date_filed'],
            entry_number=docket_entry['document_number'],
        )
        count = des.count()
        if count == 0:
            de = DocketEntry(
                docket=d,
                entry_number=docket_entry['document_number'],
            )
            de_created = True
        elif count == 1:
            de = des[0]
            de_created = False
        else:
            logger.warning(
                "Multiple docket entries returned for unnumbered docket "
                "entry on date: %s while processing %s. Attempting merge",
                docket_entry['date_filed'], d,
            )
            # There's so little metadata with unnumbered des that if there's
            # more than one match, we can just select the oldest as canonical.
            de = merge_unnumbered_docket_entries(des)
            de_created = False
    return de, de_created


def add_docket_entries(d, docket_entries, tags=None):
    """Update or create the docket entries and documents.

    :param d: The docket object to add things to and use for lookups.
    :param docket_entries: A list of dicts containing docket entry data.
    :param tags: A list of tag objects to apply to the recap documents and
    docket entries created or updated in this function.
    """
    # Remove items without a date filed value.
    docket_entries = [de for de in docket_entries if de.get('date_filed')]

    rds_created = []
    content_updated = False
    calculate_recap_sequence_numbers(docket_entries)
    for docket_entry in docket_entries:
        response = get_or_make_docket_entry(d, docket_entry)
        if response is None:
            continue
        else:
            de, de_created = response[0], response[1]

        de.description = docket_entry['description'] or de.description
        de.date_filed = docket_entry['date_filed'] or de.date_filed
        de.pacer_sequence_number = docket_entry.get('pacer_seq_no') or \
            de.pacer_sequence_number
        de.recap_sequence_number = docket_entry['recap_sequence_number']
        de.save()
        if tags:
            for tag in tags:
                tag.tag_object(de)

        if de_created:
            content_updated = True

        # Then make the RECAPDocument object. Try to find it. If we do, update
        # the pacer_doc_id field if it's blank. If we can't find it, create it
        # or throw an error.
        params = {
            'docket_entry': de,
            # Normalize to "" here. Unsure why, but RECAPDocuments have a
            # char field for this field while DocketEntries have a integer
            # field.
            'document_number': docket_entry['document_number'] or '',
        }
        if not docket_entry['document_number'] and \
                docket_entry.get('short_description'):
            params['description'] = docket_entry['short_description']

        if docket_entry.get('attachment_number'):
            params['document_type'] = RECAPDocument.ATTACHMENT
            params['attachment_number'] = docket_entry['attachment_number']
        else:
            params['document_type'] = RECAPDocument.PACER_DOCUMENT

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
                "while processing '%s'" % (docket_entry['document_number'], d)
            )
            continue

        rd.pacer_doc_id = rd.pacer_doc_id or docket_entry['pacer_doc_id']
        rd.description = docket_entry.get(
            'short_description') or rd.description
        try:
            rd.save()
        except ValidationError:
            # Happens from race conditions.
            continue
        if tags:
            for tag in tags:
                tag.tag_object(rd)

    return rds_created, content_updated


def check_json_for_terminated_entities(parties):
    """Check the parties and attorneys to find if any terminated entities

    If so, we can assume that the user checked the box for "Terminated Parties"
    before running their docket report. If not, we can assume they didn't.

    :param parties: List of party dicts, as returned by Juriscraper.
    :returns boolean indicating whether any parties had termination dates.
    """
    for party in parties:
        if party.get('date_terminated'):
            return True
        for atty in party.get('attorneys', []):
            terminated_role = {a['role'] for a in atty['roles']} & \
                                  {Role.TERMINATED, Role.SELF_TERMINATED}
            if terminated_role:
                return True
    return False


def get_terminated_entities(d):
    """Check the docket to identify if there were any terminated parties or
    attorneys. If so, return their IDs.

    :param d: A docket object to investigate.
    :returns (parties, attorneys): A tuple of two sets. One for party IDs, one
    for attorney IDs.
    """
    # This will do five queries at most rather than doing potentially hundreds
    # on cases with many parties.
    parties = d.parties.prefetch_related(
        Prefetch('party_types',
                 queryset=PartyType.objects.filter(
                     docket=d,
                 ).exclude(
                     date_terminated=None,
                 ).distinct().only('pk'),
                 to_attr='party_types_for_d'),
        Prefetch('attorneys',
                 queryset=Attorney.objects.filter(
                     roles__docket=d,
                 ).distinct().only('pk'),
                 to_attr='attys_in_d'),
        Prefetch('attys_in_d__roles',
                 queryset=Role.objects.filter(
                     docket=d,
                     role__in=[Role.SELF_TERMINATED,
                               Role.TERMINATED],
                 ).distinct().only('pk'),
                 to_attr='roles_for_atty'),
    ).distinct().only('pk')
    terminated_party_ids = set()
    terminated_attorney_ids = set()
    for party in parties:
        for _ in party.party_types_for_d:
            # PartyTypes are filtered to terminated objects. Thus, if
            # any exist, we know it's a terminated party.
            terminated_party_ids.add(party.pk)
            break
        for atty in party.attys_in_d:
            for _ in atty.roles_for_atty:
                # Roles are filtered to terminated roles. Thus, if any hits, we
                # know we have terminated attys.
                terminated_attorney_ids.add(atty.pk)
                break
    return terminated_party_ids, terminated_attorney_ids


def normalize_attorney_roles(parties):
    """Clean up the attorney roles for all parties.

    We do this fairly early in the process because we need to know if
    there are any terminated attorneys before we can start
    adding/removing content to/from the database. By normalizing
    early, we ensure we have good data for that sniffing.

    A party might be input with an attorney such as:

        {
            'name': 'William H. Narwold',
            'contact': ("1 Corporate Center\n",
                        "20 Church Street\n",
                        "17th Floor\n",
                        "Hartford, CT 06103\n",
                        "860-882-1676\n",
                        "Fax: 860-882-1682\n",
                        "Email: bnarwold@motleyrice.com"),
            'roles': ['LEAD ATTORNEY',
                      'TERMINATED: 03/12/2013'],
        }

    The role attribute will be cleaned up to be:

        'roles': [{
            'role': Role.ATTORNEY_LEAD,
            'date_action': None,
            'role_raw': 'LEAD ATTORNEY',
        }, {
            'role': Role.TERMINATED,
            'date_action': date(2013, 3, 12),
            'role_raw': 'TERMINATED: 03/12/2013',
        }

    :param parties: The parties dict from Juriscraper.
    :returns None; editing happens in place.

    """
    for party in parties:
        for atty in party.get('attorneys', []):
            roles = [normalize_attorney_role(r) for r in atty['roles']]
            roles = remove_duplicate_dicts(roles)
            atty['roles'] = roles


def disassociate_extraneous_entities(d, parties, parties_to_preserve,
                                     attorneys_to_preserve):
    """Disassociate any parties or attorneys no longer in the latest info.

     - Do not delete parties or attorneys, just allow them to be orphaned.
       Later, we can decide what to do with these, but keeping them around at
       least lets us have them later if we need them.

     - Sort out if terminated parties were included in the new data. If so,
       they'll be automatically preserved (because they would have been
       updated). If not, find the old terminated parties on the docket, and
       prevent them from getting disassociated.

     - If a party is terminated, do not delete their attorneys even if their
       attorneys are not listed as terminated.

    :param d: The docket to interrogate and act upon.
    :param parties: The parties dict that was scraped, and which we inspect to
    check if terminated parties were included.
    :param parties_to_preserve: A set of party IDs that were updated or created
    while updating the docket.
    :param attorneys_to_preserve: A set of attorney IDs that were updated or
    created while updating the docket.
    """
    new_has_terminated_entities = check_json_for_terminated_entities(parties)
    if not new_has_terminated_entities:
        # No terminated data in the JSON. Check if we have any in the DB.
        terminated_parties, terminated_attorneys = get_terminated_entities(d)
        if any([terminated_parties, terminated_attorneys]):
            # The docket currently has terminated entities, but new info
            # doesn't, indicating that the user didn't request it. Thus, delete
            # any entities that weren't just created/updated and that aren't in
            # the list of terminated entities.
            parties_to_preserve = parties_to_preserve | terminated_parties
            attorneys_to_preserve = \
                attorneys_to_preserve | terminated_attorneys
    else:
        # The terminated parties are already included in the entities to
        # preserve, so just create an empty variable for this.
        terminated_parties = set()

    # Disassociate extraneous parties from the docket.
    PartyType.objects.filter(
        docket=d,
    ).exclude(
        party_id__in=parties_to_preserve,
    ).delete()

    # Disassociate extraneous attorneys from the docket and parties.
    Role.objects.filter(
        docket=d,
    ).exclude(
        # Don't delete attorney roles for attorneys we're preserving.
        attorney_id__in=attorneys_to_preserve,
    ).exclude(
        # Don't delete attorney roles for parties we're preserving b/c
        # they were terminated.
        party_id__in=terminated_parties,
    ).delete()


@transaction.atomic
# Retry on transaction deadlocks; see #814.
@retry(OperationalError, tries=2, delay=1, backoff=1, logger=logger)
def add_parties_and_attorneys(d, parties):
    """Add parties and attorneys from the docket data to the docket.

    :param d: The docket to update
    :param parties: The parties to update the docket with, with their
    associated attorney objects. This is typically the
    docket_data['parties'] field.
    :return: None

    """
    normalize_attorney_roles(parties)

    updated_parties = set()
    updated_attorneys = set()
    for party in parties:
        ps = Party.objects.filter(name=party['name'],
                                  party_types__docket=d).distinct()
        count = ps.count()
        if count == 0:
            try:
                p = Party.objects.create(name=party['name'])
            except IntegrityError:
                # Race condition. Object was created after our get and before
                # our create. Try to get it again.
                ps = Party.objects.filter(name=party['name'],
                                          party_types__docket=d).distinct()
                count = ps.count()
        if count == 1:
            p = ps[0]
        elif count >= 2:
            p = ps.earliest('date_created')
        updated_parties.add(p.pk)

        # If the party type doesn't exist, make a new one.
        pts = p.party_types.filter(docket=d, name=party['type'])
        criminal_data = party.get('criminal_data')
        update_dict = {
            'extra_info': party.get('extra_info', ''),
            'date_terminated': party.get('date_terminated'),
        }
        if criminal_data:
            update_dict['highest_offense_level_opening'] = criminal_data[
                'highest_offense_level_opening']
            update_dict['highest_offense_level_terminated'] = criminal_data[
                'highest_offense_level_terminated']
        if pts.exists():
            pts.update(**update_dict)
            pt = pts[0]
        else:
            pt = PartyType.objects.create(docket=d, party=p,
                                          name=party['type'], **update_dict)

        # Criminal counts and complaints
        if criminal_data and criminal_data['counts']:
            CriminalCount.objects.filter(party_type=pt).delete()
            CriminalCount.objects.bulk_create([
                CriminalCount(
                    party_type=pt, name=criminal_count['name'],
                    disposition=criminal_count['disposition'],
                    status=CriminalCount.normalize_status(
                        criminal_count['status'])
                ) for criminal_count in criminal_data['counts']
            ])

        if criminal_data and criminal_data['complaints']:
            CriminalComplaint.objects.filter(party_type=pt).delete()
            CriminalComplaint.objects.bulk_create([
                CriminalComplaint(
                    party_type=pt, name=complaint['name'],
                    disposition=complaint['disposition'],
                ) for complaint in criminal_data['complaints']
            ])

        # Attorneys
        for atty in party.get('attorneys', []):
            updated_attorneys.add(add_attorney(atty, p, d))

    disassociate_extraneous_entities(d, parties, updated_parties,
                                     updated_attorneys)


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
        upload_type=UPLOAD_TYPE.PDF,
        debug=False,
        date_modified__gt=cutoff_date,
    ).values_list('pk', flat=True)
    for pq in pqs:
        try:
            process_recap_pdf(pq)
        except:
            # We can ignore this. If we don't, we get all of the
            # exceptions that were previously raised for the
            # processing queue items a second time.
            pass


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
        self.request.callbacks = None
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
        self.request.callbacks = None
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
                add_or_update_recap_document([rd.pk], force_commit=False)

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
        self.request.callbacks = None
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
        self.request.callbacks = None
        return {'docket_pk': d.pk, 'content_updated': False}

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
        self.request.callbacks = None
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
        self.request.callbacks = None
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
        jurisdiction_type=idb_row.get_jurisdiction_display(),
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

    :param data: A dict as returned by get_pacer_case_id_and_title_with_docket
    :return None
    """
    if data['lookup_result'] is None:
        return None

    d = Docket.objects.get(pk=data['pass_through'])
    d.docket_number = data['docket_number']
    d.pacer_case_id = data['pacer_case_id']
    d.save()
