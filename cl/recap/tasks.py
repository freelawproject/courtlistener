import hashlib
import logging
import os

from django.core.files.base import ContentFile
from django.db.models import Q
from django.utils import timezone
from juriscraper.lib.string_utils import CaseNameTweaker
from juriscraper.pacer import DocketReport

from cl.celery import app
from cl.lib.import_lib import get_candidate_judges
from cl.lib.pacer import map_cl_to_pacer_id, normalize_attorney_contact, \
    normalize_attorney_role, get_blocked_status
from cl.lib.recap_utils import get_document_filename
from cl.lib.utils import remove_duplicate_dicts
from cl.people_db.models import Party, PartyType, Attorney, \
    AttorneyOrganization, AttorneyOrganizationAssociation, Role
from cl.recap.models import ProcessingQueue, PacerHtmlFiles
from cl.scrapers.tasks import get_page_count, extract_recap_pdf
from cl.search.models import Docket, RECAPDocument, DocketEntry
from cl.search.tasks import add_or_update_recap_document

logger = logging.getLogger(__name__)
cnt = CaseNameTweaker()


def process_recap_upload(pq):
    """Process an item uploaded from an extension or API user.

    Uploaded objects can take a variety of forms, and we'll need to process them
    accordingly.
    """
    if pq.upload_type == pq.DOCKET:
        process_recap_docket.delay(pq.pk)
    elif pq.upload_type == pq.ATTACHMENT_PAGE:
        pass
    elif pq.upload_type == pq.PDF:
        process_recap_pdf.delay(pq.pk)


@app.task(bind=True, max_retries=2, interval_start=5 * 60,
          interval_step=10 * 60)
