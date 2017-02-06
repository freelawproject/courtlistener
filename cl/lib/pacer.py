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
from localflavor.us.forms import phone_digits_re
from localflavor.us.us_states import STATES_NORMALIZED, USPS_CHOICES
from lxml import etree

from cl.corpus_importer.import_columbia.parse_judges import find_judge_names
from cl.lib.import_lib import find_person
from cl.lib.recap_utils import (
    get_docketxml_url_from_path, get_ia_document_url_from_path,
    get_local_document_url_from_path,
)
from cl.scrapers.tasks import get_page_count
from cl.search.models import Court, Docket, RECAPDocument, DocketEntry
from cl.people_db.models import Role, Party, AttorneyOrganization, PartyType, \
    Attorney

logger = logging.getLogger(__name__)


pacer_to_cl_ids = {
    # Maps PACER ids to their CL equivalents
    'azb': 'arb',         # Arizona Bankruptcy Court
    'cofc': 'uscfc',      # Court of Federal Claims
    'nysb-mega': 'nysb',  # Remove the mega thing
}
# Reverse dict of pacer_to_cl_ids
cl_to_pacer_ids = {v: k for k, v in pacer_to_cl_ids.items()}


class ParsingException(Exception):
    pass


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
        self.blocked, self.date_blocked = self.set_blocked_fields()

        # Non-parsed fields
        self.filepath_local = os.path.join('recap', self.path)
        self.filepath_ia = get_docketxml_url_from_path(self.path)

    def save(self, debug):
        """Save the item to the database, updating any existing items.

        Returns None if an error occurs.
        """
        required_fields = ['case_name', 'date_filed']
        for field in required_fields:
            if not getattr(self, field):
                logger.error("Missing required field: %s" % field)
                return None

        try:
            d = Docket.objects.get(
                Q(pacer_case_id=self.pacer_case_id) |
                Q(docket_number=self.docket_number),
                court=self.court,
            )
            # Add RECAP as a source if it's not already.
            if d.source in [Docket.DEFAULT, Docket.SCRAPER]:
                d.source = Docket.RECAP_AND_SCRAPER
            elif d.source == Docket.COLUMBIA:
                d.source = Docket.COLUMBIA_AND_RECAP
            elif d.source == Docket.COLUMBIA_AND_SCRAPER:
                d.source = Docket.COLUMBIA_AND_RECAP_AND_SCRAPER
        except Docket.DoesNotExist:
            d = Docket(source=Docket.RECAP)
        except Docket.MultipleObjectsReturned:
            logger.error("Got multiple results while attempting save.")
            return None

        for attr, v in self.__dict__.items():
            setattr(d, attr, v)

        if not debug:
            d.save()
            logger.info("Saved as Docket %s: https://www.courtlistener.com%s" %
                        (d.pk, d.get_absolute_url()))
        return d

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
                except (IntegrityError,
                        DocketEntry.MultipleObjectsReturned):
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
            d = RECAPDocument.objects.get(
                docket_entry=docket_entry,
                document_number=entry_number,
                # Use the attachment number if it is not 0, else use None.
                attachment_number=attachment_number or None,
            )
        except RECAPDocument.DoesNotExist:
            d = RECAPDocument(
                docket_entry=docket_entry,
                pacer_doc_id=pacer_document_id,
            )
        else:
            d.pacer_doc_id = pacer_document_id or d.pacer_doc_id

        d.date_upload = self.get_datetime_from_node(doc_node, 'upload_date')
        d.document_type = document_type or d.document_type
        d.document_number = entry_number

        # If we can't parse the availability node (it returns None), default it
        # to False.
        availability = self.get_bool_from_node(doc_node, 'available')
        d.is_available = False if availability is None else availability
        d.sha1 = self.get_str_from_node(doc_node, 'sha1')
        d.description = (self.get_str_from_node(doc_node, 'short_desc') or
                         d.description)
        if d.is_available:
            d.filepath_ia = get_ia_document_url_from_path(
                self.path, entry_number, attachment_number)
            d.filepath_local = os.path.join(
                'recap',
                get_local_document_url_from_path(self.path, entry_number,
                                                 attachment_number),
            )
            if d.page_count is None:
                extension = d.filepath_local.path.split('.')[-1]
                d.page_count = get_page_count(d.filepath_local.path, extension)
        if document_type == RECAPDocument.ATTACHMENT:
            d.attachment_number = attachment_number
        if not debug:
            try:
                d.save(do_extraction=False, index=False)
            except IntegrityError as e:
                # This happens when a pacer_doc_id has been wrongly set as
                # the document_number, see for example, document 19 and
                # document 00405193374 here: https://ia802300.us.archive.org/23/items/gov.uscourts.ca4.14-1872/gov.uscourts.ca4.14-1872.docket.xml
                logger.error("Unable to create RECAPDocument for document #%s, "
                             "attachment #%s on entry: %s due to "
                             "IntegrityError." % (d.document_number,
                                                  d.attachment_number,
                                                  d.docket_entry))
                return None
        return d

    @transaction.atomic
    def make_parties(self, docket, debug):
        """Pull out the parties and their attorneys and save them to the DB."""
        atty_obj_cache = {}

        # Get the most recent date on the docket, casting datetimes
        # if needed. We'll use this to have the most updated attorney info.
        newest_docket_date = max(
            [d for d in [docket.date_filed,
                         docket.date_terminated,
                         docket.date_last_filing] if d],
        )
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
                party = Party(
                    name=party_name,
                    extra_info=party_extra_info,
                )
                if not debug:
                    party.save()
            else:
                if party_extra_info and not debug:
                    party.extra_info = party_extra_info
                    party.save()

            # If the party type doesn't exist, make a new one.
            if not party.party_types.filter(docket=docket,
                                            name=party_type).exists():
                pt = PartyType(
                    docket=docket,
                    party=party,
                    name=party_type,
                )
                if not debug:
                    pt.save()

            atty_nodes = party_node.xpath('.//attorney_list/attorney')
            logger.info("Adding %s attorneys to the party." % len(atty_nodes))
            for atty_node in atty_nodes:
                atty_name = self.get_str_from_node(atty_node, 'attorney_name')
                logger.info("Adding attorney: '%s'" % atty_name)
                atty_contact_raw = self.get_str_from_node(atty_node, 'contact')
                atty_roles = self.get_str_from_node(atty_node, 'attorney_role')

                # Try to look up the atty object from an earlier iteration.
                try:
                    atty, atty_org_info, atty_info = atty_obj_cache['atty_name']
                except KeyError:
                    if 'see above' in atty_contact_raw.lower():
                        logger.info("Unable to get atty with 'see above' "
                                    "contact information.")
                        atty_contact_raw = ''

                    # New attorney for this docket. Look them up in DB or
                    # create new attorney if necessary.
                    atty_org_info, atty_info = normalize_attorney_contact(
                        atty_contact_raw, fallback_name=atty_name)
                    try:
                        # Find an atty with the same name and one of another
                        # several IDs. Important to add contact_raw here, b/c
                        # if it cannot be parsed, all other values are blank.
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
                        logger.info("Unable to find matching attorney. "
                                    "Creating a new one: %s" % atty_name)
                        atty = Attorney(name=atty_name,
                                        date_sourced=newest_docket_date,
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
                            atty.organizations.add(org)

                    atty_info_is_newer = (atty.date_sourced <= newest_docket_date)
                    if atty_info and atty_info_is_newer:
                        logger.info("Updating atty info because %s is more "
                                    "recent than %s." % (newest_docket_date,
                                                         atty.date_sourced))
                        atty.date_sourced = newest_docket_date
                        atty.contact_raw = atty_contact_raw
                        atty.email = atty_info['email']
                        atty.phone = atty_info['phone']
                        atty.fax = atty_info['fax']

                        if not debug:
                            atty.save()

                atty_roles = [normalize_attorney_role(r) for r in
                              atty_roles.split('\n') if r]
                atty_roles = [r for r in atty_roles if r]
                logger.info("Linking attorney '%s' to party '%s' via %s roles: "
                            "%s" % (atty_name, party_name, len(atty_roles),
                                    atty_roles))
                if not debug:
                    # Delete the old roles, replace with new.
                    Role.objects.filter(attorney=atty, party=party).delete()
                    Role.objects.bulk_create([
                        Role(role=atty_role, attorney=atty, party=party) for
                        atty_role in atty_roles
                    ])

    def get_court(self):
        """Extract the court from the XML and return it as a Court object"""
        court_str = self.case_details.xpath('court/text()')[0].strip()
        try:
            c = Court.objects.get(pk=pacer_to_cl_ids.get(court_str, court_str))
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
            logger.info("Couldn't get bool from path: %s" % path)
            return None
        except ValueError:
            logger.info("Couldn't convert text '%s' to int when making boolean "
                        "for path: %s" % (s, path))
            return None
        else:
            return bool(n)

    @staticmethod
    def get_str_from_node(node, path):
        try:
            s = node.xpath('%s/text()' % path)[0].strip()
        except IndexError:
            logger.info("Couldn't get string from path: %s" % path)
            return ''  # Return an empty string. Don't return None.
        else:
            return s

    def get_int_from_details(self, node):
        s = self.case_details.xpath('%s/text()' % node)[0].strip()
        try:
            return int(s)
        except ValueError:
            # Can't parse string to int
            logger.info("Couldn't get int for node %s" % node)
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
            logger.info("Couldn't get date from path: %s" % path)
            return None
        else:
            try:
                d = parser.parse(s)
            except ValueError:
                logger.info("Couldn't parse date: %s" % s)
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
            judge_names = find_judge_names(s)
            judges = []
            for judge_name in judge_names:
                judges.append(find_person(judge_name, self.court.pk,
                                          case_date=self.date_filed))
            judges = [c for c in judges if c is not None]
            if len(judges) == 0:
                logger.info("No judge for: %s" % (
                    (s, self.court.pk, self.date_filed),
                ))
                return None, s
            elif len(judges) == 1:
                return judges[0], s
            elif len(judges) > 1:
                logger.info("Too many judges found: %s" % len(judges))
                return None, s

    def set_blocked_fields(self):
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

        """
        bankruptcy_privacy_threshold = 500
        small_case = self.document_count <= bankruptcy_privacy_threshold
        if all([small_case, self.court.is_bankruptcy]):
            return True, date.today()
        return False, None


def normalize_party_types(t):
    """Normalize various party types to as few as possible."""
    t = t.lower()

    # Numerical types
    t = re.sub(r'defendant\s+\(\d+\)', r'defendant', t)
    t = re.sub(r'debtor\s+\d+', 'debtor', t)

    # Assorted other
    t = re.sub(r'(thirdparty|3rd pty|3rd party)', r'third party', t)
    t = re.sub(r'(fourthparty|4th pty|4th party)', r'fourth party', t)
    t = re.sub(r'counter-(defendant|claimaint)', r'counter \1', t)
    t = re.sub(r'\bus\b', 'u.s.', t)
    t = re.sub(r'u\. s\.', 'u.s.', t)
    t = re.sub(r'united states', 'u.s.', t)
    t = re.sub(r'jointadmin', 'jointly administered', t)
    t = re.sub(r'consolidated-debtor', 'consolidated debtor', t)
    t = re.sub(r'plaintiff-? consolidated', 'consolidated plaintiff', t)
    t = re.sub(r'defendant-? consolidated', 'consolidated defendant', t)
    t = re.sub(r'intervenor-plaintiff', 'intervenor plaintiff', t)
    t = re.sub(r'intervenor pla\b', 'intervenor plaintiff', t)
    t = re.sub(r'intervenor dft\b', 'intervenor defendant', t)

    return titlecase(t)


def normalize_attorney_role(r):
    """Normalize attorney roles into the valid set"""
    r = r.lower()

    # Bad values we can expect. Nuke these early so they don't cause problems.
    if any([r.startswith(u'bar status'),
            r.startswith(u'designation')]):
        return None

    if u'to be noticed' in r:
        return Role.ATTORNEY_TO_BE_NOTICED
    elif u'lead attorney' in r:
        return Role.ATTORNEY_LEAD
    elif u'sealed group' in r:
        return Role.ATTORNEY_IN_SEALED_GROUP
    elif u'pro hac vice' in r:
        return Role.PRO_HAC_VICE
    elif u'self- terminated' in r:
        return Role.SELF_TERMINATED
    elif u'terminated' in r:
        return Role.TERMINATED
    elif u'suspended' in r:
        return Role.SUSPENDED
    elif u'inactive' in r:
        return Role.INACTIVE
    elif u'disbarred' in r:
        return Role.DISBARRED

    raise ValueError(u"Unable to match role: %s" % r)


def normalize_us_state(state):
    """Convert state values to valid state postal abbreviations

    va --> VA
    Virginia --> VA

    Raises KeyError if state cannot be normalized.
    """
    abbreviations = [t[0] for t in USPS_CHOICES]
    if state in abbreviations:
        return state
    return STATES_NORMALIZED[state.lower()]


def make_lookup_key(address_info):
    """Strip anything that's not a character or number"""
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
    """Normalize various street address abbreviations

     - Titlecase where appropriate
     - Normalize street abbreviations (St --> Street, etc.)
    """
    fixes = OrderedDict((
        ('Street', 'St.'),
        ('Avenue', 'Ave.'),
        ('Boulevard', 'Blvd.'),
    ))

    for k, v in address_info.items():
        if k == 'state':
            continue
        address_info[k] = titlecase(v)

    for address_part in ['address1', 'address2']:
        a = address_info.get(address_part)
        if not a:
            continue

        for bad, good in fixes.items():
            a = re.sub(r'\b%s\b' % bad, good, a, flags=re.IGNORECASE)

        address_info[address_part] = a
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
        line = re.sub('pro se', '', line, re.I)
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
                atty_info['fax'] = clean_line
            continue
        else:
            m = phone_digits_re.search(clean_line)
            if m:
                atty_info['phone'] = clean_line
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
    address_info['lookup_key'] = make_lookup_key(address_info)
    return address_info, atty_info
