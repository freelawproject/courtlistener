# Code for merging PACER content into the DB
import logging
import re
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Prefetch, Q
from django.utils.timezone import now
from juriscraper.lib.string_utils import CaseNameTweaker

from cl.corpus_importer.utils import mark_ia_upload_needed
from cl.lib.decorators import retry
from cl.lib.import_lib import get_candidate_judges
from cl.lib.pacer import get_blocked_status, map_pacer_to_cl_id, \
    normalize_attorney_contact, normalize_attorney_role
from cl.lib.string_utils import anonymize
from cl.lib.utils import previous_and_next, remove_duplicate_dicts
from cl.people_db.models import Attorney, AttorneyOrganization, \
    AttorneyOrganizationAssociation, CriminalComplaint, CriminalCount, Party, \
    PartyType, Role
from cl.recap.models import ProcessingQueue, UPLOAD_TYPE
from cl.search.models import BankruptcyInformation, Claim, ClaimHistory, Court, \
    DocketEntry, OriginatingCourtInformation, RECAPDocument, Tag

logger = logging.getLogger(__name__)

cnt = CaseNameTweaker()


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
    :returns tuple of a list of RECAPDocument objects created and whether the
    any docket entry was created.
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


@transaction.atomic
def add_bankruptcy_data_to_docket(d, claims_data):
    """Add bankruptcy data to the docket from the claims data."""
    try:
        bankr_data = d.bankruptcy_information
    except BankruptcyInformation.DoesNotExist:
        bankr_data = BankruptcyInformation(docket=d)

    bankr_data.date_converted = claims_data.get(
        'date_converted') or bankr_data.date_converted
    bankr_data.date_last_to_file_claims = claims_data.get(
        'date_last_to_file_claims') or bankr_data.date_last_to_file_claims
    bankr_data.date_last_to_file_govt = claims_data.get(
        'date_last_to_file_govt') or bankr_data.date_last_to_file_govt
    bankr_data.date_debtor_dismissed = claims_data.get(
        'date_debtor_dismissed') or bankr_data.date_debtor_dismissed
    bankr_data.chapter = claims_data.get(
        'chapter') or bankr_data.chapter
    bankr_data.trustee_str = claims_data.get(
        'trustee_str') or bankr_data.trustee_str
    bankr_data.save()


def add_claim_history_entry(new_history, claim):
    """Add a document from a claim's history table to the database.

    These documents can reference docket entries or documents that only exist
    in the claims registry. Whatever the case, we just make an entry in the
    claims history table. For now we don't try to link the docket entry table
    with the claims table. It's doable, but adds complexity.

    :param new_history: The history dict returned by juriscraper.
    :param claim: The claim in the database the history is associated with.
    :return None
    """
    history_type = new_history['type']
    common_lookup_params = {
        'claim': claim,
        'date_filed': new_history['date_filed'],
        'pacer_case_id': new_history['pacer_case_id'],
        'document_number': new_history['document_number'],
    }
    if history_type == 'docket_entry':
        db_history, _ = ClaimHistory.objects.get_or_create(
            claim_document_type=ClaimHistory.DOCKET_ENTRY,
            pacer_doc_id=new_history.get('pacer_doc_id', ''),
            **common_lookup_params
        )
        db_history.pacer_dm_id = new_history.get(
            'pacer_dm_id') or db_history.pacer_dm_id
        db_history.pacer_seq_no = new_history.get(
            'pacer_seq_no') or db_history.pacer_seq_no
    else:
        db_history, _ = ClaimHistory.objects.get_or_create(
            claim_document_type=ClaimHistory.CLAIM_ENTRY,
            claim_doc_id=new_history['id'],
            attachment_number=new_history['attachment_number'],
            **common_lookup_params
        )

    db_history.description = new_history.get(
        'description') or db_history.description
    db_history.save()


@transaction.atomic
def add_claims_to_docket(d, new_claims, tag_names):
    """Add claims data to the docket.

    :param d: A docket object to associate claims with.
    :param new_claims: A list of claims dicts from Juriscraper.
    :param tag_names: A list of tag names to add to the claims.
    """
    for new_claim in new_claims:
        db_claim, _ = Claim.objects.get_or_create(
            docket=d,
            claim_number=new_claim['claim_number']
        )
        db_claim.date_claim_modified = new_claim.get(
            'date_claim_modified') or db_claim.date_claim_modified
        db_claim.date_original_entered = new_claim.get(
            'date_original_entered') or db_claim.date_original_entered
        db_claim.date_original_filed = new_claim.get(
            'date_original_filed') or db_claim.date_original_filed
        db_claim.date_last_amendment_entered = new_claim.get(
            'date_last_amendment_entered') or db_claim.date_last_amendment_entered
        db_claim.date_last_amendment_filed = new_claim.get(
            'date_last_amendment_filed') or db_claim.date_last_amendment_filed
        db_claim.creditor_details = new_claim.get(
            'creditor_details') or db_claim.creditor_details
        db_claim.creditor_id = new_claim.get(
            'creditor_id') or db_claim.creditor_id
        db_claim.status = new_claim.get(
            'status') or db_claim.status
        db_claim.entered_by = new_claim.get(
            'entered_by') or db_claim.entered_by
        db_claim.filed_by = new_claim.get(
            'filed_by') or db_claim.filed_by
        db_claim.amount_claimed = new_claim.get(
            'amount_claimed') or db_claim.amount_claimed
        db_claim.unsecured_claimed = new_claim.get(
            'unsecured_claimed') or db_claim.unsecured_claimed
        db_claim.secured_claimed = new_claim.get(
            'secured_claimed') or db_claim.secured_claimed
        db_claim.priority_claimed = new_claim.get(
            'priority_claimed') or db_claim.priority_claimed
        db_claim.description = new_claim.get(
            'description') or db_claim.description
        db_claim.remarks = new_claim.get(
            'remarks') or db_claim.remarks
        db_claim.save()

        # Add tags to claim
        tags = []
        if tag_names is not None:
            for tag_name in tag_names:
                tag, _ = Tag.objects.get_or_create(name=tag_name)
                tag.tag_object(db_claim)
                tags.append(tag)

        for new_history in new_claim['history']:
            add_claim_history_entry(new_history, db_claim)


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
            from cl.recap.tasks import process_recap_pdf
            process_recap_pdf(pq)
        except:
            # We can ignore this. If we don't, we get all of the
            # exceptions that were previously raised for the
            # processing queue items a second time.
            pass
