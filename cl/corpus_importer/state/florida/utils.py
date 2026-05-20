import logging
import re

from cl.lib.string_utils import normalize_dashes

logger = logging.getLogger(__name__)

# Non-comprehensive list of court IDs that can be handled by Florida make_docket_number_core
FLORIDA_COURT_IDS: set[str] = {
    "fl",
    "fladistctapp",
    "fladistctapp1",
    "fladistctapp2",
    "fladistctapp3",
    "fladistctapp4",
    "fladistctapp5",
    "fladistctapp6",
}


def is_florida_court(court_id: str) -> bool:
    """Check if the given `court_id` belongs to a Florida state court.

    :param court_id: The court ID to check.
    :return: Whether the ID belongs to a Florida state court."""

    return court_id in FLORIDA_COURT_IDS


# <District>D<Year>-<Case number>
FLORIDA_APPELLATE_DN_RE = re.compile(r"[1-6]D\d{4}-\d{4}")
# SC<Year>-<Case number>
FLORIDA_SUPREME_DN_RE = re.compile(r"SC\d{4}-\d{4}")


def make_docket_number_core(
    docket_number: str, /, court_id: str = "fl"
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
    docket_number = docket_number.strip().upper()
    if not docket_number:
        return ""
    docket_number = normalize_dashes(docket_number)

    if court_id == "fl":
        pattern = FLORIDA_SUPREME_DN_RE
    elif court_id.startswith("fladistctapp"):
        pattern = FLORIDA_APPELLATE_DN_RE
    else:
        logger.error("Unsupported Florida court ID: %s", court_id)
        return docket_number

    matches = pattern.findall(docket_number)

    if not matches:
        logger.error(
            "Unable to find valid Florida DN for court %s in string %s",
            court_id,
            docket_number,
        )
        return docket_number

    matches.sort()
    if len(matches) > 1:
        logger.warning(
            "Found multiple Florida DNs for court %s in string %s. Using %s",
            matches[0],
        )
    return matches[0]
