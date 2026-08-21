"""The schema of Court-PASS (nycourts.gov) data that the New York Court of Appeals
mergers consume.
"""

import logging
from datetime import date
from enum import Enum
from functools import partial
from typing import Annotated, Any, ClassVar

from juriscraper.state.docket import (
    Docket,
    DocketEntry,
    DocketTransfer,
    Document,
    Party,
    Representative,
)
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    CourtVocabulary,
    FilingDocType,
    FilingRole,
    FilingType,
    IssueCategory,
    IssueSubcategory,
)
from pydantic import BaseModel, BeforeValidator, model_validator

logger = logging.getLogger(__name__)

__all__ = [
    "NYCoAAttorney",
    "NYCoACase",
    "NYCoAFile",
    "NYCoDocketEntry",
    "NYCoAIssue",
    "NYCoAParty",
    "Unclassified",
]


class Unclassified(Enum):
    """Why a vocabulary field on one of these models names no member.

    Every vocabulary field below holds either a Juriscraper member or one of
    these, never `None`, so that a merger reading one of these models never has
    to ask what nothing means.

    These two names are the ones the mirrors in
    `cl.search.state.new_york.vocabularies` reserve, which is what lets
    `cl.corpus_importer.state.new_york.utils.mirrored_code` map a reading of
    either kind onto a stored code the same way.
    """

    UNKNOWN = "unknown"
    """The Court stated nothing for this field."""

    UNASSIGNED = "unassigned"
    """The Court stated something Juriscraper's vocabulary does not cover,
    which is the signal that a member needs adding."""


def _classify[Vocabulary: CourtVocabulary](
    vocabulary: type[Vocabulary], value: Any
) -> Vocabulary | Unclassified:
    """The vocabulary member `value` names, or why there is none.
    Logging for values we might want to add to our classifiers.

    :param vocabulary: The vocabulary to look `value` up in.
    :param value: Whatever the scrape stated. `None` is `UNKNOWN`; members of
        `vocabulary` and of `Unclassified` pass through untouched; and the
        strings either kind of member serializes as read back as that member.
        So this is safe to apply to a model built in Python and to one read
        back from a dump, as well as to one parsed from a scrape.
    :return: The member, or why the vocabulary names none.
    """
    if isinstance(value, Unclassified | vocabulary):
        return value
    if not value:
        return Unclassified.UNKNOWN
    try:
        return vocabulary(value)
    except ValueError:
        pass
    try:
        # An `Unclassified` member dumps as its own value, so a model read back
        # from a dump states one of those where a scrape states the Court's
        # wording. No vocabulary covers either string, so this cannot shadow a
        # reading the Court stated.
        return Unclassified(value)
    except ValueError:
        pass
    logger.warning(
        "Court-PASS stated %s %r, which Juriscraper's vocabulary does not "
        "cover; recording it as unassigned. Add the member to "
        "juriscraper.state.new_york.nycourts_gov.vocabularies.%s.",
        vocabulary.__name__,
        value,
        vocabulary.__name__,
    )
    return Unclassified.UNASSIGNED


ClassifiedFilingRole = Annotated[
    FilingRole | Unclassified, BeforeValidator(partial(_classify, FilingRole))
]
ClassifiedFilingDocType = Annotated[
    FilingDocType | Unclassified,
    BeforeValidator(partial(_classify, FilingDocType)),
]
ClassifiedFilingType = Annotated[
    FilingType | Unclassified, BeforeValidator(partial(_classify, FilingType))
]
ClassifiedIssueCategory = Annotated[
    IssueCategory | Unclassified,
    BeforeValidator(partial(_classify, IssueCategory)),
]
ClassifiedIssueSubcategory = Annotated[
    IssueSubcategory | Unclassified,
    BeforeValidator(partial(_classify, IssueSubcategory)),
]


