"""Mergers for New York Court of Appeals (Court-PASS) docket data.

The input is the standard Juriscraper docket format described in
`cl.corpus_importer.state.new_york.court_pass`.
"""

import logging
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, ClassVar, cast, override

from asgiref.sync import async_to_sync
from django.db.models import Model, QuerySet

from cl.corpus_importer.state.common.docket import (
    DocketEntryRelation,
    DocketMerger,
    PartyRelation,
)
from cl.corpus_importer.state.common.docket_entry import AttachmentRelation
from cl.corpus_importer.state.common.party import (
    AttorneyMerger,
    AttorneyRelation,
    PartyMerger,
    PartyTypeMerger,
    RoleMerger,
)
from cl.corpus_importer.state.merger import (
    Attribute,
    ManyStrategy,
    Merger,
    OneToManyRelation,
    RelatedParams,
    ReverseOneToOneRelation,
    ThroughParameters,
    overwrite,
)
from cl.corpus_importer.state.new_york.nycourts_gov import (
    NYCoAAttorney,
    NYCoACase,
    NYCoAFile,
    NYCoAIssue,
    NYCoAParty,
    NYCoDocketEntry,
)
from cl.corpus_importer.state.new_york.utils import (
    NYCOA_COURT_ID,
    filing_doctype_value,
    filing_role_value,
    filing_type_value,
    is_nycoa_court,
    issue_category_value,
    issue_subcategory_value,
    make_docket_number_core,
)
from cl.people_db.models import Attorney, Party, Role
from cl.recap.mergers import find_docket_object_query
from cl.search.models import Docket
from cl.search.state.new_york.models import (
    NYCoADocketEntry,
    NYCoADocketIssue,
    NYCoADocketMetadata,
    NYCoADocument,
)

logger = logging.getLogger(__name__)

PHONE_MAX_LENGTH: int = Attorney._meta.get_field("phone").max_length or 20
"""How much of a phone number `Attorney` can store."""

SMALLINT_MAX = 32767
"""The largest volume or part number `NYCoADocument` can store.

Both are `SmallIntegerField`s, which is ample for a record published in
volumes, and both are read out of the file name rather than stated by the
Court."""


def _storable_number(
    value: int | None, field: str, document: NYCoAFile
) -> int | None:
    """A file's volume or part number, or `None` when it cannot be stored.

    A volume is whatever the file name's numbering reads as, and a name the
    Court wrote as `...-Appdx-Vol6.1910` -- the extension is `.1910` -- reads as
    volume 61910. Postgres refuses that, and because the docket merges
    atomically the whole case would be lost over one misread number. Storing
    nothing loses only the volume, and the error names the file so the scraper's
    reading of it can be fixed.

    :param value: The number the scraper read.
    :param field: Which number it is, for the log message.
    :param document: The file it was read from, for the log message.
    :return: The number, or `None` if it is out of range.
    """
    if value is None or 0 <= value <= SMALLINT_MAX:
        return value
    logger.error(
        "Court-PASS file %s states %s %s, which is outside the range "
        "NYCoADocument can store; storing none.",
        document.file_name,
        field,
        value,
    )
    return None


def _keep_stored_file(scrape: Any, db: Any) -> Any:
    """Merge strategy that keeps the path already stored for a document when
    this scrape reports none.

    A file the scraper skipped this time -- a sealed one, or one a partial
    scrape never reached -- is still where it left it last time, so a blank must
    not clobber the path.

    The default strategy will not do this, and not for the usual reason:
    `filepath_local` is a `FileField`, whose descriptor wraps whatever it is
    handed in a `FieldFile`. An absent value therefore arrives as an empty
    `FieldFile` rather than as `None`, and `overwrite_if_present` reads it as a
    real value. An empty `FieldFile` is falsy, which is what this tests
    instead."""
    return scrape if scrape else db


