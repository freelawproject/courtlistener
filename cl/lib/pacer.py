import logging
import os
import re
from collections import OrderedDict
from datetime import date

import usaddress
from dateutil import parser
from dateutil.tz import gettz
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.db import transaction
from django.db.models import Q
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize, titlecase
from juriscraper.lib.exceptions import ParsingException
from juriscraper.pacer import DocketReport, DocketHistoryReport
from juriscraper.pacer.docket_utils import normalize_party_types
from localflavor.us.forms import phone_digits_re
from localflavor.us.us_states import STATES_NORMALIZED, USPS_CHOICES
from lxml import etree

from cl.lib.import_lib import get_candidate_judges
from cl.lib.recap_utils import (
    get_docketxml_url_from_path, get_ia_document_url_from_path,
    get_local_document_url_from_path,
)
from cl.lib.utils import remove_duplicate_dicts
from cl.scrapers.tasks import get_page_count
from cl.search.models import Court, Docket, RECAPDocument, DocketEntry
from cl.people_db.models import Role, Party, AttorneyOrganization, PartyType, \
    Attorney, AttorneyOrganizationAssociation
from cl.recap.models import DOCKET_HISTORY_REPORT, DOCKET


logger = logging.getLogger(__name__)


pacer_to_cl_ids = {
    # Maps PACER ids to their CL equivalents
    'azb': 'arb',         # Arizona Bankruptcy Court
    'cofc': 'uscfc',      # Court of Federal Claims
    'neb': 'nebraskab',   # Nebraska Bankruptcy
    'nysb-mega': 'nysb',  # Remove the mega thing
}

# Reverse dict of pacer_to_cl_ids
cl_to_pacer_ids = {v: k for k, v in pacer_to_cl_ids.items()}


def map_pacer_to_cl_id(pacer_id):
    return pacer_to_cl_ids.get(pacer_id, pacer_id)


def map_cl_to_pacer_id(cl_id):
    if cl_id == 'nysb':
        return cl_id
    else:
        return cl_to_pacer_ids.get(cl_id, cl_id)


def lookup_and_save(new, debug=False):
    """Merge new docket info into the database.

    Start by attempting to lookup an existing Docket. If that's not found,
    create a new one. Either way, merge all the attributes of `new` into the
    Docket found, and then save the Docket.

    Returns None if an error occurs, else, return the new or updated Docket.
    """
    try:
        d = Docket.objects.get(pacer_case_id=new.pacer_case_id,
                               court=new.court)
    except (Docket.DoesNotExist, Docket.MultipleObjectsReturned):
        d = None

    if d is None:
        ds = Docket.objects.filter(docket_number=new.docket_number,
                                   court=new.court).order_by('-date_filed')
        count = ds.count()
        if count < 1:
            # Can't find it by pacer_case_id or docket_number. Make a new item.
            d = Docket(source=Docket.RECAP)
        elif count == 1:
            # Nailed it!
            d = ds[0]
        elif count > 1:
            # Too many dockets returned. Disambiguate.
            logger.error("Got multiple results while attempting save.")

            def is_different(x):
                return x.pacer_case_id and x.pacer_case_id != new.pacer_case_id
            if all([is_different(d) for d in ds]):
                # All the dockets found match on docket number, but have
                # different pacer_case_ids. This means that the docket has
                # multiple pacer_case_ids in PACER, and we should mirror that
                # in CL by creating a new docket for the new item.
                d = Docket(source=Docket.RECAP)
            else:
                # Just use the most recent docket. Looking at the data, this is
                # OK. Nearly all of these are dockets associated with clusters
                # that can be merged (however, that's a project for clusters).
                d = ds[0]

    # Add RECAP as a source if it's not already.
    if d.source in [Docket.DEFAULT, Docket.SCRAPER]:
        d.source = Docket.RECAP_AND_SCRAPER
    elif d.source == Docket.COLUMBIA:
        d.source = Docket.COLUMBIA_AND_RECAP
    elif d.source == Docket.COLUMBIA_AND_SCRAPER:
        d.source = Docket.COLUMBIA_AND_RECAP_AND_SCRAPER

    for attr, v in new.__dict__.items():
        setattr(d, attr, v)

    if not debug:
        d.save()
        logger.info("Saved as Docket %s: https://www.courtlistener.com%s" %
                    (d.pk, d.get_absolute_url()))
    return d


