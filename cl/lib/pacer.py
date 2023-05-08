import logging
import pickle
import re
import socket
from collections import OrderedDict
from datetime import date, datetime, timezone
from typing import Mapping, Optional, TypedDict

import requests
import usaddress
from dateutil import parser
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from juriscraper.lib.string_utils import titlecase
from juriscraper.pacer import (
    AppellateDocketReport,
    CaseQuery,
    ClaimsRegister,
    DocketHistoryReport,
    DocketReport,
    InternetArchive,
)
from localflavor.us.us_states import STATES_NORMALIZED, USPS_CHOICES

from cl.lib.redis_utils import make_redis_interface
from cl.people_db.models import AttorneyOrganization, Role
from cl.people_db.types import RoleType
from cl.recap.models import UPLOAD_TYPE
from cl.search.models import Court, Docket

logger = logging.getLogger(__name__)

phone_digits_re = re.compile(r"^(?:1-?)?(\d{3})[-.]?(\d{3})[-.]?(\d{4})$")


pacer_to_cl_ids = {
    # Maps PACER ids to their CL equivalents
    "azb": "arb",  # Arizona Bankruptcy Court
    "cofc": "uscfc",  # Court of Federal Claims
    "neb": "nebraskab",  # Nebraska Bankruptcy
    "nysb-mega": "nysb",  # Remove the mega thing
}

# Reverse dict of pacer_to_cl_ids
cl_to_pacer_ids = {v: k for k, v in pacer_to_cl_ids.items() if v != "nysb"}


def map_pacer_to_cl_id(pacer_id):
    return pacer_to_cl_ids.get(pacer_id, pacer_id)


def map_cl_to_pacer_id(cl_id):
    return cl_to_pacer_ids.get(cl_id, cl_id)


def lookup_and_save(new, debug=False):
    """Merge new docket info into the database.

    Start by attempting to lookup an existing Docket. If that's not found,
    create a new one. Either way, merge all the attributes of `new` into the
    Docket found, and then save the Docket.

    Returns None if an error occurs, else, return the new or updated Docket.
    """
    try:
        d = Docket.objects.get(
            pacer_case_id=new.pacer_case_id, court=new.court
        )
    except (Docket.DoesNotExist, Docket.MultipleObjectsReturned):
        d = None

    if d is None:
        ds = Docket.objects.filter(
            docket_number=new.docket_number, court=new.court
        ).order_by("-date_filed")
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
        logger.info(
            "Saved as Docket %s: https://www.courtlistener.com%s"
            % (d.pk, d.get_absolute_url())
        )
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
    de_number_tuples = list(
        d.docket_entries.exclude(description="")
        .order_by("entry_number")
        .values_list("entry_number", "date_filed")
    )
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


def get_blocked_status(docket: Docket, count_override: int | None = None):
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
    if getattr(docket, "blocked", False):
        # Short circuit. This function can only make things blocked that were
        # previously public.
        return docket.blocked, docket.date_blocked

    bankruptcy_privacy_threshold = 500
    if count_override is not None:
        count = count_override
    elif docket.pk:
        count = docket.docket_entries.all().count()
    else:
        count = 0
    small_case = count <= bankruptcy_privacy_threshold
    bankruptcy_court = (
        docket.court.jurisdiction in Court.BANKRUPTCY_JURISDICTIONS
    )
    if all([small_case, bankruptcy_court]):
        return True, date.today()
    return False, None