class NYCoADocumentMerger[ParamType](
    Merger[NYCoAFile, RelatedParams[ParamType], NYCoADocument]
):
    """Merger for a file Court-PASS published for a filing.

    Subclasses `Merger` rather than the shared `DocumentMerger`, which merges
    `url` and drives a re-download off it changing. Court-PASS serves files
    through form postbacks and publishes no per-file URL, so `url` is left
    empty and `NYCoADocument.download` refuses to fetch by it.

    Nothing needs downloading: the scraper writes the file into the same bucket
    `filepath_local` is stored in, and reports where, so the merge points
    `filepath_local` straight at it rather than copying it anywhere. That
    leaves only the text extraction, which
    `manage.py state_document_download --model search.NYCoADocument
    --skip-download` picks up from `filepath_local` being set and `ocr_status`
    not being finished -- the same sweep every other state's documents go
    through."""

    model: ClassVar[type[Model]] = NYCoADocument
    key: ClassVar[Iterable[str]] = ["file_name"]

    file_name: str = Attribute(
        lambda doc, params: doc.file_name, strategy=overwrite
    )
    content_type: str = Attribute(
        lambda doc, params: doc.content_type, strategy=overwrite
    )
    available: bool = Attribute(
        lambda doc, params: doc.available, strategy=overwrite
    )
    doc_role: str = Attribute(
        lambda doc, params: doc.doc_role.value if doc.doc_role else "",
        strategy=overwrite,
    )
    doc_party: str = Attribute(
        lambda doc, params: doc.doc_party, strategy=overwrite
    )
    doc_type: str = Attribute(
        lambda doc, params: doc.doc_type.value if doc.doc_type else "",
        strategy=overwrite,
    )
    volume: int | None = Attribute(
        lambda doc, params: _storable_number(doc.volume, "volume", doc),
        strategy=overwrite,
    )
    part: int | None = Attribute(
        lambda doc, params: _storable_number(doc.part, "part", doc),
        strategy=overwrite,
    )
    # Where the scraper put the file, which is a key in the bucket this field
    # is stored in, so it needs no fetching or copying.
    filepath_local: str = Attribute(
        lambda doc, params: doc.local_path, strategy=_keep_stored_file
    )

    @override
    def pre_update(self, updated_fields: list[str]) -> list[str]:
        """Send a document back for extraction when the scraper reports its
        file at a new path.

        A new path means the scraper fetched the file again, so whatever was
        extracted came from a copy that has been replaced. Clearing
        `ocr_status` is what puts the document back in front of the extraction
        sweep.

        Unlike `DocumentMerger`, the file the path pointed at is *not* deleted.
        CourtListener did not put it there and does not own it -- it is the
        scraper's own download, and deleting it would destroy the scrape rather
        than a copy of it."""
        updated = super().pre_update(updated_fields)
        # This hook only runs on the update path, so `existing` is set; the
        # guard narrows the type for mypy.
        if (existing := self.existing) is None:
            return updated
        if "filepath_local" not in updated_fields:
            return updated
        existing.ocr_status = None
        updated.append("ocr_status")
        return updated


def _entry_party_id(
    entry: NYCoDocketEntry, params: RelatedParams[Any]
) -> int | None:
    """Resolve the filing's party to a party on this docket, matching on name
    the way `PartyMerger` does."""
    if not entry.party:
        return None
    docket = cast(Docket, params.parent)
    return (
        docket.parties.filter(name=entry.party)
        .values_list("pk", flat=True)
        .first()
    )


def _keep_party_name(scrape: str | None, db: str | None) -> str:
    """Merge strategy that keeps the party name an earlier scrape recorded when
    this one read none, rather than blanking it.

    A filing's party is part of its `docket_entry_id`, so within one entry the
    name never legitimately changes -- a clerk correcting it re-keys the entry
    into a new row. A blank here therefore means this scrape did not see the
    name, not that the Court withdrew it. The default strategy would not do:
    it only protects a `None`, and Court-PASS reports a missing party as `""`."""
    return scrape or db or ""


class NYCoADocketEntryMerger[ParamType](
    Merger[NYCoDocketEntry, RelatedParams[ParamType], NYCoADocketEntry]
):
    """Merger for a Court-PASS filing.

    Subclasses `Merger` rather than the shared `DocketEntryMerger`, whose
    cross-state entry type NYCoA does not store -- the Court's own filing type
    vocabulary is normalized instead."""

    model: ClassVar[type[Model]] = NYCoADocketEntry
    key: ClassVar[Iterable[str]] = ["docket_entry_id"]

    # Court-PASS only dates the filings its FILINGS table lists.
    date_filed: date | None = Attribute(
        lambda e, params: e.date_filed, strategy=overwrite
    )
    date_due: date | None = Attribute(
        lambda e, params: e.date_due, strategy=overwrite
    )
    docket_entry_id: str = Attribute(
        lambda e, params: e.docket_entry_id, strategy=overwrite
    )
    entry_index: int | None = Attribute(
        lambda e, params: e.entry_index, strategy=overwrite
    )
    filing_type: int = Attribute(
        lambda e, params: filing_type_value(
            e.entry_filing_type, e.raw_filing_type
        ),
        strategy=overwrite,
    )
    filing_type_raw: str = Attribute(
        lambda e, params: e.raw_filing_type, strategy=overwrite
    )
    filing_role: int = Attribute(
        lambda e, params: filing_role_value(e.entry_role), strategy=overwrite
    )
    filing_doctype: int = Attribute(
        lambda e, params: filing_doctype_value(e.entry_doctype),
        strategy=overwrite,
    )
    filing_type_recognized: bool = Attribute(
        lambda e, params: e.filing_type_recognized, strategy=overwrite
    )
    # Keep a party we resolved on an earlier scrape rather than clearing it
    # when this scrape can't find a match.
    party_id: int | None = Attribute(_entry_party_id)
    # The name Court-PASS printed, kept whether or not `party_id` resolved --
    # on a filing by a party with no attorney of record it is the only record
    # of who filed.
    party_name: str = Attribute(
        lambda e, params: e.party, strategy=_keep_party_name
    )
    # Court-PASS lists every file it has for a case, so a file that is gone
    # from the list is gone from the case.
    documents: list[NYCoADocument] = AttachmentRelation(
        NYCoADocumentMerger, strategy=ManyStrategy.REPLACE
    )