def get_first_missing_de_number(d):
    """When buying dockets use this function to figure out which docket entries
    we already have, starting at the first item. Since PACER only allows you to
    do a range of docket entries, this allows us to figure out a later starting
    point for our query.

    For example, if we have documents 1-32 already in the DB, we can save some
    money by only getting items 33 and on.

    :param d: The Docket object to check.
    :returns int: The starting point that should be used in your query. If the
    docket has no entries, returns 1. If the docket has entries, returns the
    value of the lowest missing item.
    """
    de_numbers = list(d.docket_entries.all().order_by(
        'entry_number'
    ).values_list('entry_number', flat=True))

    if len(de_numbers) > 0:
        # Get the earliest missing item
        end = de_numbers[-1]
        missing_items = sorted(set(range(1, end + 1)).difference(de_numbers))
        if missing_items:
            return missing_items[0]
        else:
            # None missing, but we can start after the highest de we know.
            return end + 1
    return 1


def get_blocked_status(docket, count_override=None):
    """Set the blocked status for the Docket.

    Dockets are public (blocked is False) when:

                                       Is Bankr. Court
                                    +---------+--------+
                                    |   YES   |   NO   |
                    +---------------+---------+--------+
             Size   | > 500 items   |    X    |    X   |
              of    +---------------+---------+--------+
            Docket  | <= 500 items  |         |    X   |
                    +---------------+---------+--------+

    :param docket: A Docket or Docket-like object that contains a `court`
    attribute that can be checked to see if it is a bankruptcy court.
    :param count_override: Allows a calling function to provide the count, if
    it is known in advance.
    :returns A tuple containing two entries. The first is a boolean stating
    whether the item should be private. The second is the date of the privacy
    decision (today) or None if the item should not be private.
    """
    if getattr(docket, 'blocked', False):
        # Short circuit. This function can only make things blocked that were
        # previously public.
        return docket.blocked, docket.date_blocked

    bankruptcy_privacy_threshold = 500
    if count_override is not None:
        count = count_override
    else:
        count = docket.docket_entries.all().count()
    small_case = count <= bankruptcy_privacy_threshold
    if all([small_case, docket.court in Court.BANKRUPTCY_JURISDICTIONS]):
        return True, date.today()
    return False, None


def reprocess_docket_data(d, filepath, report_type):
    """Reprocess docket data that we already have.

    :param d: A docket object to work on.
    :param filepath: The path to a saved HTML file containing docket or docket
    history report data.
    :param report_type: Whether it's a docket or a docket history report.
    """
    from cl.recap.tasks import update_docket_metadata, add_docket_entries, \
        add_parties_and_attorneys
    if report_type == DOCKET:
        report = DocketReport(map_cl_to_pacer_id(d.court_id))
    elif report_type == DOCKET_HISTORY_REPORT:
        report = DocketHistoryReport(map_cl_to_pacer_id(d.court_id))
    with open(filepath, 'r') as f:
        text = f.read().decode('utf-8')
    report._parse_text(text)
    data = report.data
    if data == {}:
        return None
    update_docket_metadata(d, data)
    d.save()
    add_docket_entries(d, data['docket_entries'])
    if report_type == DOCKET:
        add_parties_and_attorneys(d, data['parties'])
    return d.pk