def process_docket_data(
    d: Docket,
    report_type: int,
    filepath: str | None = None,
) -> Optional[int]:
    """Process docket data file.

    :param d: A docket object to work on.
    :param report_type: Whether it's a docket or a docket history report.
    :param filepath: A local path where the item can be found. If not provided,
    the filepath_local field of the docket object will be attempted.
    """
    from cl.recap.mergers import (
        add_bankruptcy_data_to_docket,
        add_claims_to_docket,
        add_docket_entries,
        add_parties_and_attorneys,
        update_docket_appellate_metadata,
        update_docket_metadata,
    )

    court_id = map_cl_to_pacer_id(d.court_id)
    if report_type == UPLOAD_TYPE.DOCKET:
        report = DocketReport(court_id)
    elif report_type == UPLOAD_TYPE.DOCKET_HISTORY_REPORT:
        report = DocketHistoryReport(court_id)
    elif report_type == UPLOAD_TYPE.APPELLATE_DOCKET:
        report = AppellateDocketReport(court_id)
    elif report_type == UPLOAD_TYPE.IA_XML_FILE:
        report = InternetArchive(court_id)
    elif report_type == UPLOAD_TYPE.CASE_REPORT_PAGE:
        report = CaseQuery(court_id)
    elif report_type == UPLOAD_TYPE.CLAIMS_REGISTER:
        report = ClaimsRegister(court_id)
    else:
        raise NotImplementedError(
            "The report type with id '%s' is not yet "
            "supported. Perhaps you need to add it?" % report_type
        )

    if filepath:
        with open(filepath, "r") as f:
            text = f.read()
    else:
        # This is an S3 path, so get it remotely.
        text = d.filepath_local.read().decode()

    report._parse_text(text)
    data = report.data
    if data == {}:
        return None

    if report_type == UPLOAD_TYPE.CLAIMS_REGISTER:
        add_bankruptcy_data_to_docket(d, data)
        add_claims_to_docket(d, data["claims"])
    else:
        update_docket_metadata(d, data)
        d, og_info = update_docket_appellate_metadata(d, data)
        if og_info is not None:
            og_info.save()
            d.originating_court_information = og_info
        d.save()
        if data.get("docket_entries"):
            add_docket_entries(d, data["docket_entries"])
    if report_type in (
        UPLOAD_TYPE.DOCKET,
        UPLOAD_TYPE.APPELLATE_DOCKET,
        UPLOAD_TYPE.IA_XML_FILE,
    ):
        add_parties_and_attorneys(d, data["parties"])
    return d.pk


def normalize_attorney_role(r: str) -> RoleType:
    """Normalize attorney roles into the valid set"""
    role: RoleType = {"role": None, "date_action": None, "role_raw": r}

    r = r.lower()
    # Bad values we can expect. Nuke these early so they don't cause problems.
    if any([r.startswith("bar status"), r.startswith("designation")]):
        return role

    if "to be noticed" in r:
        role["role"] = Role.ATTORNEY_TO_BE_NOTICED
    elif "lead attorney" in r:
        role["role"] = Role.ATTORNEY_LEAD
    elif "sealed group" in r:
        role["role"] = Role.ATTORNEY_IN_SEALED_GROUP
    elif "pro hac vice" in r:
        role["role"] = Role.PRO_HAC_VICE
    elif "self- terminated" in r:
        role["role"] = Role.SELF_TERMINATED
    elif "terminated" in r:
        role["role"] = Role.TERMINATED
    elif "suspended" in r:
        role["role"] = Role.SUSPENDED
    elif "inactive" in r:
        role["role"] = Role.INACTIVE
    elif "disbarred" in r:
        role["role"] = Role.DISBARRED

    try:
        role["date_action"] = parser.parse(r, fuzzy=True).date()
    except ValueError:
        role["date_action"] = None

    return role


def normalize_us_phone_number(phone):
    """Tidy up phone numbers so they're nice."""
    phone = re.sub(r"(\(|\)|\s+)", "", phone)
    m = phone_digits_re.search(phone)
    if m:
        return f"({m.group(1)}) {m.group(2)}-{m.group(3)}"
    return ""


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
        state = ""
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
        r"atty.": "",
        r"and": "",  # These are often used instead of & in firm names.
        r"boulevard": "blvd",
        r"llp": "",
        r"offices": "office",
        r"pc": "",
        r"p\.c\.": "",
        r"pa": "",
        r"p\.a\.": "",
        r"post office box": "P.O. Box",
        r"Ste": "Suite",
    }
    for k, v in sorted_info.items():
        for bad, good in fixes.items():
            v = re.sub(r"\b%s\b" % bad, good, v, flags=re.IGNORECASE)
        sorted_info[k] = v
    key = "".join(sorted_info.values())
    return re.sub(r"[^a-z0-9]", "", key.lower())