def _attorney_contact_raw(attorney: NYCoAAttorney, params: Any) -> str:
    """Fold the firm and address Court-PASS prints for an attorney into the one
    free-text contact field CourtListener keeps for them.

    The phone joins them when `_attorney_phone` had to shorten it, so the full
    string the Court printed survives somewhere."""
    parts = [attorney.firm, attorney.address]
    if attorney.phone != _attorney_phone(attorney, params):
        parts.append(attorney.phone)
    return "\n".join(part for part in parts if part)


def _attorney_phone(attorney: NYCoAAttorney, params: Any) -> str:
    """The attorney's phone number, trimmed to fit `Attorney.phone`.

    Court-PASS writes a direct line as `(516) 222-6200 ext: 284`, which is
    longer than the 20 characters the column allows. Dropping the extension
    keeps the field dialable; `_attorney_contact_raw` keeps the whole string."""
    phone = attorney.phone.strip()
    if len(phone) <= PHONE_MAX_LENGTH:
        return phone
    number, extension, _ = phone.partition(" ext")
    if extension and len(number) <= PHONE_MAX_LENGTH:
        return number
    return phone[:PHONE_MAX_LENGTH]


class NYCoAAttorneyMerger(AttorneyMerger[NYCoAAttorney, RelatedParams[None]]):
    contact_raw: str = Attribute(_attorney_contact_raw, strategy=overwrite)
    phone: str = Attribute(_attorney_phone, strategy=overwrite)


def _attorney_role(
    attorney: NYCoAAttorney, params: ThroughParameters[Any]
) -> int:
    """Court-PASS states which party an attorney represents but never in what
    role, and the role is not nullable."""
    return Role.UNKNOWN


class NYCoARoleMerger(RoleMerger[NYCoAAttorney, RelatedParams[None]]):
    role: int = Attribute(_attorney_role)


def _party_type_name(party: NYCoAParty, params: Any) -> str:
    """Prefer the role Court-PASS printed. The cross-state `PartyType`
    vocabulary has no value for several roles the Court of Appeals uses, amicus
    curiae among them, so normalizing here would lose them."""
    return party.party_role_raw or party.party_type.value.title()


class NYCoAPartyTypeMerger(PartyTypeMerger[NYCoAParty, RelatedParams[None]]):
    name: str = Attribute(_party_type_name)


class NYCoAPartyMerger(PartyMerger[NYCoAParty, RelatedParams[None]]):
    """Merger for a party on a Court-PASS docket.

    Identity is `PartyMerger`'s -- the name, within the docket -- with the role
    breaking a tie; see `resolve_query`."""

    attorneys: list[Attorney] = AttorneyRelation(
        attorney=NYCoAAttorneyMerger, role=NYCoARoleMerger
    )

    @override
    def resolve_query(self, qs: QuerySet[Party]) -> tuple[bool, Party | None]:
        """Pick which of the docket's parties this scraped one is.

        A name is not unique on a Court-PASS docket: in a family case the Court
        lists one person under two roles -- the child and the respondent -- and
        each is its own party with its own attorney. `PartyMerger` matches on
        the name alone, which finds both and, with the base implementation,
        fails the whole docket on every scrape after the first. The role the
        Court printed is what separates them, so it decides here.

        A single candidate is taken whatever its role, so that a party the
        Court has re-designated -- a respondent who becomes a
        respondent-appellant on a cross-appeal -- keeps its row rather than
        being duplicated under the new role.

        :param qs: The candidates `PartyMerger.query` found. The framework caps
            this at two rows; a third party sharing one name would need a later
            scrape to settle, which is why the ambiguous case is refused rather
            than guessed.
        :return: Whether to continue, and the row to merge into.
        """
        candidates = list(qs)
        if len(candidates) < 2:
            return True, candidates[0] if candidates else None

        docket = cast(Docket, self.params.parent)
        role = _party_type_name(self.scrape, None)
        for candidate in candidates:
            if candidate.party_types.filter(docket=docket, name=role).exists():
                return True, candidate
        logger.error(
            "Docket %s lists %s under several roles and none is %s; refusing "
            "to guess which party this is.",
            docket.docket_number,
            self.scrape.name,
            role,
        )
        return False, None