class PacerXMLParser(object):
    """A class to parse a PACER XML file"""

    cnt = CaseNameTweaker()

    def __init__(self, path):
        logger.info("Initializing parser for %s" % path)
        # High-level attributes
        self.path = path
        self.xml = self.get_xml_contents()
        self.case_details = self.get_case_details()
        self.document_list = self.get_document_list()
        self.party_list = self.get_party_list()
        self.document_count = self.get_document_count()

        # Docket attributes
        self.court = self.get_court()
        self.docket_number = self.get_str_from_node(
            self.case_details, 'docket_num')
        self.pacer_case_id = self.get_str_from_node(
            self.case_details, 'pacer_case_num')
        self.date_filed = self.get_datetime_from_node(
            self.case_details, 'date_case_filed', cast_to_date=True)
        self.date_terminated = self.get_datetime_from_node(
            self.case_details, 'date_case_terminated', cast_to_date=True)
        self.date_last_filing = self.get_datetime_from_node(
            self.case_details, 'date_last_filing', cast_to_date=True)
        self.case_name = harmonize(self.get_str_from_node(
            self.case_details, 'case_name'))
        self.case_name_short = self.cnt.make_case_name_short(self.case_name)
        self.cause = self.get_str_from_node(
            self.case_details, 'case_cause')
        self.nature_of_suit = self.get_str_from_node(
            self.case_details, 'nature_of_suit')
        self.jury_demand = self.get_str_from_node(
            self.case_details, 'jury_demand')
        self.jurisdiction_type = self.get_str_from_node(
            self.case_details, 'jurisdiction')
        self.assigned_to, self.assigned_to_str = self.get_judges('assigned_to')
        self.referred_to, self.referred_to_str = self.get_judges('referred_to')
        self.blocked, self.date_blocked = get_blocked_status(
            self, self.document_count)

        # Non-parsed fields
        self.filepath_local = os.path.join('recap', self.path)
        self.filepath_ia = get_docketxml_url_from_path(self.path)

    def get_xml_contents(self):
        """Extract the XML from the file on disk and return it as an lxml
        tree
        """
        xml_parser = etree.XMLParser(recover=True)
        tree = etree.parse(self.path, xml_parser)

        return tree

    def get_case_details(self):
        """Most of the details are in the case_details node, so set it aside
        for faster parsing.
        """
        return self.xml.xpath('//case_details')[0]

    def get_document_list(self):
        """Get the XML nodes for the documents"""
        return self.xml.xpath('//document_list/document')

    def get_party_list(self):
        """Get the XML nodes for the parties"""
        return self.xml.xpath('//party_list/party')

    def get_document_count(self):
        """Get the number of documents associated with this docket."""
        return len(self.document_list)

    def make_documents(self, docket, debug):
        """Parse through the document nodes, making good objects.

        For every node, create a line item on the Docket (a DocketEntry), and
        create 1..n additional RECAPDocuments (attachments or regular documents)
        that are associated with that DocketEntry.

        Returns None if an error occurs.
        """
        recap_docs = []
        for doc_node in self.document_list:
            # Make a DocketEntry object
            entry_number = doc_node.xpath('@doc_num')[0]
            attachment_number = int(doc_node.xpath('@attachment_num')[0])
            logger.info("Working on document %s, attachment %s" %
                        (entry_number, attachment_number))

            if attachment_number == 0:
                document_type = RECAPDocument.PACER_DOCUMENT
            else:
                document_type = RECAPDocument.ATTACHMENT

            try:
                docket_entry = DocketEntry.objects.get(
                    docket=docket,
                    entry_number=entry_number,
                )
            except DocketEntry.DoesNotExist:
                if document_type == RECAPDocument.PACER_DOCUMENT:
                    docket_entry = DocketEntry(
                        docket=docket,
                        entry_number=entry_number,
                    )
                else:
                    logger.error("Tried to create attachment without a "
                                 "DocketEntry object to associate it with.")
                    continue

            if document_type == RECAPDocument.PACER_DOCUMENT:
                date_filed = (
                    self.get_datetime_from_node(doc_node, 'date_filed',
                                                cast_to_date=True) or
                    docket_entry.date_filed
                )
                docket_entry.date_filed = date_filed
                docket_entry.description = (
                    self.get_str_from_node(doc_node, 'long_desc') or
                    docket_entry.description
                )
                try:
                    if not debug:
                        docket_entry.save()
                except (IntegrityError, DocketEntry.MultipleObjectsReturned):
                    logger.error("Unable to create docket entry for docket "
                                 "#%s, on entry: %s." % (docket, entry_number))
                    continue

            recap_doc = self.make_recap_document(
                doc_node,
                docket_entry,
                entry_number,
                attachment_number,
                document_type,
                debug,
            )
            if recap_doc is not None:
                recap_docs.append(recap_doc)

        return [item.pk for item in recap_docs]

    def make_recap_document(self, doc_node, docket_entry, entry_number,
                            attachment_number, document_type, debug):
        """Make a PACER document."""
        pacer_document_id = self.get_str_from_node(
            doc_node, 'pacer_doc_id')
        try:
            rd = RECAPDocument.objects.get(
                docket_entry=docket_entry,
                document_number=entry_number,
                # Use the attachment number if it is not 0, else use None.
                attachment_number=attachment_number or None,
            )
        except RECAPDocument.DoesNotExist:
            rd = RECAPDocument(
                docket_entry=docket_entry,
                pacer_doc_id=pacer_document_id,
                document_number=entry_number,
            )
        else:
            rd.pacer_doc_id = pacer_document_id or rd.pacer_doc_id

        rd.date_upload = self.get_datetime_from_node(doc_node, 'upload_date')
        rd.document_type = document_type or rd.document_type

        if not rd.is_available:
            # If we can't parse the availability node (it returns None),
            # default it to False.
            availability = self.get_bool_from_node(doc_node, 'available')
            rd.is_available = False if availability is None else availability
        if not rd.sha1:
            rd.sha1 = self.get_str_from_node(doc_node, 'sha1')
        rd.description = (self.get_str_from_node(doc_node, 'short_desc') or
                          rd.description)
        if rd.is_available:
            rd.filepath_ia = get_ia_document_url_from_path(
                self.path, entry_number, attachment_number)
            rd.filepath_local = os.path.join(
                'recap',
                get_local_document_url_from_path(self.path, entry_number,
                                                 attachment_number),
            )
            if rd.page_count is None:
                extension = rd.filepath_local.path.split('.')[-1]
                rd.page_count = get_page_count(rd.filepath_local.path, extension)
        if document_type == RECAPDocument.ATTACHMENT:
            rd.attachment_number = attachment_number
        if not debug:
            rd.save(do_extraction=False, index=False)
        return rd

    @transaction.atomic
    def make_parties(self, docket, debug):
        """Pull out the parties and their attorneys and save them to the DB."""
        atty_obj_cache = {}
        for party_node in self.party_list:
            party_name = self.get_str_from_node(party_node, 'name')
            party_type = self.get_str_from_node(party_node, 'type')
            party_type = normalize_party_types(party_type)
            party_extra_info = self.get_str_from_node(party_node, 'extra_info')
            logger.info("Working on party '%s' of type '%s'" % (party_name,
                                                                party_type))

            try:
                party = Party.objects.get(name=party_name)
            except Party.DoesNotExist:
                party = Party(name=party_name)
                if not debug:
                    try:
                        party.save()
                    except IntegrityError:
                        party = Party.objects.get(name=party_name)

            # If the party type doesn't exist, make a new one.
            pts = party.party_types.filter(docket=docket, name=party_type)
            if pts.exists():
                pts.update(extra_info=party_extra_info)
            else:
                pt = PartyType(
                    docket=docket,
                    party=party,
                    name=party_type,
                    extra_info=party_extra_info,
                )
                if not debug:
                    pt.save()

            self.add_attorneys(docket, party_node, party, atty_obj_cache, debug)

    def add_attorneys(self, docket, party_node, party, atty_obj_cache, debug):
        atty_nodes = party_node.xpath('.//attorney_list/attorney')
        logger.info("Adding %s attorneys to the party." % len(atty_nodes))
        for atty_node in atty_nodes:
            atty_name = self.get_str_from_node(atty_node, 'attorney_name')
            logger.info("Adding attorney: '%s'" % atty_name)
            atty_contact_raw = self.get_str_from_node(atty_node, 'contact')
            if 'see above' in atty_contact_raw.lower():
                logger.info("Got 'see above' entry for atty_contact_raw.")
                atty_contact_raw = ''
                try:
                    atty, atty_org_info, atty_info = atty_obj_cache[atty_name]
                except KeyError:
                    logger.warn("Unable to lookup 'see above' entry. "
                                "Creating/using atty with no contact info.")
                    try:
                        atty = Attorney.objects.get(name=atty_name,
                                                    contact_raw=atty_contact_raw)
                    except Attorney.DoesNotExist:
                        atty = Attorney(name=atty_name,
                                        contact_raw=atty_contact_raw)
                        if not debug:
                            atty.save()

            else:
                # New attorney for this docket. Look them up in DB or create new
                # attorney if necessary.
                atty_org_info, atty_info = normalize_attorney_contact(
                    atty_contact_raw, fallback_name=atty_name)
                try:
                    logger.info("Didn't find attorney in cache, attempting "
                                "lookup in the DB.")
                    # Find an atty with the same name and one of another several
                    # IDs. Important to add contact_raw here, b/c if it cannot
                    # be parsed, all other values are blank.
                    q = Q()
                    fields = [
                        ('phone', atty_info['phone']),
                        ('fax', atty_info['fax']),
                        ('email', atty_info['email']),
                        ('contact_raw', atty_contact_raw),
                        ('organizations__lookup_key',
                         atty_org_info.get('lookup_key')),
                    ]
                    for field, lookup in fields:
                        if lookup:
                            q |= Q(**{field: lookup})
                    atty = Attorney.objects.get(Q(name=atty_name) & q)
                except Attorney.DoesNotExist:
                    logger.info("Unable to find matching attorney. Creating a "
                                "new one: %s" % atty_name)
                    atty = Attorney(name=atty_name,
                                    contact_raw=atty_contact_raw)
                    if not debug:
                        atty.save()
                except Attorney.MultipleObjectsReturned:
                    logger.warn("Got too many results for attorney: '%s' "
                                "Punting." % atty_name)
                    continue

                # Cache the atty object and info for "See above" entries.
                atty_obj_cache[atty_name] = (atty, atty_org_info, atty_info)

            if atty_contact_raw:
                if atty_org_info:
                    logger.info("Adding organization information to "
                                "'%s': %s" % (atty_name, atty_org_info))
                    try:
                        org = AttorneyOrganization.objects.get(
                            lookup_key=atty_org_info['lookup_key'],
                        )
                    except AttorneyOrganization.DoesNotExist:
                        org = AttorneyOrganization(**atty_org_info)
                        if not debug:
                            org.save()

                    # Add the attorney to the organization
                    if not debug:
                        AttorneyOrganizationAssociation.objects.get_or_create(
                            attorney=atty,
                            attorney_organization=org,
                            docket=docket,
                        )

                if atty_info:
                    atty.contact_raw = atty_contact_raw
                    atty.email = atty_info['email']
                    atty.phone = atty_info['phone']
                    atty.fax = atty_info['fax']
                    if not debug:
                        atty.save()

            atty_role_str = self.get_str_from_node(atty_node, 'attorney_role')
            atty_roles = [normalize_attorney_role(r) for r in
                          atty_role_str.split('\n') if r]
            atty_roles = [r for r in atty_roles if r['role'] is not None]
            atty_roles = remove_duplicate_dicts(atty_roles)
            if len(atty_roles) > 0:
                logger.info("Linking attorney '%s' to party '%s' via %s "
                            "roles: %s" % (atty_name, party.name,
                                           len(atty_roles), atty_roles))
            else:
                logger.info("No role data parsed. Linking via 'UNKNOWN' role.")
                atty_roles = [{'role': Role.UNKNOWN, 'date_action': None}]

            if not debug:
                # Delete the old roles, replace with new.
                Role.objects.filter(attorney=atty, party=party,
                                    docket=docket).delete()
                Role.objects.bulk_create([
                    Role(attorney=atty, party=party, docket=docket,
                         **atty_role) for
                    atty_role in atty_roles
                ])

    def get_court(self):
        """Extract the court from the XML and return it as a Court object"""
        court_str = self.case_details.xpath('court/text()')[0].strip()
        try:
            c = Court.objects.get(pk=map_pacer_to_cl_id(court_str))
        except Court.DoesNotExist:
            raise ParsingException("Unable to identify court: %s" % court_str)
        else:
            return c

    @staticmethod
    def get_bool_from_node(node, path):
        try:
            s = node.xpath('%s/text()' % path)[0].strip()
            n = int(s)
        except IndexError:
            logger.debug("Couldn't get bool from path: %s" % path)
            return None
        except ValueError:
            logger.debug("Couldn't convert text '%s' to int when making boolean "
                         "for path: %s" % (s, path))
            return None
        else:
            return bool(n)

    @staticmethod
    def get_str_from_node(node, path):
        try:
            s = node.xpath('%s/text()' % path)[0].strip()
        except IndexError:
            logger.debug("Couldn't get string from path: %s" % path)
            return ''  # Return an empty string. Don't return None.
        else:
            return s

    def get_int_from_details(self, node):
        s = self.case_details.xpath('%s/text()' % node)[0].strip()
        try:
            return int(s)
        except ValueError:
            # Can't parse string to int
            logger.debug("Couldn't get int for node %s" % node)
            raise ParsingException("Cannot extract int for node %s" % node)

    @staticmethod
    def get_datetime_from_node(node, path, cast_to_date=False):
        """Parse a datetime from the XML located at node.

        If cast_to_date is true, the datetime object will be converted to a
        date. Else, will return a datetime object in parsed TZ if possible.
        Failing that, it will assume UTC.
        """
        try:
            s = node.xpath('%s/text()' % path)[0].strip()
        except IndexError:
            logger.debug("Couldn't get date from path: %s" % path)
            return None
        else:
            try:
                d = parser.parse(s)
            except ValueError:
                logger.debug("Couldn't parse date: %s" % s)
                return None
            else:
                d = d.replace(tzinfo=d.tzinfo or gettz('UTC'))  # Set it to UTC.
                if cast_to_date is True:
                    return d.date()
                return d

    def get_judges(self, node):
        """Parse out the judge string and then look it up in the DB"""
        try:
            s = self.case_details.xpath('%s/text()' % node)[0].strip()
        except IndexError:
            logger.info("Couldn't get judge for node: %s" % node)
            return None, ''
        else:
            judges = get_candidate_judges(s, self.court.pk, self.date_filed)
            if len(judges) == 0:
                return None, s
            elif len(judges) == 1:
                return judges[0], s
            else:
                return None, s