def process_recap_pdf(self, pk):
    """Save a RECAP PDF to the database."""
    pq = ProcessingQueue.objects.get(pk=pk)
    pq.status = pq.PROCESSING_IN_PROGRESS
    pq.save()
    logger.info("Processing RECAP item: %s" % pq)
    try:
        rd = RECAPDocument.objects.get(
            docket_entry__docket__pacer_case_id=pq.pacer_case_id,
            pacer_doc_id=pq.pacer_doc_id,
        )
    except RECAPDocument.DoesNotExist:
        try:
            d = Docket.objects.get(pacer_case_id=pq.pacer_case_id,
                                   court_id=pq.court_id)
        except Docket.DoesNotExist as exc:
            # No Docket and no RECAPDocument. Do a retry. Hopefully the docket
            # will be in place soon (it could be in a different upload task that
            # hasn't yet been processed).
            logger.warning("Unable to find docket for processing queue '%s'. "
                           "Retrying if max_retries is not exceeded." % pq)
            pq.error_message = "Unable to find docket for item."
            if self.request.retries == self.max_retries:
                pq.status = pq.PROCESSING_FAILED
                pq.save()
                return None
            else:
                pq.status = pq.QUEUED_FOR_RETRY
                pq.save()
                raise self.retry(exc=exc)
        except Docket.MultipleObjectsReturned:
            msg = "Too many dockets found when trying to save '%s'" % pq
            logger.error(msg)
            pq.error_message = msg
            pq.status = pq.PROCESSING_FAILED
            pq.save()
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
                if self.request.retries == self.max_retries:
                    pq.status = pq.PROCESSING_FAILED
                    pq.save()
                    return None
                else:
                    pq.status = pq.QUEUED_FOR_RETRY
                    pq.save()
                    raise self.retry(exc=exc)

        # All objects accounted for. Make some data.
        rd = RECAPDocument(
            docket_entry=de,
            pacer_doc_id=pq.pacer_doc_id,
            date_upload=timezone.now(),
        )
        if pq.attachment_number is None:
            rd.document_type = RECAPDocument.PACER_DOCUMENT
        else:
            rd.document_type = RECAPDocument.ATTACHMENT

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
        rd.filepath_local.save(file_name, cf, save=False)
        rd.is_available = True
        rd.sha1 = new_sha1

        # Do page count and extraction
        extension = rd.filepath_local.path.split('.')[-1]
        rd.page_count = get_page_count(rd.filepath_local.path, extension)
        rd.ocr_status = None

    rd.save()
    if not existing_document:
        extract_recap_pdf(rd.pk)
        add_or_update_recap_document([rd.pk], force_commit=False)

    # Ditch the original file
    pq.filepath_local.delete(save=False)
    pq.error_message = 'Success! Nice work.'
    pq.status = pq.PROCESSING_SUCCESSFUL
    pq.docket_id = rd.docket_entry.docket_id
    pq.docket_entry_id = rd.docket_entry_id
    pq.recap_document_id = rd.pk
    pq.save()

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
        ).get_or_create(
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
                org = AttorneyOrganization.objects.create(**atty_org_info)

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


def update_docket_metadata(d, docket_data):
    """Update the Docket object with the data from Juriscraper"""
    d.docket_number = d.docket_number or docket_data['docket_number']
    d.pacer_case_id = d.pacer_case_id or docket_data['pacer_case_id']
    d.date_filed = d.date_filed or docket_data['date_filed']
    d.date_terminated = d.date_terminated or docket_data['date_terminated']
    d.case_name = d.case_name or docket_data['case_name']
    d.case_name_short = d.case_name_short or cnt.make_case_name_short(d.case_name)
    d.cause = d.cause or docket_data['cause']
    d.nature_of_suit = d.nature_of_suit or docket_data['nature_of_suit']
    d.jury_demand = d.jury_demand or docket_data['jury_demand']
    d.jurisdiction_type = d.jurisdiction_type or docket_data['jurisdiction']
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
            p = Party.objects.create(
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


@app.task
def process_recap_docket(pk):
    """Process an uploaded docket from the RECAP API endpoint.

    param pk: The primary key of the processing queue item you want to work on.
    """
    pq = ProcessingQueue.objects.get(pk=pk)
    pq.status = pq.PROCESSING_IN_PROGRESS
    pq.save()
    logger.info("Processing RECAP item: %s" % pq)

    report = DocketReport(map_cl_to_pacer_id(pq.court_id))
    text = pq.filepath_local.read().decode('utf-8')
    report._parse_text(text)
    docket_data = report.data
    logger.info("Parsing completed of item %s" % pq)

    # Merge the contents of the docket into CL
    try:
        d = Docket.objects.get(
            Q(pacer_case_id=pq.pacer_case_id) |
            Q(docket_number=docket_data['docket_number']),
            court_id=pq.court_id,
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
            pacer_case_id=pq.pacer_case_id,
            court_id=pq.court_id
        )
    except Docket.MultipleObjectsReturned:
        msg = "Too many dockets found when trying to look up '%s'" % pq
        logger.error(msg)
        pq.error_message = msg
        pq.status = pq.PROCESSING_FAILED
        pq.save()
        return None

    update_docket_metadata(d, docket_data)
    d.save()

    # Add the HTML to the docket in case we need it someday.
    pacer_file = PacerHtmlFiles(content_object=d)
    pacer_file.filepath.save(
        'docket.html',  # We only care about the ext w/UUIDFileSystemStorage
        ContentFile(text),
    )

    # Docket entries
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
                "while processing '%s'" % (docket_entry['document_number'], pq)
            )
            continue

        # Then make the RECAPDocument object. Try to find it. If we do, update
        # the pacer_doc_id field if it's blank. If we can't find it, create it
        # or throw an error.
        try:
            rd = RECAPDocument.objects.get(
                docket_entry=de,
                # No attachments when uploading dockets.
                document_type=RECAPDocument.PACER_DOCUMENT,
                document_number=docket_entry['document_number'],
            )
        except RECAPDocument.DoesNotExist:
            RECAPDocument.objects.create(
                docket_entry=de,
                # No attachments when uploading dockets.
                document_type=RECAPDocument.PACER_DOCUMENT,
                document_number=docket_entry['document_number'],
                pacer_doc_id=docket_entry['pacer_doc_id'],
                is_available=False,
            )
        except RECAPDocument.MultipleObjectsReturned:
            logger.error(
                "Multiple recap documents found for document entry number'%s' "
                "while processing '%s'" % (docket_entry['document_number'], pq)
            )
            continue
        else:
            rd.pacer_doc_id = rd.pacer_doc_id or pq.pacer_doc_id

    add_parties_and_attorneys(d, docket_data['parties'])

    # Ditch the original file (it's associated with the Docket now)
    pq.filepath_local.delete(save=False)
    pq.error_message = ''  # Clear out errors b/c successful
    pq.status = pq.PROCESSING_SUCCESSFUL
    pq.docket = d
    pq.save()

    return d