@dataclass(frozen=True)
class ScrapedIssue:
    """One of a case's issues, with what the merger needs beyond the issue.

    :ivar issue: The issue as the scraper classified it.
    :ivar category: The code stored for the issue's category.
    :ivar subcategory: The code stored for the issue's subcategory.
    :ivar alone_in_category: Whether this is the only issue the scrape states
        under this category and subcategory. `NYCoAIssueMerger` identifies an
        issue by that pair, so it needs to know when the pair is shared, and a
        child merger cannot see its siblings.
    """

    issue: NYCoAIssue
    category: int
    subcategory: int
    alone_in_category: bool


class NYCoAIssueMerger[ParamType](
    Merger[ScrapedIssue, RelatedParams[ParamType], NYCoADocketIssue]
):
    """Merger for one issue the Court assigned to a case.

    An issue is identified by its category and subcategory, which is what
    `NYCoADocketIssue` is indexed on, so the Court rewording a description it
    has already published updates the issue in place rather than replacing the
    row. The Court does assign a case two issues under one category pair,
    though, and then the description is the only thing separating them, so for
    those it joins the identity; see `query`.
    """

    model: ClassVar[type[Model]] = NYCoADocketIssue
    key: ClassVar[Iterable[str]] = ["category", "subcategory"]

    category: int = Attribute(
        lambda scraped, params: scraped.category, strategy=overwrite
    )
    subcategory: int = Attribute(
        lambda scraped, params: scraped.subcategory, strategy=overwrite
    )
    category_raw: str = Attribute(
        lambda scraped, params: scraped.issue.category_raw, strategy=overwrite
    )
    detail: str = Attribute(
        lambda scraped, params: scraped.issue.detail, strategy=overwrite
    )

    @override
    def query(self) -> QuerySet[NYCoADocketIssue]:
        """The issues already stored on this case under the same category pair.

        Narrows to the description as well when the scrape states another issue
        under that pair. Matching on the pair alone would then hand both scraped
        issues whichever row was found first, merging two issues into one; the
        description is what the Court tells them apart by, so it is what the
        merger has to as well.

        :return: The candidate rows, oldest first, so that `resolve_query` is
            deterministic.
        """
        candidates = self.manager.filter(
            category=self.transformed["category"],
            subcategory=self.transformed["subcategory"],
        )
        if not self.scrape.alone_in_category:
            candidates = candidates.filter(detail=self.transformed["detail"])
        return candidates.order_by("pk")

    @override
    def resolve_query(
        self, qs: QuerySet[NYCoADocketIssue]
    ) -> tuple[bool, NYCoADocketIssue | None]:
        """Pick which of the stored issues this scraped one is.

        Several rows can share a category pair -- an earlier scrape stated two
        issues under it and this one states fewer -- and all of them are
        candidates for the same issue. The row whose description still matches
        wins, so a case that kept an issue and dropped another keeps the right
        row; failing that the oldest does, and `ManyStrategy.REPLACE` on the
        relation prunes the rest.

        :param qs: The candidates `query` found. The framework caps this at two
            rows, which is enough here: the choice only has to come out the same
            on every scrape, and a third row under one pair would have to be
            pruned by a later scrape rather than this one.
        :return: Whether to continue, and the row to merge into.
        """
        candidates = list(qs)
        if not candidates:
            return True, None
        detail = self.transformed["detail"]
        return True, next(
            (
                candidate
                for candidate in candidates
                if candidate.detail == detail
            ),
            candidates[0],
        )


