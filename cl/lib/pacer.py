import logging
import re
from collections import OrderedDict
from datetime import date

import usaddress
from dateutil import parser
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from juriscraper.lib.string_utils import titlecase
from juriscraper.pacer import AppellateDocketReport, DocketReport, \
    DocketHistoryReport, InternetArchive, CaseQuery, ClaimsRegister
from localflavor.us.forms import phone_digits_re
from localflavor.us.us_states import STATES_NORMALIZED, USPS_CHOICES

from cl.people_db.models import Role, AttorneyOrganization
from cl.recap.mergers import add_bankruptcy_data_to_docket, \
    add_claims_to_docket
from cl.recap.models import UPLOAD_TYPE
from cl.search.models import Court, Docket

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


def get_first_missing_de_date(d):
    """When buying dockets use this function to figure out which docket entries
    we already have, starting at the first item. Since PACER only allows you to
    do a range of docket entries, this allows us to figure out a later starting
    point for our query.

    For example, if we have documents 1-32 already in the DB, we can save some
    money by only getting items 33 and on.

    :param d: The Docket object to check.
    :returns date: The starting date that should be used in your query. If the
    docket has no entries, returns 1960/1/1. If the docket has entries, returns
    the date of the highest available item.
    """
    # Get docket entry numbers for items that *have* docket entry descriptions.
    # This ensures that we don't count RSS items towards the docket being
    # complete, since we only have the short description for those.
    de_number_tuples = list(d.docket_entries.exclude(description='').order_by(
        'entry_number'
    ).values_list('entry_number', 'date_filed'))
    de_numbers = [i[0] for i in de_number_tuples if i[0]]

    if len(de_numbers) > 0:
        # Get the earliest missing item
        end = de_numbers[-1]
        missing_items = sorted(set(range(1, end + 1)).difference(de_numbers))
        if missing_items:
            if missing_items[0] == 1:
                return date(1960, 1, 1)
            else:
                previous = missing_items[0] - 1
                for entry_number, entry_date in de_number_tuples:
                    if entry_number == previous:
                        return entry_date
        else:
            # None missing, but we can start after the highest de we know.
            return de_number_tuples[-1][1]
    return date(1960, 1, 1)


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
    bankruptcy_court = docket.court.jurisdiction in \
                                    Court.BANKRUPTCY_JURISDICTIONS
    if all([small_case, bankruptcy_court]):
        return True, date.today()
    return False, None


def process_docket_data(d, filepath, report_type):
    """Process docket data file.

    :param d: A docket object to work on.
    :param filepath: The path to a saved HTML file containing docket or docket
    history report data.
    :param report_type: Whether it's a docket or a docket history report.
    """
    from cl.recap.mergers import add_docket_entries, \
        add_parties_and_attorneys, update_docket_appellate_metadata, \
        update_docket_metadata
    if report_type == UPLOAD_TYPE.DOCKET:
        report = DocketReport(map_cl_to_pacer_id(d.court_id))
    elif report_type == UPLOAD_TYPE.DOCKET_HISTORY_REPORT:
        report = DocketHistoryReport(map_cl_to_pacer_id(d.court_id))
    elif report_type == UPLOAD_TYPE.APPELLATE_DOCKET:
        report = AppellateDocketReport(map_cl_to_pacer_id(d.court_id))
    elif report_type == UPLOAD_TYPE.IA_XML_FILE:
        report = InternetArchive()
    elif report_type == UPLOAD_TYPE.CASE_REPORT_PAGE:
        report = CaseQuery(map_cl_to_pacer_id(d.court_id))
    elif report_type == UPLOAD_TYPE.CLAIMS_REGISTER:
        report = ClaimsRegister(map_cl_to_pacer_id(d.court_id))
    else:
        raise NotImplementedError("The report type with id '%s' is not yet "
                                  "supported. Perhaps you need to add it?" %
                                  report_type)
    with open(filepath, 'r') as f:
        text = f.read().decode('utf-8')
    report._parse_text(text)
    data = report.data
    if data == {}:
        return None

    if report_type == UPLOAD_TYPE.CLAIMS_REGISTER:
        add_bankruptcy_data_to_docket(d, data)
        add_claims_to_docket(d, data['claims'])
    else:
        update_docket_metadata(d, data)
        d, og_info = update_docket_appellate_metadata(d, data)
        if og_info is not None:
            og_info.save()
            d.originating_court_information = og_info
        d.save()
        if data.get('docket_entries'):
            add_docket_entries(d, data['docket_entries'])
    if report_type in (UPLOAD_TYPE.DOCKET, UPLOAD_TYPE.APPELLATE_DOCKET,
                       UPLOAD_TYPE.IA_XML_FILE):
        add_parties_and_attorneys(d, data['parties'])
    return d.pk


def normalize_attorney_role(r):
    """Normalize attorney roles into the valid set"""
    role = {'role': None, 'date_action': None, 'role_raw': r}

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
     - Remove/normalize a variety of words that add little meaning and
       are often omitted.
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
            u', '.join(address_lines),
            tag_mapping=mapping,
        )
    except (usaddress.RepeatedLabelError, UnicodeEncodeError):
        # See https://github.com/datamade/probableparsing/issues/2 for why we
        # catch the UnicodeEncodeError. Oy.
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
