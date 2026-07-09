import logging
import re

from juriscraper.state.florida.courts import FloridaCourtID

from cl.lib.string_utils import normalize_dashes

logger = logging.getLogger(__name__)

FL_APPELLATE_COURT_ID: str = "fladistctapp"

FLORIDA_COURT_ID_MAP: dict[str, str] = {
    FloridaCourtID.SUPREME_COURT.value: "fla",
    FloridaCourtID.FIRST_COA.value: "fladistctapp1",
    FloridaCourtID.SECOND_COA.value: "fladistctapp2",
    FloridaCourtID.THIRD_COA.value: "fladistctapp3",
    FloridaCourtID.FOURTH_COA.value: "fladistctapp4",
    FloridaCourtID.FIFTH_COA.value: "fladistctapp5",
    FloridaCourtID.SIXTH_COA.value: "fladistctapp6",
}

# Non-comprehensive list of court IDs that can be handled by Florida make_docket_number_core
FLORIDA_COURT_IDS: set[str] = set(FLORIDA_COURT_ID_MAP.values()) | {
    FL_APPELLATE_COURT_ID
}


def is_florida_court(court_id: str) -> bool:
    """Check if the given `court_id` belongs to a Florida state court.

    :param court_id: The court ID to check.
    :return: Whether the ID belongs to a Florida state court."""

    return court_id in FLORIDA_COURT_IDS


# <District>D<Year>-<Case number>
FLORIDA_APPELLATE_DN_RE = re.compile(r"[1-6]D\d{4}-\d{4,5}")
# SC<Year>-<Case number>
FLORIDA_SUPREME_DN_RE = re.compile(r"SC\d{4}-\d{4,5}")


def make_docket_number_core(
    docket_number: str,
    /,
    court_id: str = FLORIDA_COURT_ID_MAP[FloridaCourtID.SUPREME_COURT.value],
) -> str:
    """Normalize Florida docket numbers.

    The `court_id` parameter helps determine what format to force.

    :param docket_number: The docket number to normalize.
    :param court_id: The court ID of the docket. Defaults to the Supreme Court.
    :return: The normalized Florida docket number."""
    if not is_florida_court(court_id):
        logger.error(
            "Cannot make Florida DN core from non-Florida court %s", court_id
        )
        return docket_number
    dn_clean = docket_number.strip().upper()
    if not docket_number:
        return ""
    dn_clean = normalize_dashes(docket_number)

    if court_id == FLORIDA_COURT_ID_MAP[FloridaCourtID.SUPREME_COURT.value]:
        pattern = FLORIDA_SUPREME_DN_RE
    elif court_id.startswith("fladistctapp"):
        pattern = FLORIDA_APPELLATE_DN_RE
    else:
        logger.error("Unsupported Florida court ID: %s", court_id)
        return docket_number

    matches = pattern.findall(dn_clean)

    if not matches:
        logger.error(
            "Unable to find valid Florida DN for court %s in string %s",
            court_id,
            docket_number,
        )
        return docket_number

    if len(matches) > 1:
        matches.sort()
        logger.warning(
            "Found multiple Florida DNs for court %s in string %s. Using %s",
            court_id,
            docket_number,
            matches[0],
        )
    not_alphanum_regex = re.compile(r"[^a-z0-9]")
    return not_alphanum_regex.sub("", matches[0].lower())
