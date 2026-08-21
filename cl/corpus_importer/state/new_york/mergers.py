"""Mergers for New York Court of Appeals (Court-PASS) docket data.

The input is the standard Juriscraper docket format described in
`cl.corpus_importer.state.new_york.court_pass`.
"""

import logging
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Any, ClassVar, cast, override

from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models import Model, QuerySet
from django.db.models.fields.files import FieldFile
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    CourtVocabulary,
)

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
    OneToOneRelation,
    RelatedParams,
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
    Unclassified,
)
from cl.corpus_importer.state.new_york.storage import (
    PUBLISHED_PREFIX,
    copy_file,
    discard_private_file,
    is_published,
    is_scraped,
    withdraw_file,
)
from cl.corpus_importer.state.new_york.utils import (
    NYCOA_COURT_ID,
    is_nycoa_court,
    issue_code,
    make_docket_number_core,
    mirrored_code,
)
from cl.corpus_importer.state.utils import MergeResult
from cl.people_db.models import Attorney, Party, PartyType, Role
from cl.recap.mergers import find_docket_object_query
from cl.search.models import Docket
from cl.search.state.new_york.models import (
    NYCoADocketEntry,
    NYCoADocketIssue,
    NYCoADocketMetadata,
    NYCoADocument,
)
from cl.search.state.new_york.vocabularies import (
    FilingDocType,
    FilingRole,
    FilingType,
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


def _keep_stored_file(scrape: FieldFile, db: FieldFile) -> str:
    """Merge strategy that keeps the path already stored for a document when
    this scrape has no published one to put there.

    :param scrape: The path this scrape published to, if any.
    :param db: The path already stored for the document.
    :return: The path to store.
    """
    return (scrape.name or "") or (db.name or "")


def _stated(reading: CourtVocabulary | Unclassified) -> str:
    """The Court-PASS value to store for a field read off a file name.

    `NYCoADocument.doc_role` and `doc_type` are free text mirroring what the
    name itself stated, so a name that stated nothing readable is stored blank
    rather than under one of the reserved readings.

    :param reading: What the scrape schema classified the field as.
    :return: The value Court-PASS's naming convention uses, or the empty string.
    """
    return "" if isinstance(reading, Unclassified) else reading.value


class NYCoADocumentMerger[ParamType](
    Merger[NYCoAFile, RelatedParams[ParamType], NYCoADocument]
):
    """Merger for a file Court-PASS published for a filing.

    Subclasses `Merger` rather than the shared `DocumentMerger`, which merges
    `url` and drives a re-download off it changing. Court-PASS serves files
    through form postbacks and publishes no per-file URL, so `url` is left
    empty and `NYCoADocument.download` refuses to fetch by it.

    Nothing needs downloading: the scraper has already fetched the file into
    the private bucket and reports where, so the merge moves it into the
    public one rather than fetching it again; see `publish`. That leaves only
    the text extraction,
    which `manage.py state_document_download --model search.NYCoADocument
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
        lambda doc, params: _stated(doc.doc_role), strategy=overwrite
    )
    doc_party: str = Attribute(
        lambda doc, params: doc.doc_party, strategy=overwrite
    )
    doc_type: str = Attribute(
        lambda doc, params: _stated(doc.doc_type), strategy=overwrite
    )
    volume: int | None = Attribute(
        lambda doc, params: _storable_number(doc.volume, "volume", doc),
        strategy=overwrite,
    )
    part: int | None = Attribute(
        lambda doc, params: _storable_number(doc.part, "part", doc),
        strategy=overwrite,
    )
    filepath_local: str = Attribute(
        lambda doc, params: doc.local_path, strategy=_keep_stored_file
    )

    @override
    def merge_one(self) -> tuple[MergeResult[Any], NYCoADocument | None]:
        """Publish the file, then write the document once.

        :return: The merge result and the merged document, unchanged.
        """
        self.publish()
        return super().merge_one()

    def publish(self) -> None:
        """Move the scraped file into the bucket CourtListener serves, and
        rewrite the path the merge is about to store to say so."""
        private_key = self.scrape.local_path
        if not private_key or is_published(private_key):
            return
        if not is_scraped(private_key):
            logger.error(
                "Court-PASS names %s a file at %s, which is in neither the "
                "private bucket nor the published layout; not publishing it.",
                self.scrape.file_name,
                private_key,
            )
            self.transformed["filepath_local"] = ""
            return

        naming = NYCoADocument(
            docket_entry=cast(NYCoADocketEntry, self.params.parent),
            filepath_local=private_key,
        )
        published_key = naming.get_pdf_path(naming.make_filename())

        if (existing := self.existing) is not None:
            if existing.filepath_local.name == published_key:
                # Already moved, on the merge that first saw this file.
                self.transformed["filepath_local"] = published_key
                return

        if not copy_file(
            private_key, published_key, self.transformed["content_type"]
        ):
            self.transformed["filepath_local"] = ""
            return
        transaction.on_commit(partial(discard_private_file, private_key))
        self.transformed["filepath_local"] = published_key

    @override
    def needs_update(self) -> bool:
        """Force the update path for a document whose file the Court has
        stopped serving, so `pre_update` can drop the path in the same write
        even when nothing else about the document changed."""
        return self._withdrawn() and bool(
            self.existing and self.existing.filepath_local
        )

    def _withdrawn(self) -> bool:
        """Whether the Court has stopped serving this document's file, which
        it says by listing the file without making it available."""
        return not self.scrape.available and not self.scrape.local_path

    @override
    def pre_update(self, updated_fields: list[str]) -> list[str]:
        """Drop the file of a document the Court has stopped serving, and send
        one whose file has moved back for extraction.

        A new path means the scraper fetched the file again, so whatever was
        extracted came from a copy that has been replaced. Clearing
        `ocr_status` is what puts the document back in front of the extraction
        sweep."""
        updated = super().pre_update(updated_fields)
        if (existing := self.existing) is None:
            return updated
        if self._withdrawn() and existing.filepath_local:
            existing.filepath_local = ""
            updated.append("filepath_local")
        if "filepath_local" not in updated_fields + updated:
            return updated
        existing.ocr_status = None
        updated.append("ocr_status")
        return updated


def _entry_party_id(
    entry: NYCoDocketEntry, params: RelatedParams[Any]
) -> int | None:
    """Resolve the filing's party to a party on this docket, matching on the
    name the way `PartyMerger` does, with the filing's role breaking a tie.

    :param entry: The filing whose party to resolve.
    :param params: The parameters of the merge, whose parent is the docket.
    :return: The party's pk, or `None` when the docket lists no party of that
        name. A filer with no attorney of record is one the FILINGS table names
        and the ATTORNEY DETAILS section never does; `party_name` keeps the
        name whether or not this resolves.
    """
    if not entry.party:
        return None
    docket = cast(Docket, params.parent)
    matched = list(
        docket.parties.filter(name=entry.party)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    if len(matched) < 2:
        return matched[0] if matched else None
    # Only an ambiguous name is worth the second query the role costs.
    role = FilingRole(mirrored_code(FilingRole, entry.entry_role)).label
    by_role = (
        PartyType.objects.filter(
            docket=docket, party_id__in=matched, name__iexact=role
        )
        .order_by("party_id")
        .values_list("party_id", flat=True)
        .first()
    )
    return matched[0] if by_role is None else by_role


def _keep_party_name(scrape: str | None, db: str | None) -> str:
    """Merge strategy that keeps the party name an earlier scrape recorded when
    this one read none, rather than blanking it."""
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
        lambda e, params: mirrored_code(FilingType, e.entry_filing_type),
        strategy=overwrite,
    )
    filing_type_raw: str = Attribute(
        lambda e, params: e.raw_filing_type, strategy=overwrite
    )
    filing_role: int = Attribute(
        lambda e, params: mirrored_code(FilingRole, e.entry_role),
        strategy=overwrite,
    )
    filing_doctype: int = Attribute(
        lambda e, params: mirrored_code(FilingDocType, e.entry_doctype),
        strategy=overwrite,
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


class ScrapedAttorney(NYCoAAttorney):
    """One of a party's attorneys, with what the role merger needs beyond the
    attorney.

    :ivar primary: Whether this is the first attorney Court-PASS listed for the
        party. Court-PASS never states an attorney's role, so the role follows
        the convention the other states' mergers use -- the first attorney
        listed is the party's lead and the rest are unknown -- which a child
        merger cannot work out on its own because it cannot see its siblings.
    """

    primary: bool = False


def _attorney_contact_raw(attorney: NYCoAAttorney, params: Any) -> str:
    """Fold the firm and address Court-PASS prints for an attorney into the one
    free-text contact field CourtListener keeps for them."""
    parts = [attorney.firm, attorney.address]
    if (phone := attorney.phone.strip()) != _attorney_phone(attorney, params):
        parts.append(phone)
    return "\n".join(part for part in parts if part)


def _attorney_phone(attorney: NYCoAAttorney, params: Any) -> str:
    """The attorney's phone number, trimmed to fit `Attorney.phone`."""
    phone = attorney.phone.strip()
    if len(phone) <= PHONE_MAX_LENGTH:
        return phone
    number, extension, _ = phone.partition(" ext")
    if extension and len(number) <= PHONE_MAX_LENGTH:
        return number
    return phone[:PHONE_MAX_LENGTH]


class NYCoAAttorneyMerger(
    AttorneyMerger[ScrapedAttorney, RelatedParams[None]]
):
    """Merger for an attorney on a Court-PASS docket."""

    contact_raw: str = Attribute(_attorney_contact_raw, strategy=overwrite)
    phone: str = Attribute(_attorney_phone, strategy=overwrite)


def _attorney_role(
    attorney: ScrapedAttorney, params: ThroughParameters[Any]
) -> int:
    """The role to store for an attorney Court-PASS lists for a party.

    Court-PASS states which party an attorney represents but never in what
    role, and the role is not nullable, so the attorney the Court listed first
    is stored as the party's lead and the rest as unknown -- the convention the
    other states' mergers follow. See `ScrapedAttorney`.

    :param attorney: The attorney, marked with whether the Court listed it
        first.
    :param params: Unused; the role is read off the attorney alone.
    :return: The `Role` code to store.
    """
    return Role.ATTORNEY_LEAD if attorney.primary else Role.UNKNOWN


class NYCoARoleMerger(RoleMerger[ScrapedAttorney, RelatedParams[None]]):
    """Merger for the link between a Court-PASS attorney and the party.

    Overrides only `role`, which Court-PASS never states; see
    `_attorney_role`."""

    role: int = Attribute(_attorney_role)


def _party_type_name(party: NYCoAParty, params: Any) -> str:
    """Prefer the role Court-PASS printed. The cross-state `PartyType`
    vocabulary has no value for several roles the Court of Appeals uses, amicus
    curiae among them, so normalizing here would lose them."""
    return party.party_role_raw or party.party_type.value.title()


class NYCoAPartyTypeMerger(PartyTypeMerger[NYCoAParty, RelatedParams[None]]):
    """Merger for a party's role on a Court-PASS docket."""

    name: str = Attribute(_party_type_name)


def _party_attorneys(party: NYCoAParty, params: Any) -> list[ScrapedAttorney]:
    """The party's attorneys, each marked with whether the Court listed it
    first.

    Which attorney that is decides the role stored for all of them, and only
    the party sees them all at once. See `ScrapedAttorney`."""
    return [
        # `dict` copies the scraped fields across without re-serializing them.
        ScrapedAttorney(**dict(attorney), primary=index == 0)
        for index, attorney in enumerate(party.representatives)
    ]


class NYCoAPartyMerger(PartyMerger[NYCoAParty, RelatedParams[None]]):
    """Merger for a party on a Court-PASS docket.

    Identity is `PartyMerger`'s -- the name, within the docket -- with the role
    breaking a tie; see `resolve_query`."""

    attorneys: list[Attorney] = AttorneyRelation(
        attorney=NYCoAAttorneyMerger,
        role=NYCoARoleMerger,
        transform=_party_attorneys,
    )

    @override
    def query(self) -> QuerySet[Party]:
        """The docket's parties by date created.

        :return: `PartyMerger`'s candidates, oldest first.
        """
        return super().query().order_by("date_created")

    @override
    def resolve_query(self, qs: QuerySet[Party]) -> tuple[bool, Party | None]:
        """Pick which of the docket's parties this scraped one is.

        A name is not unique on a Court-PASS docket. We make a best effort here
        to match parties when they have the same name (family cases), and log when
        we can't disambiguate.

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
            if candidate.party_types.filter(
                docket=docket, name__iexact=role
            ).exists():
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

    An issue is identified by its category, subcategory, and details which is what
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
            issue_code(issue.category),
            issue_code(issue.subcategory),
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

    The `OneToOneField` lives on this model rather than on `Docket`, so the
    relation fills in `docket` from the parent and matches on it; this merger
    must not declare that field itself."""

    model: ClassVar[type[Model]] = NYCoADocketMetadata

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
    """The date the case's most recent dated filing was received.

    Court-PASS only dates the filings its FILINGS table lists, so on a docket
    whose filings were all reconstructed from the file list none of them
    carries a date. Those fall back to the case's own filing date -- itself the
    earliest filing the scrape dated -- so the field states the last date known
    for the case rather than nothing at all.

    :param case: The scraped case.
    :param params: Unused; the docket is the top-level merge.
    :return: The latest filing date, the case's filing date when no filing
        carries one, and `None` when the scrape dates nothing.
    """
    filing_dates = sorted(e.date_filed for e in case.entries if e.date_filed)
    return filing_dates[-1] if filing_dates else case.date_filed


class NYCoADocketMerger(DocketMerger[NYCoACase, None]):
    """Merger for a whole Court-PASS docket. This is the entry point: hand it a
    scraped `NYCoACase` and it merges the docket, its parties and their
    attorneys, its filings and their files, and the NYCoA-only metadata.

    The merge is atomic, so a case either lands in full or not at all. That is
    what makes a failure recoverable -- a re-scrape merges the case again from
    scratch -- but it also means one unstorable value can cost the whole case,
    which is why `_storable_number` drops a misread volume rather than letting
    it raise."""

    model: ClassVar[type[Model]] = Docket

    atomic = True

    court_id: str = Attribute(
        lambda case, params: NYCOA_COURT_ID, strategy=overwrite
    )
    docket_number_core: str = Attribute(
        lambda case, params: make_docket_number_core(case.docket_number),
        strategy=overwrite,
    )
    date_filed: date | None = Attribute(lambda case, params: case.date_filed)
    date_argued: date | None = Attribute(
        lambda case, params: case.argument_date
    )
    date_last_filing: date | None = Attribute(
        _date_last_filing, strategy=overwrite
    )

    parties: list[Party] = PartyRelation(
        NYCoAPartyMerger, party_type=NYCoAPartyTypeMerger
    )
    nycoa_docket_entries: list[NYCoADocketEntry] = DocketEntryRelation(
        NYCoADocketEntryMerger, strategy=ManyStrategy.REPLACE
    )
    nycoa_metadata: NYCoADocketMetadata = OneToOneRelation(
        NYCoADocketMetadataMerger, _case_metadata
    )

    @override
    def merge_one(self) -> tuple[MergeResult[Any], Docket | None]:
        """Merge the case, then take down the published files it has stopped
        pointing at.

        :return: The merge result and the merged docket, unchanged.
        """
        published = self._published_files()
        result, docket = super().merge_one()
        self._withdraw_unreferenced(published)
        return result, docket

    def _published_files(self) -> set[str]:
        """The published files this docket's documents point at, before the
        merge runs.

        :return: The keys, or an empty set for a docket being created, which
            has no documents to have published yet.
        """
        if (docket := self.existing) is None:
            return set()
        return set(
            NYCoADocument.objects.filter(
                docket_entry__docket=docket,
                filepath_local__startswith=PUBLISHED_PREFIX,
            ).values_list("filepath_local", flat=True)
        )

    @staticmethod
    def _withdraw_unreferenced(published: set[str]) -> None:
        """Delete the published files nothing points at any more.

        :param published: The keys the docket pointed at before the merge.
        """
        if not published:
            return
        kept = set(
            NYCoADocument.objects.filter(
                filepath_local__in=published
            ).values_list("filepath_local", flat=True)
        )
        for orphan in published - kept:
            transaction.on_commit(partial(withdraw_file, orphan))

    @override
    def query(self) -> QuerySet[Docket]:
        """The docket this case is, if CourtListener already has it.

        :return: The candidate docket, of which the function returns at most
            one.
        """
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
        """Whether this scrape can be merged at all.

        :param scrape: The scraped case.
        :return: Whether the merge may proceed.
        """
        if not is_nycoa_court(scrape.court_id):
            logger.error("Unknown court id: %s", scrape.court_id)
            return False
        return bool(make_docket_number_core(scrape.docket_number))