def normalize_address_info(address_info):
    """Normalize various address components"""

    # Titlecase where appropriate
    for k, v in address_info.items():
        if k == "state":
            continue
        address_info[k] = titlecase(v)

    # Normalize street abbreviations (St --> Street, etc.)
    fixes = OrderedDict(
        (("Street", "St."), ("Avenue", "Ave."), ("Boulevard", "Blvd."))
    )
    for address_part in ["address1", "address2"]:
        a = address_info.get(address_part)
        if not a:
            continue

        for bad, good in fixes.items():
            a = re.sub(r"\b%s\b" % bad, good, a, flags=re.IGNORECASE)

        address_info[address_part] = a

    # Nuke any zip code that's longer than allowed in the DB (usually caused by
    # phone numbers)
    zip_code_field = AttorneyOrganization._meta.get_field("zip_code")
    if len(address_info.get("zip_code", "")) > zip_code_field.max_length:
        address_info["zip_code"] = ""
    return address_info


def normalize_attorney_contact(c, fallback_name=""):
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
        "email": "",
        "fax": "",
        "phone": "",
    }
    if not c:
        return {}, atty_info

    address_lines = []
    lines = c.split("\n")
    for i, line in enumerate(lines):
        line = re.sub(r"Email:\s*", "", line).strip()
        line = re.sub("pro se", "", line, flags=re.I)
        if not line:
            continue
        try:
            validate_email(line)
        except ValidationError:
            # Not an email address, press on.
            pass
        else:
            # An email address.
            atty_info["email"] = line
            continue

        # Perhaps a phone/fax number?
        clean_line = re.sub(r"(\(|\)|\\|/|\s+)", "", line)
        if clean_line.startswith("Fax:"):
            clean_line = re.sub("Fax:", "", clean_line)
            m = phone_digits_re.search(clean_line)
            if m:
                atty_info["fax"] = normalize_us_phone_number(clean_line)
            continue
        else:
            m = phone_digits_re.search(clean_line)
            if m:
                atty_info["phone"] = normalize_us_phone_number(clean_line)
                continue

        # First line containing an ampersand? These are usually law firm names.
        if "&" in line and i == 0:
            fallback_name = line
            continue

        has_chars = re.search("[a-zA-Z]", line)
        if has_chars:
            # Not email, phone, fax, and has at least one char.
            address_lines.append(line)

    mapping = {
        "Recipient": "name",
        "AddressNumber": "address1",
        "AddressNumberPrefix": "address1",
        "AddressNumberSuffix": "address1",
        "StreetName": "address1",
        "StreetNamePreDirectional": "address1",
        "StreetNamePreModifier": "address1",
        "StreetNamePreType": "address1",
        "StreetNamePostDirectional": "address1",
        "StreetNamePostModifier": "address1",
        "StreetNamePostType": "address1",
        # When corner addresses are given, you have two streets in an address
        "SecondStreetName": "address1",
        "SecondStreetNamePreDirectional": "address1",
        "SecondStreetNamePreModifier": "address1",
        "SecondStreetNamePreType": "address1",
        "SecondStreetNamePostDirectional": "address1",
        "SecondStreetNamePostModifier": "address1",
        "SecondStreetNamePostType": "address1",
        "CornerOf": "address1",
        "IntersectionSeparator": "address1",
        "LandmarkName": "address1",
        "USPSBoxGroupID": "address1",
        "USPSBoxGroupType": "address1",
        "USPSBoxID": "address1",
        "USPSBoxType": "address1",
        "BuildingName": "address2",
        "OccupancyType": "address2",
        "OccupancyIdentifier": "address2",
        "SubaddressIdentifier": "address2",
        "SubaddressType": "address2",
        "PlaceName": "city",
        "StateName": "state",
        "ZipCode": "zip_code",
        "ZipPlus4": "zip_code",
    }
    try:
        address_info, address_type = usaddress.tag(
            ", ".join(address_lines), tag_mapping=mapping
        )
    except (usaddress.RepeatedLabelError, UnicodeEncodeError):
        # See https://github.com/datamade/probableparsing/issues/2 for why we
        # catch the UnicodeEncodeError. Oy.
        logger.warning(
            "Unable to parse address (RepeatedLabelError): %s"
            % ", ".join(c.split("\n"))
        )
        return {}, atty_info

    # We don't want this getting through to the database layer. Pop it.
    address_info.pop("NotAddress", None)

    if any([address_type == "Ambiguous", "CountryName" in address_info]):
        logger.warning(
            "Unable to parse address (Ambiguous address type): %s"
            % ", ".join(c.split("\n"))
        )
        return {}, atty_info

    if address_info.get("name") is None and fallback_name:
        address_info["name"] = fallback_name
    if address_info.get("state"):
        address_info["state"] = normalize_us_state(address_info["state"])

    address_info = normalize_address_info(dict(address_info))
    address_info["lookup_key"] = make_address_lookup_key(address_info)
    return address_info, atty_info


