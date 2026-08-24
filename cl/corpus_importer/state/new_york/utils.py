import logging
import re

from cl.lib.string_utils import normalize_dashes

logger = logging.getLogger(__name__)

# The Court of Appeals is the only New York court we scrape so far, and
# Juriscraper reports it with CourtListener's own ID.
NYCOA_COURT_ID: str = "ny"


def is_nycoa_court(court_id: str) -> bool:
    """Check if the given `court_id` belongs to the New York Court of Appeals.

    :param court_id: The court ID to check.
    :return: Whether the ID belongs to the New York Court of Appeals."""

    return court_id == NYCOA_COURT_ID


# <Case type>-<Year>-<Case number>, e.g. APL-2024-00177. The case type comes
# from a dropdown on the search form (APL, CTQ, JCR, ...), so the pattern
# accepts any short alphabetic prefix rather than enumerating them.
NYCOA_DN_RE = re.compile(r"[A-Z]{2,4}-\d{4}-\d{3,6}")


def make_docket_number_core(docket_number: str, /) -> str:
    """Normalize a New York Court of Appeals docket number.

    :param docket_number: The docket number to normalize.
    :return: The normalized docket number, or an empty string when the input
        holds no recognizable Court of Appeals docket number."""
    dn_clean = normalize_dashes(docket_number.strip().upper())
    if not dn_clean:
        return ""

    matches = NYCOA_DN_RE.findall(dn_clean)
    if not matches:
        logger.error(
            "Unable to find valid NYCoA docket number in string %s",
            docket_number,
        )
        return ""

    if len(matches) > 1:
        matches.sort()
        logger.warning(
            "Found multiple NYCoA docket numbers in string %s. Using %s",
            docket_number,
            matches[0],
        )

    return re.sub(r"[^a-z0-9]", "", matches[0].lower())