class NYCoAFile(Document):
    """A file published on a Court-PASS filing-detail page.

    :ivar file_name: The name of the file as Court-PASS published it.
    :ivar content_type: The MIME type of the file, when known. Court-PASS
        publishes PDFs along with playlist files for oral argument recordings.
    :ivar available: Whether the file can be downloaded. ``False`` for sealed
        files and files the site lists but does not serve.
    :ivar doc_role: The party role the file name states. ``UNKNOWN`` when the
        name does not follow the Court's naming convention, and ``UNASSIGNED``
        when it states a role the vocabulary does not cover.
    :ivar doc_party: The party name encoded in the file name.
    :ivar doc_type: The document type the file name states. The
        ``_``-prefixed members are court output rather than a filing.
        ``UNKNOWN`` and ``UNASSIGNED`` on the same terms as ``doc_role``.
    :ivar volume: Volume number, for a record or appendix spanning volumes.
    :ivar part: Part number, for a volume that is itself split.
    :ivar local_path: Where the scraper stored the downloaded file, as a key in
        the same bucket `NYCoADocument.filepath_local` is stored in. Empty for a
        file the scraper did not fetch, a sealed one among them. Court-PASS
        serves a document only to the scraper, so this is the only way
        CourtListener learns where the file is; the merge points
        `filepath_local` straight at it, since it is already in the right
        bucket and needs no fetching.
    """

    # Court-PASS serves files through form postbacks rather than addressable
    # URLs, so nothing ever states one. Declaring the `url` the standard docket
    # format requires as a `ClassVar` drops it from the model's fields, which is
    # what `NYCoADocument` does with the column: it cannot be set, is not dumped,
    # and no merger reads it -- `NYCoADocumentMerger` subclasses `Merger` rather
    # than the shared `DocumentMerger`, which is the only thing that would.
    # pyrefly: ignore[bad-override]
    url: ClassVar[str] = ""
    file_name: str
    content_type: str = ""
    available: bool = False
    doc_role: ClassifiedFilingRole = Unclassified.UNKNOWN
    doc_party: str = ""
    doc_type: ClassifiedFilingDocType = Unclassified.UNKNOWN
    volume: int | None = None
    part: int | None = None
    local_path: str = ""


class NYCoDocketEntry(DocketEntry[NYCoAFile]):
    """A filing on a Court-PASS docket.

    :ivar docket_entry_id: The scraper's identifier for this filing, unique
        within the docket and stable across scrapes.
    :ivar entry_index: Position of this filing in the source listing.
        Reproduces display order but shifts between scrapes, so it is not an
        identifier.
    :ivar raw_filing_type: The filing type exactly as the FILINGS table
        rendered it (e.g. ``Appellant Brief``). Blank when no table row listed
        this filing, which is what marks a filing as reconstructed.
    :ivar entry_filing_type: The classified filing type. ``UNKNOWN`` when no
        table row named this filing, ``UNASSIGNED`` when the scraper's
        vocabulary does not cover what the table named; see
        ``_tell_unlisted_from_uncovered``.
    :ivar party: Name of the party associated with this filing.
    :ivar date_filed: The date Court-PASS recorded the filing as received.
        ``None`` on a filing reconstructed from a document, since the file list
        carries no dates.
    :ivar date_due: The date Court-PASS recorded the filing as due.
    :ivar entry_role: The party role for this filing. ``UNKNOWN`` when the
        filing type implies no role, ``UNASSIGNED`` when it implies one the
        vocabulary does not cover.
    :ivar entry_doctype: The document type for this filing. The ``_``-prefixed
        members are court output rather than a party filing. ``UNKNOWN`` and
        ``UNASSIGNED`` on the same terms as ``entry_role``.
    """

    date_filed: date | None = None
    docket_entry_id: str
    entry_index: int
    raw_filing_type: str
    entry_filing_type: ClassifiedFilingType = Unclassified.UNKNOWN
    party: str = ""
    date_due: date | None = None
    entry_role: ClassifiedFilingRole = Unclassified.UNKNOWN
    entry_doctype: ClassifiedFilingDocType = Unclassified.UNKNOWN

    @model_validator(mode="after")
    def _tell_unlisted_from_uncovered(self) -> "NYCoDocketEntry":
        """Separate a filing no FILINGS row named from one whose row named a
        type the vocabulary does not cover.
        """
        if (
            self.entry_filing_type is Unclassified.UNKNOWN
            and self.raw_filing_type.strip()
        ):
            self.entry_filing_type = Unclassified.UNASSIGNED
        return self