def _case_issues(case: NYCoACase, params: Any) -> Sequence[ScrapedIssue]:
    """The case's issues, each paired with the codes it is stored under.

    The codes are classified here rather than in the child merger because
    whether another issue shares an issue's category pair decides how the
    merger identifies it, and only the case sees all of them at once. See
    `ScrapedIssue`."""
    classified = [
        (
            issue,
            issue_category_value(issue.category, issue.category_raw),
            issue_subcategory_value(issue.subcategory, issue.category_raw),
        )
        for issue in case.issues
    ]
    shared = Counter(
        (category, subcategory) for _, category, subcategory in classified
    )
    return [
        ScrapedIssue(
            issue=issue,
            category=category,
            subcategory=subcategory,
            alone_in_category=shared[(category, subcategory)] == 1,
        )
        for issue, category, subcategory in classified
    ]


class NYCoADocketMetadataMerger(
    Merger[NYCoACase, RelatedParams[None], NYCoADocketMetadata]
):
    """Merger for the NYCoA-only docket fields.

    The `OneToOneField` lives on this model rather than on `Docket`, so this
    merger sets its own `docket` from the parent and matches on it."""

    model: ClassVar[type[Model]] = NYCoADocketMetadata
    key: ClassVar[Iterable[str]] = ["docket"]

    docket: Docket = Attribute(lambda case, params: params.parent)
    # Court-PASS states a case's issues in full, so an issue that is gone from
    # the scrape is one the Court removed.
    issues: list[NYCoADocketIssue] = OneToManyRelation(
        NYCoAIssueMerger, _case_issues, strategy=ManyStrategy.REPLACE
    )
    decision_date: date | None = Attribute(
        lambda case, params: case.decision_date, strategy=overwrite
    )
    official_citation: str = Attribute(
        lambda case, params: case.official_citation, strategy=overwrite
    )
    lower_court_citation: str = Attribute(
        lambda case, params: case.lower_court_citation, strategy=overwrite
    )


def _case_metadata(case: NYCoACase, params: None) -> NYCoACase | None:
    """The NYCoA metadata is spread across the case's own fields rather than
    nested under a key of its own, so the metadata merger takes the case."""
    return case


def _date_last_filing(case: NYCoACase, params: None) -> date | None:
    filing_dates = sorted(e.date_filed for e in case.entries if e.date_filed)
    return filing_dates[-1] if filing_dates else case.date_filed


class NYCoADocketMerger(DocketMerger[NYCoACase, None]):
    model: ClassVar[type[Model]] = Docket

    atomic = True

    court_id: str = Attribute(
        lambda case, params: NYCOA_COURT_ID, strategy=overwrite
    )
    docket_number_core: str = Attribute(
        lambda case, params: make_docket_number_core(case.docket_number),
        strategy=overwrite,
    )
    # Court-PASS publishes no filing date for the case itself, so keep any date
    # another source already established.
    date_filed: date | None = Attribute(lambda case, params: case.date_filed)
    date_argued: date | None = Attribute(
        lambda case, params: case.argument_date, strategy=overwrite
    )
    date_last_filing: date | None = Attribute(
        _date_last_filing, strategy=overwrite
    )

    parties: list[Party] = PartyRelation(
        NYCoAPartyMerger, party_type=NYCoAPartyTypeMerger
    )
    # Court-PASS states a case's filings in full -- the loader refuses a scrape
    # that never read the file list -- so a filing that is gone from the scrape
    # is one the Court removed.
    nycoa_docket_entries: list[NYCoADocketEntry] = DocketEntryRelation(
        NYCoADocketEntryMerger, strategy=ManyStrategy.REPLACE
    )
    nycoa_metadata: NYCoADocketMetadata = ReverseOneToOneRelation(
        NYCoADocketMetadataMerger, _case_metadata
    )

    @override
    def query(self) -> QuerySet[Docket]:
        return async_to_sync(find_docket_object_query)(
            court_id=NYCOA_COURT_ID,
            pacer_case_id=None,
            docket_number=self.scrape.docket_number,
            docket_number_core=make_docket_number_core(
                self.scrape.docket_number
            ),
            federal_defendant_number=None,
            federal_dn_judge_initials_assigned=None,
            federal_dn_judge_initials_referred=None,
            skip_dn_core_confirmation=True,
            cheap_count=False,
        )

    @staticmethod
    def validate(scrape: NYCoACase) -> bool:
        if not is_nycoa_court(scrape.court_id):
            logger.error("Unknown court id: %s", scrape.court_id)
            return False
        # A docket number we can't normalize can't be matched against the
        # dockets we already have, and `make_docket_number_core` logs why.
        return bool(make_docket_number_core(scrape.docket_number))