def normalize_attorney_role(r):
    """Normalize attorney roles into the valid set"""
    role = {'role': None, 'date_action': None}

    r = r.lower()
    # Bad values we can expect. Nuke these early so they don't cause problems.
    if any([r.startswith(u'bar status'),
            r.startswith(u'designation')]):
        return role

    if u'to be noticed' in r:
        role['role'] = Role.ATTORNEY_TO_BE_NOTICED
    elif u'lead attorney' in r:
        role['role'] = Role.ATTORNEY_LEAD
    elif u'sealed group' in r:
        role['role'] = Role.ATTORNEY_IN_SEALED_GROUP
    elif u'pro hac vice' in r:
        role['role'] = Role.PRO_HAC_VICE
    elif u'self- terminated' in r:
        role['role'] = Role.SELF_TERMINATED
    elif u'terminated' in r:
        role['role'] = Role.TERMINATED
    elif u'suspended' in r:
        role['role'] = Role.SUSPENDED
    elif u'inactive' in r:
        role['role'] = Role.INACTIVE
    elif u'disbarred' in r:
        role['role'] = Role.DISBARRED

    try:
        role['date_action'] = parser.parse(r, fuzzy=True).date()
    except ValueError:
        role['date_action'] = None

    if role['role'] is None:
        raise ValueError(u"Unable to match role: %s" % r)
    else:
        return role


