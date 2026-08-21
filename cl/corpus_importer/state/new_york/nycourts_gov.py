"""The schema of Court-PASS (nycourts.gov) data that the New York Court of Appeals
mergers consume.
"""

import logging
from datetime import date
from enum import Enum
from functools import partial
from typing import Annotated

from juriscraper.state.docket import (
    Docket,
    DocketEntry,
    DocketTransfer,
    Document,
    Party,
    Representative,
)
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    FilingDocType,
    FilingRole,
    FilingType,
    IssueCategory,
    IssueSubcategory,
)
from pydantic import BaseModel, BeforeValidator

logger = logging.getLogger(__name__)

__all__ = [
    "NYCoAAttorney",
    "NYCoACase",
    "NYCoAFile",
    "NYCoDocketEntry",
    "NYCoAIssue",
    "NYCoAParty",
]


def _covered[Vocabulary: Enum](
    vocabulary: type[Vocabulary], value: Vocabulary | str | None
) -> Vocabulary | None:
    """The vocabulary member `value` names, or `None` when there is no such
    member.

    Court-PASS states values the scraper's vocabularies do not cover yet: the
    Court assigns an issue a subcategory nobody has seen, or names a filing
    type the classifier has no member for. Refusing the value outright would
    cost the whole docket -- pydantic rejects the model, the loader counts it
    invalid, and every filing, party and issue on the case is lost over one
    unrecognized string.

    `None` is what the mergers already expect for a value the vocabulary does
    not cover. `cl.corpus_importer.state.new_york.utils` turns it into
    `UNASSIGNED` in the database, telling it apart from `UNKNOWN` -- the Court
    stated nothing at all -- by the raw string stored alongside it. So the
    classification of one field is lost and the docket is kept, which is the
    trade the mergers were built for.

    :param vocabulary: The vocabulary to look `value` up in.
    :param value: The string the scrape stated. `None` and members of
        `vocabulary` pass through untouched, so this is safe to apply to a
        model built in Python as well as one parsed from a scrape.
    :return: The member, or `None` if the vocabulary does not cover `value`.
    """
    if value is None or isinstance(value, vocabulary):
        return value
    try:
        return vocabulary(value)
    except ValueError:
        logger.warning(
            "Court-PASS stated %s %r, which Juriscraper's vocabulary does not "
            "cover; recording it as unassigned. Add the member to "
            "juriscraper.state.new_york.nycourts_gov.vocabularies.%s.",
            vocabulary.__name__,
            value,
            vocabulary.__name__,
        )
        return None


# The vocabularies the scraper classifies Court-PASS's own wording into, each
# paired with the fallback above so that a value it does not cover costs the
# field rather than the docket. Every scrape-stated vocabulary field below is
# annotated with one of these; see `_covered`.
CoveredFilingRole = Annotated[
    FilingRole | None, BeforeValidator(partial(_covered, FilingRole))
]
CoveredFilingDocType = Annotated[
    FilingDocType | None, BeforeValidator(partial(_covered, FilingDocType))
]
CoveredFilingType = Annotated[
    FilingType | None, BeforeValidator(partial(_covered, FilingType))
]
CoveredIssueCategory = Annotated[
    IssueCategory | None, BeforeValidator(partial(_covered, IssueCategory))
]
CoveredIssueSubcategory = Annotated[
    IssueSubcategory | None,
    BeforeValidator(partial(_covered, IssueSubcategory)),
]


class NYCoAFile(Document):
    """A file published on a Court-PASS filing-detail page.

    :ivar file_name: The name of the file as Court-PASS published it.
    :ivar content_type: The MIME type of the file, when known. Court-PASS
        publishes PDFs along with playlist files for oral argument recordings.
    :ivar url: Required by the standard docket format, but Court-PASS serves
        files through form postbacks rather than addressable URLs, so it is
        empty and CourtListener stores nothing from it.
    :ivar available: Whether the file can be downloaded. ``False`` for sealed
        files and files the site lists but does not serve.
    :ivar doc_role: The party role the file name states. ``None`` when the name
        does not follow the Court's naming convention, and also when it states
        a role the vocabulary does not cover.
    :ivar doc_party: The party name encoded in the file name.
    :ivar doc_type: The document type the file name states. The
        ``_``-prefixed members are court output rather than a filing. ``None``
        on the same terms as ``doc_role``.
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

    url: str = ""
    file_name: str
    content_type: str = ""
    available: bool = True
    doc_role: CoveredFilingRole = None
    doc_party: str = ""
    doc_type: CoveredFilingDocType = None
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
        rendered it (e.g. ``Appellant Brief``). Empty when no table row listed
        this filing, which is what marks a filing as reconstructed.
    :ivar entry_filing_type: The classified filing type. ``None`` both when no
        table row named this filing and when the scraper's vocabulary does not
        cover what the table named; ``raw_filing_type`` tells those apart.
    :ivar party: Name of the party associated with this filing.
    :ivar date_filed: The date Court-PASS recorded the filing as received.
        ``None`` on a filing reconstructed from a document, since the file list
        carries no dates.
    :ivar date_due: The date Court-PASS recorded the filing as due.
    :ivar entry_role: The party role for this filing. ``None`` when the filing
        type implies no role, and also when it implies one the vocabulary does
        not cover.
    :ivar entry_doctype: The document type for this filing. The ``_``-prefixed
        members are court output rather than a party filing. ``None`` on the
        same terms as ``entry_role``.
    """

    date_filed: date | None = None
    docket_entry_id: str
    entry_index: int | None = None
    raw_filing_type: str = ""
    entry_filing_type: CoveredFilingType = None
    party: str = ""
    date_due: date | None = None
    entry_role: CoveredFilingRole = None
    entry_doctype: CoveredFilingDocType = None


class NYCoAIssue(BaseModel):
    """An issue the Court of Appeals assigned to a case, classified.

    :ivar category_raw: The issue exactly as Court-PASS stated it, its category
        and subcategory joined by a double dash (e.g.
        ``Judgments--Confession of Judgment``).
    :ivar category: The classified category. ``None`` when the scraper's
        vocabulary does not cover what the Court stated.
    :ivar subcategory: The classified subcategory. ``None`` when the Court stated
        a bare category -- roughly 13% of issues -- and also ``None`` when the
        vocabulary does not cover it.
    :ivar detail: The Court's description of the issue. Empty when Court-PASS
        stated none, which happens on roughly 4% of the issues observed.
    """

    category_raw: str
    category: CoveredIssueCategory = None
    subcategory: CoveredIssueSubcategory = None
    detail: str = ""


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
