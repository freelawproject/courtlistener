import logging
import re

from django.db.models import IntegerChoices
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    CourtVocabulary,
    IssueCategory,
    IssueSubcategory,
)
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    FilingDocType as ScrapeFilingDocType,
)
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    FilingRole as ScrapeFilingRole,
)
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    FilingType as ScrapeFilingType,
)

from cl.lib.string_utils import normalize_dashes
from cl.search.state.new_york.vocabularies import (
    UNASSIGNED,
    UNKNOWN,
    FilingDocType,
    FilingRole,
    FilingType,
)

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


def _mirrored_code(
    mirror: type[IntegerChoices], member: CourtVocabulary
) -> int:
    """The code CourtListener stores for a member of a Juriscraper vocabulary
    it mirrors.

    :param mirror: CourtListener's mirror of the member's vocabulary.
    :param member: The member Juriscraper classified.
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


def filing_type_value(
    filing_type: ScrapeFilingType | None, raw_filing_type: str
) -> int:
    """The code for a filing's type.

    :param filing_type: The type the scraper classified.
    :param raw_filing_type: The string the FILINGS table printed, empty when no
        table row named this filing.
    :return: The type's code, `UNKNOWN` when no table row named the filing at
        all, or `UNASSIGNED` when the table named a type Juriscraper's
        vocabulary does not cover."""
    if filing_type is not None:
        return _mirrored_code(FilingType, filing_type)
    return UNASSIGNED if raw_filing_type.strip() else UNKNOWN


def filing_role_value(role: ScrapeFilingRole | None) -> int:
    """The code for a filing's party role.

    :param role: The role the scraper classified. None when the filing implies
        no role, and also None when the file name stated one it could not read.
    :return: The role's code, or `UNKNOWN`."""
    return UNKNOWN if role is None else _mirrored_code(FilingRole, role)


def filing_doctype_value(doctype: ScrapeFilingDocType | None) -> int:
    """The code for a filing's document type.

    :param doctype: The document type the scraper classified. None when the
        filing carries no document, and also None when the file name's type
        could not be read -- roughly 6% of names.
    :return: The document type's code, or `UNKNOWN`."""
    return (
        UNKNOWN if doctype is None else _mirrored_code(FilingDocType, doctype)
    )


def issue_category_value(
    category: IssueCategory | None, category_raw: str
) -> int:
    """The code for the category of an issue the Court assigned to a case.

    :param category: The category the scraper classified.
    :param category_raw: The issue as Court-PASS stated it.
    :return: The category's code, `UNKNOWN` when the Court stated no issue at
        all, or `UNASSIGNED` when it stated a category Juriscraper's vocabulary
        does not cover."""
    if category is not None:
        return category.code
    return UNASSIGNED if category_raw.strip() else UNKNOWN


def issue_subcategory_value(
    subcategory: IssueSubcategory | None, category_raw: str
) -> int:
    """The code for the subcategory of an issue the Court assigned to a case.

    :param subcategory: The subcategory the scraper classified. None both when
        the Court stated a bare category and when it stated a subcategory the
        vocabulary does not cover.
    :param category_raw: The issue as Court-PASS stated it. Whether it holds the
        double dash the Court joins the two halves with is what separates those
        two cases.
    :return: The subcategory's code, `UNKNOWN` when the Court stated a bare
        category, or `UNASSIGNED` when it stated one that is not covered."""
    if subcategory is not None:
        return subcategory.code
    _, _, stated = category_raw.partition("--")
    return UNASSIGNED if stated.strip() else UNKNOWN