def normalize_us_phone_number(phone):
    """Tidy up phone numbers so they're nice."""
    phone = re.sub('(\(|\)|\s+)', '', phone)
    m = phone_digits_re.search(phone)
    if m:
        return '(%s) %s-%s' % (m.group(1), m.group(2), m.group(3))
    return ''


def normalize_us_state(state):
    """Convert state values to valid state postal abbreviations

    va --> VA
    Virginia --> VA

    Raises KeyError if state cannot be normalized.
    """
    abbreviations = [t[0] for t in USPS_CHOICES]
    if state in abbreviations:
        return state

    try:
        state = STATES_NORMALIZED[state.lower()]
    except KeyError:
        state = ''
    return state


def make_address_lookup_key(address_info):
    """Make a key for looking up normalized addresses in the DB

     - Sort the fields alphabetically
     - Strip anything that's not a character or number
     - Remove/normalize a variety of words that add little meaning and are often
       omitted.
    """
    sorted_info = OrderedDict(sorted(address_info.items()))
    fixes = {
        r'atty.': '',
        r'and': '',  # These are often used instead of & in firm names.
        r'boulevard': 'blvd',
        r'llp': '',
        r'offices': 'office',
        r'pc': '',
        r'p\.c\.': '',
        r'pa': '',
        r'p\.a\.': '',
        r'post office box': 'P.O. Box',
        r'Ste': 'Suite',
    }
    for k, v in sorted_info.items():
        for bad, good in fixes.items():
            v = re.sub(r'\b%s\b' % bad, good, v, flags=re.IGNORECASE)
        sorted_info[k] = v
    key = ''.join(sorted_info.values())
    return re.sub(r'[^a-z0-9]', '', key.lower())