class NYCoAIssue(BaseModel):
    """An issue the Court of Appeals assigned to a case, classified.

    :ivar category_raw: The issue exactly as Court-PASS stated it, its category
        and subcategory joined by a double dash (e.g.
        ``Judgments--Confession of Judgment``).
    :ivar category: The classified category. ``UNASSIGNED`` when the scraper's
        vocabulary does not cover what the Court stated.
    :ivar subcategory: The classified subcategory. ``UNKNOWN`` when the Court
        stated a bare category -- roughly 13% of issues -- and ``UNASSIGNED``
        when the vocabulary does not cover the one it stated; see
        ``_tell_unstated_from_uncovered``.
    :ivar detail: The Court's description of the issue. Empty when Court-PASS
        stated none, which happens on roughly 4% of the issues observed.
    """

    category_raw: str
    category: ClassifiedIssueCategory = Unclassified.UNKNOWN
    subcategory: ClassifiedIssueSubcategory = Unclassified.UNKNOWN
    detail: str = ""

    @model_validator(mode="after")
    def _tell_unstated_from_uncovered(self) -> "NYCoAIssue":
        """Separate a half of the issue the Court did not state from one it
        stated in words the vocabulary does not cover.

        Juriscraper reports both as `None`, so `_classify` can only read them
        both as `UNKNOWN`. `category_raw` is the one thing that tells them
        apart: the Court joins the two halves with a double dash, so an issue
        stated at all has a category, and one stated as a bare category has no
        subcategory.
        """
        stated_category, _, stated_subcategory = self.category_raw.partition(
            "--"
        )
        if self.category is Unclassified.UNKNOWN and stated_category.strip():
            self.category = Unclassified.UNASSIGNED
        if (
            self.subcategory is Unclassified.UNKNOWN
            and stated_subcategory.strip()
        ):
            self.subcategory = Unclassified.UNASSIGNED
        return self


class NYCoAAttorney(Representative):
    """An attorney from the ATTORNEY DETAILS section of a Court-PASS docket.

    :ivar firm: The law firm the attorney filed under.
    :ivar address: The attorney's address, as one block of text.
    :ivar phone: The attorney's phone number.
    """

    firm: str = ""
    address: str = ""
    phone: str = ""


class NYCoAParty(Party[NYCoAAttorney]):
    """A party on a Court-PASS docket, with the attorneys representing it.

    :ivar party_role_raw: The party's role exactly as Court-PASS stated it
        (e.g. ``Amicus Curiae``).
    """

    party_role_raw: str = ""


class NYCoACase(Docket[DocketTransfer, NYCoDocketEntry, NYCoAParty]):
    """A New York Court of Appeals docket.

    :ivar date_filed: Court-PASS publishes no filing date for the case itself,
        so this is the earliest date any of its filings was received.
    :ivar argument_date: The date the case was or will be argued.
    :ivar decision_date: The date the case was decided, for decided cases.
    :ivar issues: The issues the Court assigned to the case, each paired with
        its detail. Usually one, occasionally up to five.
    :ivar official_citation: The official citation, for decided cases.
    :ivar lower_court_citation: The "Reported Below" citation for the decision
        under review, when Court-PASS reports one.
    :ivar transfers: Court-PASS publishes no transfer data, so this is always
        empty. Present because the standard docket format requires it.
    """

    date_filed: date | None = None
    argument_date: date | None = None
    decision_date: date | None = None
    issues: list[NYCoAIssue] = []
    official_citation: str = ""
    lower_court_citation: str = ""
    transfers: list[DocketTransfer] = []