class ConnectionType(TypedDict):
    connection_ok: bool
    status_code: int | None
    date_time: datetime


def check_pacer_court_connectivity(court_id: str) -> ConnectionType:
    """Check PACER connection status for the given court.

    :param court_id: The court ID to check.
    :returns: A dict with the court connection status.
    """

    url = f"https://ecf.{court_id}.uscourts.gov/"

    connection_ok = False
    status_code = None
    try:
        r = requests.get(url, timeout=5)
        status_code = r.status_code
        r.raise_for_status()
        connection_ok = True
    except requests.exceptions.RequestException as e:
        connection_ok = False

    blocked_dict: ConnectionType = {
        "connection_ok": connection_ok,
        "status_code": status_code,
        "date_time": datetime.now(timezone.utc),
    }
    return blocked_dict


def get_or_cache_pacer_court_status(court_id: str, server_ip: str) -> bool:
    """Get the court status from Redis or cache it if it's not there.

    :param court_id: The court ID to check.
    :param server_ip: The server IP address.
    :return: True if connection was successful, False otherwise.
    """

    court_status_key = f"status:pacer:court.{court_id}:ip.{server_ip}"
    r = make_redis_interface("CACHE", decode_responses=False)
    pickle_status = r.get(court_status_key)
    if pickle_status:
        court_status = pickle.loads(pickle_status)
        return court_status

    # Unable to find court_status in cache, getting it from request.
    connection_info = check_pacer_court_connectivity(court_id)
    current_status = connection_info["connection_ok"]

    # Stores court connection status with court ID and server IP as key.
    # 30 seconds expiration time.
    status_expiration = 30
    r.set(court_status_key, pickle.dumps(current_status), ex=status_expiration)
    if connection_info["connection_ok"]:
        return True

    # If court connection failed, log the error and return False.
    log_pacer_court_connection(connection_info, court_id, server_ip)
    return False


def log_pacer_court_connection(
    connection_info: ConnectionType,
    court_id: str,
    server_ip: str,
) -> None:
    """Log the problem with the court in Redis.

    :param connection_info: A dict as returned by
    check_pacer_court_connectivity method.
    :param court_id: The court ID.
    :param server_ip: The server IP address.
    :return: None
    """
    r = make_redis_interface("STATS")
    pipe = r.pipeline()
    d = connection_info["date_time"].date().isoformat()
    t = connection_info["date_time"].time().isoformat()
    ip_key = f"pacer_log:c:{court_id}:server_ip:{server_ip}:d:{d}.ip_error"

    status_code = connection_info["status_code"]
    if status_code is None:
        status_code = 0
    if connection_info["connection_ok"] is True:
        connection_ok = "True"
    else:
        connection_ok = "False"

    log_info: Mapping[str | bytes, str | int] = {
        "connection_ok": connection_ok,
        "status_code": status_code,
        "time": t,
    }
    pipe.hset(ip_key, mapping=log_info)
    pipe.expire(ip_key, 60 * 60 * 24 * 14)  # Two weeks
    pipe.execute()


def is_pacer_court_accessible(court_id: str) -> bool:
    """Check the connectivity for the given court.

    :param court_id: The court ID to check.
    :return: True if connection was successful, False otherwise.
    """

    pacer_court_id = map_cl_to_pacer_id(court_id)
    # Get the IP address of the current node.
    hostname = socket.gethostname()
    ip_addr = socket.gethostbyname(hostname)

    court_status = get_or_cache_pacer_court_status(pacer_court_id, ip_addr)
    return court_status