def normalize_address_info(address_info):
    """Normalize various address components"""

    # Titlecase where appropriate
    for k, v in address_info.items():
        if k == 'state':
            continue
        address_info[k] = titlecase(v)

    # Normalize street abbreviations (St --> Street, etc.)
    fixes = OrderedDict((
        ('Street', 'St.'),
        ('Avenue', 'Ave.'),
        ('Boulevard', 'Blvd.'),
    ))
    for address_part in ['address1', 'address2']:
        a = address_info.get(address_part)
        if not a:
            continue

        for bad, good in fixes.items():
            a = re.sub(r'\b%s\b' % bad, good, a, flags=re.IGNORECASE)

        address_info[address_part] = a

    # Nuke any zip code that's longer than allowed in the DB (usually caused by
    # phone numbers)
    zip_code_field = AttorneyOrganization._meta.get_field('zip_code')
    if len(address_info.get('zip_code', '')) > zip_code_field.max_length:
        address_info['zip_code'] = ''
    return address_info


def normalize_attorney_contact(c, fallback_name=''):
    """Normalize the contact string for an attorney.

    Attorney contact strings are newline separated addresses like:

        Landye Bennett Blumstein LLP
        701 West Eighth Avenue, Suite 1200
        Anchorage, AK 99501
        907-276-5152
        Email: brucem@lbblawyers.com

    We need to pull off email and phone numbers, and then our address parser
    should work nicely.
    """
    atty_info = {
        'email': '',
        'fax': '',
        'phone': '',
    }
    if not c:
        return {}, atty_info

    address_lines = []
    lines = c.split('\n')
    for i, line in enumerate(lines):
        line = re.sub('Email:\s*', '', line).strip()
        line = re.sub('pro se', '', line, flags=re.I)
        if not line:
            continue
        try:
            validate_email(line)
        except ValidationError:
            # Not an email address, press on.
            pass
        else:
            # An email address.
            atty_info['email'] = line
            continue

        # Perhaps a phone/fax number?
        clean_line = re.sub(r'(\(|\)|\\|/|\s+)', '', line)
        if clean_line.startswith('Fax:'):
            clean_line = re.sub('Fax:', '', clean_line)
            m = phone_digits_re.search(clean_line)
            if m:
                atty_info['fax'] = normalize_us_phone_number(clean_line)
            continue
        else:
            m = phone_digits_re.search(clean_line)
            if m:
                atty_info['phone'] = normalize_us_phone_number(clean_line)
                continue

        # First line containing an ampersand? These are usually law firm names.
        if u'&' in line and i == 0:
            fallback_name = line
            continue

        has_chars = re.search('[a-zA-Z]', line)
        if has_chars:
            # Not email, phone, fax, and has at least one char.
            address_lines.append(line)

    mapping = {
        'Recipient': 'name',
        'AddressNumber': 'address1',
        'AddressNumberPrefix': 'address1',
        'AddressNumberSuffix': 'address1',
        'StreetName': 'address1',
        'StreetNamePreDirectional': 'address1',
        'StreetNamePreModifier': 'address1',
        'StreetNamePreType': 'address1',
        'StreetNamePostDirectional': 'address1',
        'StreetNamePostModifier': 'address1',
        'StreetNamePostType': 'address1',
        # When corner addresses are given, you have two streets in an address
        'SecondStreetName': 'address1',
        'SecondStreetNamePreDirectional': 'address1',
        'SecondStreetNamePreModifier': 'address1',
        'SecondStreetNamePreType': 'address1',
        'SecondStreetNamePostDirectional': 'address1',
        'SecondStreetNamePostModifier': 'address1',
        'SecondStreetNamePostType': 'address1',
        'CornerOf': 'address1',
        'IntersectionSeparator': 'address1',
        'LandmarkName': 'address1',
        'USPSBoxGroupID': 'address1',
        'USPSBoxGroupType': 'address1',
        'USPSBoxID': 'address1',
        'USPSBoxType': 'address1',
        'BuildingName': 'address2',
        'OccupancyType': 'address2',
        'OccupancyIdentifier': 'address2',
        'SubaddressIdentifier': 'address2',
        'SubaddressType': 'address2',
        'PlaceName': 'city',
        'StateName': 'state',
        'ZipCode': 'zip_code',
        'ZipPlus4': 'zip_code',
    }
    try:
        address_info, address_type = usaddress.tag(
            ', '.join(address_lines),
            tag_mapping=mapping,
        )
    except usaddress.RepeatedLabelError:
        logger.warn("Unable to parse address (RepeatedLabelError): %s" %
                    ', '.join(c.split('\n')))
        return {}, atty_info

    # We don't want this getting through to the database layer. Pop it.
    address_info.pop('NotAddress', None)

    if any([address_type == 'Ambiguous',
            'CountryName' in address_info]):
        logger.warn("Unable to parse address (Ambiguous address type): %s" %
                    ', '.join(c.split('\n')))
        return {}, atty_info

    if address_info.get('name') is None and fallback_name:
        address_info['name'] = fallback_name
    if address_info.get('state'):
        address_info['state'] = normalize_us_state(address_info['state'])

    address_info = normalize_address_info(dict(address_info))
    address_info['lookup_key'] = make_address_lookup_key(address_info)
    return address_info, atty_info
