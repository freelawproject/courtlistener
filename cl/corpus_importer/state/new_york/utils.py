import logging
import re

from django.db.models import IntegerChoices
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    CourtVocabulary,
)

from cl.corpus_importer.state.new_york.nycourts_gov import Unclassified
from cl.lib.string_utils import normalize_dashes
from cl.search.state.new_york.vocabularies import UNASSIGNED, UNKNOWN

logger = logging.getLogger(__name__)

NYCOA_COURT_ID: str = "ny"
NYCOA_DN_RE = re.compile(r"[A-Z]{2,4}-\d{4}-\d{3,6}")


def is_nycoa_court(court_id: str) -> bool:
    """Check if the given `court_id` belongs to the New York Court of Appeals.

    :param court_id: The court ID to check.
    :return: Whether the ID belongs to the New York Court of Appeals."""

    return court_id == NYCOA_COURT_ID


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


RESERVED_CODES: dict[Unclassified, int] = {
    Unclassified.UNKNOWN: UNKNOWN,
    Unclassified.UNASSIGNED: UNASSIGNED,
}
"""The code stored for each of the two readings that name no member."""


def mirrored_code(
    mirror: type[IntegerChoices], member: CourtVocabulary | Unclassified
) -> int:
    """The code CourtListener stores for a reading of a Juriscraper vocabulary
    it mirrors.

    Both kinds of reading map by name, since every mirror defines `UNKNOWN` and
    `UNASSIGNED` under the names `Unclassified` uses.

    :param mirror: CourtListener's mirror of the vocabulary.
    :param member: What the scrape schema classified the field as.
    :return: The mirrored code, or `UNASSIGNED` for a member not yet mirrored.
    """
    try:
        return int(mirror[member.name].value)
    except KeyError:
        logger.error(
            "Juriscraper's %s.%s is not mirrored in CourtListener; storing "
            "UNASSIGNED. Add the member to cl.search.state.new_york."
            "vocabularies.%s.",
            type(member).__name__,
            member.name,
            mirror.__name__,
        )
        return UNASSIGNED


def issue_code(member: CourtVocabulary | Unclassified) -> int:
    """The code CourtListener stores for a reading of one of the two issue
    vocabularies.

    Those two are too large to mirror, so their codes are Juriscraper's own
    rather than a mirror's; see `cl.search.state.new_york.vocabularies`.

    :param member: What the scrape schema classified the category or subcategory
        as.
    :return: The published code, or the reserved one for a reading that names no
        member.
    """
    if isinstance(member, Unclassified):
        return RESERVED_CODES[member]
    return member.code
