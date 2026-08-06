"""Database choices for the vocabularies the Court-PASS scraper classifies into.

Juriscraper owns these vocabularies
(`juriscraper.state.new_york.nycourts_gov.vocabularies`) and does the
classifying; this module only turns them into Django choices. Each member
carries the integer `code` we store, so adding a member upstream widens the
choices here without renumbering anything already in the database.

`UNKNOWN` and `UNASSIGNED` are the two codes Juriscraper reserves. Juriscraper
reports both cases as `None` -- it has nothing to say -- and the raw string
stored beside each of these fields is what tells them apart:

* `UNKNOWN`: the Court stated nothing. No FILINGS row named the filing, the
  filing type implies no role, the file name carried no readable document type.
* `UNASSIGNED`: the Court stated something Juriscraper's vocabulary does not
  cover, which is the signal that a member needs adding upstream.
"""

from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    CourtVocabulary,
    FilingDocType,
    FilingRole,
    FilingType,
    IssueCategory,
    IssueSubcategory,
)

__all__ = [
    "FILING_DOCTYPE_CHOICES",
    "FILING_ROLE_CHOICES",
    "FILING_TYPE_CHOICES",
    "ISSUE_CATEGORY_CHOICES",
    "ISSUE_SUBCATEGORY_CHOICES",
    "UNASSIGNED",
    "UNKNOWN",
]

UNKNOWN = 0
"""The Court stated nothing for this field."""

UNASSIGNED = 999
"""The Court stated something Juriscraper's vocabulary does not cover."""


def _choices(
    vocabulary: type[CourtVocabulary],
) -> list[tuple[int, str]]:
    """Django choices for one Juriscraper vocabulary, bracketed by the two
    reserved codes."""
    return [
        (UNKNOWN, "Unknown"),
        *((member.code, member.label) for member in vocabulary),
        (UNASSIGNED, "Unassigned"),
    ]


FILING_TYPE_CHOICES = _choices(FilingType)
FILING_ROLE_CHOICES = _choices(FilingRole)
FILING_DOCTYPE_CHOICES = _choices(FilingDocType)
ISSUE_CATEGORY_CHOICES = _choices(IssueCategory)
ISSUE_SUBCATEGORY_CHOICES = _choices(IssueSubcategory)
