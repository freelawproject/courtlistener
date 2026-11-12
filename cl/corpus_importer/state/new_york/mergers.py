"""Mergers for New York Court of Appeals (Court-PASS) docket data.

The input is the standard Juriscraper docket format described in
`cl.corpus_importer.state.new_york.court_pass`.
"""

import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Any, ClassVar, cast, override

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import models, transaction
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
    Ancestor,
    Constant,
    Fn,
    ManyStrategy,
    Merger,
    MergerConfig,
    MergerState,
    OneToManyRelation,
    OneToOneRelation,
    RelatedParams,
    Scrape,
    WithStrategy,
    overwrite_if_present,
)
from cl.corpus_importer.state.merger.specifications import AttributeMerger
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
    is_published,
    is_scraped,
)
from cl.corpus_importer.state.new_york.utils import (
    NYCOA_COURT_ID,
    is_nycoa_court,
    issue_code,
    make_docket_number_core,
    mirrored_code,
)
from cl.corpus_importer.state.storage import delete_file
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

PHONE_MAX_LENGTH: int = (
    cast(models.CharField, Attorney._meta.get_field("phone")).max_length or 20
)
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

    Args:
        value: The number the scraper read.
        field: Which number it is, for the log message.
        document: The file it was read from, for the log message.

    Returns:
        The number, or `None` if it is out of range.
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
    """Merge strategy that keeps the path already stored for a document when this scrape has no published one to put there.

    Args:
        scrape: The path this scrape published to, if any.
        db: The path already stored for the document.

    Returns:
        The path to store.
    """
    return (scrape.name or "") or (db.name or "")


def _keep_downloaded[T](scrape: T | None, db: T | None) -> T | None:
    """Merge strategy for scraped files.

    Args:
        scrape: What this scrape's download established, if it made one.
        db: What is already stored for the document.

    Returns:
        The value to store.
    """
    return db if scrape is None or scrape == "" else scrape


def _stated(reading: CourtVocabulary | Unclassified) -> str:
    """The Court-PASS value to store for a field read off a file name.

    `NYCoADocument.doc_role` and `doc_type` are free text mirroring what the
    name itself stated, so a name that stated nothing readable is stored blank
    rather than under one of the reserved readings.

    Args:
        reading: What the scrape schema classified the field as.

    Returns:
        The value Court-PASS's naming convention uses, or the empty string.
    """
    return "" if isinstance(reading, Unclassified) else reading.value


def is_publishable(file: NYCoAFile) -> bool:
    """Whether the scrape vouches for a file it reports having downloaded.

    The file has to be in the private bucket, which is the only place
    publishing looks, and has to carry the hash a later merge tells a
    corrected file from the published one by.

    :param file: A file whose `local_path` the scrape filled in.
    :return: Whether the file may be stored for publishing.
    """
    return is_scraped(file.local_path) and bool(file.content_hash)


class NYCoADocumentMerger[ParamType](
    Merger[NYCoAFile, RelatedParams[ParamType], NYCoADocument]
):
    """Merger for a file Court-PASS published for a filing.

    Subclasses `Merger` rather than the shared `DocumentMerger`, which merges
    `url` and drives a re-download off it changing. Court-PASS serves files
    through form postbacks and publishes no per-file URL, so `url` is left
    empty and `NYCoADocument.download` refuses to fetch by it.

    Nothing needs downloading: the scraper has already fetched the file into
    the private bucket and reports where, so the merge stores that key and the
    loader moves the file into the published layout once the merge has
    committed and the document has the primary key its name needs; see
    `JKentScrapeLoader.publish_files`. The loader then dispatches extraction
    for it.
    """

    config: ClassVar[MergerConfig[NYCoADocument]] = MergerConfig(
        model=NYCoADocument, key=("file_name",)
    )

    file_name: str = Scrape(NYCoAFile).file_name
    content_type: str = Scrape(NYCoAFile).content_type
    doc_role: str = Fn(_stated)(Scrape(NYCoAFile).doc_role)
    doc_party: str = Scrape(NYCoAFile).doc_party
    doc_type: str = Fn(_stated)(Scrape(NYCoAFile).doc_type)
    volume: int | None = Fn(_storable_number)(
        Scrape(NYCoAFile).volume, "volume", Scrape(NYCoAFile)
    )
    part: int | None = Fn(_storable_number)(
        Scrape(NYCoAFile).part, "part", Scrape(NYCoAFile)
    )
    filepath_local: str = WithStrategy(
        Scrape(NYCoAFile).local_path, _keep_stored_file
    )
    sha256: str = WithStrategy(
        Scrape(NYCoAFile).content_hash, _keep_downloaded
    )
    file_size: int | None = WithStrategy(
        Scrape(NYCoAFile).file_size, _keep_downloaded
    )

    @override
    def create(
        self,
        state: MergerState.Create[
            NYCoAFile, RelatedParams[ParamType], NYCoADocument
        ],
    ) -> MergerState.CreateOutput[
        NYCoAFile, RelatedParams[ParamType], NYCoADocument
    ]:
        """Settle which path to store for the file, then write the document."""
        self._accept_file(state.scrape, None)
        return super().create(state)

    @override
    def update(
        self,
        state: MergerState.Update[
            NYCoAFile, RelatedParams[ParamType], NYCoADocument
        ],
    ) -> MergerState.UpdateOutput[
        NYCoAFile, RelatedParams[ParamType], NYCoADocument
    ]:
        """Settle which path to store for the file, then write the document."""
        self._accept_file(state.scrape, state.instance)
        return super().update(state)

    def _scrub_fileinfo(self) -> None:
        """Remove info relevant to file."""
        self.filepath_local = ""
        self.sha256 = ""
        self.file_size = None

    def _accept_file(
        self, scrape: NYCoAFile, existing: NYCoADocument | None
    ) -> None:
        """Decide what the document's `filepath_local` should hold.

        Normally that is the scraper's key in the private bucket, which the
        loader publishes after the merge. Two exceptions: a file this document
        has already published is kept where it is, and the scraper's copy of it
        is deleted once the merge commits, since nothing will ever point at it;
        and a file the scrape cannot vouch for is not stored at all, which
        leaves the document with whatever file it already has.

        Args:
            scrape: The file Court-PASS listed.
            existing: The document being merged into, if there is one.
        """
        private_key = scrape.local_path
        if not private_key:
            return
        stored = (existing.filepath_local.name or "") if existing else ""
        if (
            existing is not None
            and scrape.content_hash
            and existing.sha256 == scrape.content_hash
            and is_published(stored)
        ):
            self.filepath_local = stored
            if is_scraped(private_key):
                transaction.on_commit(
                    partial(
                        delete_file,
                        settings.AWS_PRIVATE_STORAGE_BUCKET_NAME,
                        private_key,
                    )
                )
            return
        if is_publishable(scrape):
            return
        logger.error(
            "Court-PASS file %s was downloaded to %s, which is not in the "
            "private bucket or has no hash recorded; not publishing it.",
            scrape.file_name,
            private_key,
        )
        self._scrub_fileinfo()

    @override
    def pre_update(self, updated_fields: list[str]) -> list[str]:
        """Send a document whose file has moved back for extraction."""
        updated = super().pre_update(updated_fields)
        if not isinstance(self.state, MergerState.Update):
            return updated
        if "filepath_local" not in updated_fields + updated:
            return updated
        self.state.instance.page_count = None
        self.state.instance.ocr_status = None
        updated += ["page_count", "ocr_status"]
        return updated


def _served_attachments(
    entry: NYCoDocketEntry, params: Any
) -> Sequence[NYCoAFile]:
    """The filing's files Court-PASS will actually hand over.

    Args:
        entry: The filing whose files to merge.
        params: Unused; matches the transform signature.

    Returns:
        The files that get a document row.
    """
    return [file for file in entry.attachments if file.available]


def _entry_party_id(entry: NYCoDocketEntry, docket: Docket) -> int | None:
    """Resolve the filing's party to a party on this docket, matching on the name the way `PartyMerger` does, with the filing's role breaking a tie.

    Args:
        entry: The filing whose party to resolve.
        docket: The docket the filing belongs to.

    Returns:
        The party's pk, or `None` when the docket lists no party of that
        name. A filer with no attorney of record is one the FILINGS table names
        and the ATTORNEY DETAILS section never does; `party_name` keeps the
        name whether or not this resolves.
    """
    if not entry.party:
        return None
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
    """Merge strategy that keeps the party name an earlier scrape recorded when this one read none, rather than blanking it."""
    return scrape or db or ""


class NYCoADocketEntryMerger[ParamType](
    Merger[NYCoDocketEntry, RelatedParams[ParamType], NYCoADocketEntry]
):
    """Merger for a Court-PASS filing.

    Subclasses `Merger` rather than the shared `DocketEntryMerger`, whose
    cross-state entry type NYCoA does not store -- the Court's own filing type
    vocabulary is normalized instead.
    """

    config: ClassVar[MergerConfig[NYCoADocketEntry]] = MergerConfig(
        model=NYCoADocketEntry, key=("docket_entry_id",)
    )

    # Court-PASS only dates the filings its FILINGS table lists.
    date_filed: date | None = Scrape(NYCoDocketEntry).date_filed
    date_due: date | None = Scrape(NYCoDocketEntry).date_due
    docket_entry_id: str = Scrape(NYCoDocketEntry).docket_entry_id
    entry_index: int | None = Scrape(NYCoDocketEntry).entry_index
    filing_type: int = Fn(mirrored_code)(
        FilingType, Scrape(NYCoDocketEntry).entry_filing_type
    )
    filing_type_raw: str = Scrape(NYCoDocketEntry).raw_filing_type
    filing_role: int = Fn(mirrored_code)(
        FilingRole, Scrape(NYCoDocketEntry).entry_role
    )
    filing_doctype: int = Fn(mirrored_code)(
        FilingDocType, Scrape(NYCoDocketEntry).entry_doctype
    )
    # Keep a party we resolved on an earlier scrape rather than clearing it
    # when this scrape can't find a match.
    party_id: int | None = WithStrategy(
        Fn(_entry_party_id)(Scrape(NYCoDocketEntry), Ancestor(Docket)),
        overwrite_if_present,
    )
    # The name Court-PASS printed, kept whether or not `party_id` resolved --
    # on a filing by a party with no attorney of record it is the only record
    # of who filed.
    party_name: str = WithStrategy(
        Scrape(NYCoDocketEntry).party, _keep_party_name
    )
    # Court-PASS lists every file it has for a case, so a file that is gone
    # from the list -- or that it has stopped serving -- is gone from the
    # case.
    documents: list[NYCoADocument] = AttachmentRelation(
        NYCoADocumentMerger,
        transform=_served_attachments,
        strategy=ManyStrategy.REPLACE,
    )

    @override
    def update(
        self,
        state: MergerState.Update[
            NYCoDocketEntry, RelatedParams[ParamType], NYCoADocketEntry
        ],
    ) -> MergerState.UpdateOutput[
        NYCoDocketEntry, RelatedParams[ParamType], NYCoADocketEntry
    ]:
        """Drop any document the filing no longer serves a file for, then merge the filing."""
        self._drop_unserved_documents(state.scrape, state.instance)
        return super().update(state)

    @staticmethod
    def _drop_unserved_documents(
        scrape: NYCoDocketEntry, entry: NYCoADocketEntry
    ) -> None:
        """Delete the documents of a filing Court-PASS now serves no file for.

        This exists to handle the special case of all documents being retracted.

        Args:
            scrape: The filing as Court-PASS lists it.
            entry: The stored filing.
        """
        if not scrape.attachments:
            return
        if any(file.available for file in scrape.attachments):
            return
        # Not through `entry.documents`: the documents the entry was loaded
        # with are missing fields the deletion signals read.
        _ = NYCoADocument.objects.filter(docket_entry=entry).delete()


class ScrapedAttorney(NYCoAAttorney):
    """One of a party's attorneys, with what the role merger needs beyond the attorney.

    Attributes:
        primary: Whether this is the first attorney Court-PASS listed for the
            party. Court-PASS never states an attorney's role, so the role follows
            the convention the other states' mergers use -- the first attorney
            listed is the party's lead and the rest are unknown -- which a child
            merger cannot work out on its own because it cannot see its siblings.
    """

    primary: bool = False


def _attorney_contact_raw(attorney: NYCoAAttorney) -> str:
    """Fold the firm and address Court-PASS prints for an attorney into the one free-text contact field CourtListener keeps for them."""
    parts = [attorney.firm, attorney.address]
    if (phone := attorney.phone.strip()) != _attorney_phone(attorney):
        parts.append(phone)
    return "\n".join(part for part in parts if part)


def _attorney_phone(attorney: NYCoAAttorney) -> str:
    """The attorney's phone number, trimmed to fit `Attorney.phone`."""
    phone = attorney.phone.strip()
    if len(phone) <= PHONE_MAX_LENGTH:
        return phone
    number, extension, _ = phone.partition(" ext")
    if extension and len(number) <= PHONE_MAX_LENGTH:
        return number
    return phone[:PHONE_MAX_LENGTH]


class NYCoAAttorneyMerger(
    AttorneyMerger[ScrapedAttorney, RelatedParams[RelatedParams[None]]]
):
    """Merger for an attorney on a Court-PASS docket."""

    contact_raw: str = Fn(_attorney_contact_raw)(Scrape(ScrapedAttorney))
    phone: str = Fn(_attorney_phone)(Scrape(ScrapedAttorney))


def _attorney_role(attorney: ScrapedAttorney) -> int:
    """The role to store for an attorney Court-PASS lists for a party.

    Court-PASS states which party an attorney represents but never in what
    role, and the role is not nullable, so the attorney the Court listed first
    is stored as the party's lead and the rest as unknown -- the convention the
    other states' mergers follow. See `ScrapedAttorney`.

    Args:
        attorney: The attorney, marked with whether the Court listed it
            first.

    Returns:
        The `Role` code to store.
    """
    return Role.ATTORNEY_LEAD if attorney.primary else Role.UNKNOWN


class NYCoARoleMerger(RoleMerger[ScrapedAttorney, RelatedParams[None]]):
    """Merger for the link between a Court-PASS attorney and the party.

    Overrides only `role`, which Court-PASS never states; see
    `_attorney_role`.
    """

    role: int = Fn(_attorney_role)(Scrape(ScrapedAttorney))


def _party_type_name(party: NYCoAParty) -> str:
    """Prefer the role Court-PASS printed.

    The cross-state `PartyType` vocabulary has no value for several roles the
    Court of Appeals uses, amicus curiae among them, so normalizing here would
    lose them.
    """
    return party.party_role_raw or party.party_type.value.title()


class NYCoAPartyTypeMerger(PartyTypeMerger[NYCoAParty, RelatedParams[None]]):
    """Merger for a party's role on a Court-PASS docket."""

    name: str = Fn(_party_type_name)(Scrape(NYCoAParty))


def _party_attorneys(party: NYCoAParty, params: Any) -> list[ScrapedAttorney]:
    """The party's attorneys, each marked with whether the Court listed it first.

    Which attorney that is decides the role stored for all of them, and only
    the party sees them all at once. See `ScrapedAttorney`.
    """
    return [
        # `dict` copies the scraped fields across without re-serializing them.
        ScrapedAttorney(**dict(attorney), primary=index == 0)
        for index, attorney in enumerate(party.representatives)
    ]


class NYCoAPartyMerger(PartyMerger[NYCoAParty, RelatedParams[None]]):
    """Merger for a party on a Court-PASS docket.

    Identity is `PartyMerger`'s -- the name, within the docket -- with the role
    breaking a tie; see `resolve`.
    """

    attorneys: Sequence[Attorney] = AttorneyRelation(
        attorney=NYCoAAttorneyMerger,
        role=NYCoARoleMerger,
        transform=_party_attorneys,
    )

    @override
    def resolve(
        self,
        state: MergerState.Resolve[
            NYCoAParty,
            RelatedParams[None],
            Party,
        ],
    ) -> MergerState.ResolveOutput[
        NYCoAParty,
        RelatedParams[None],
        Party,
    ]:
        """Pick which of the docket's parties this scraped one is.

        A name is not unique on a Court-PASS docket. We make a best effort here
        to match parties when they have the same name (family cases), and log when
        we can't disambiguate.

        Args:
            state: Carries the candidates `PartyMerger.lookup` found. A
                name no role settles is refused rather than guessed.

        Returns:
            The state to continue in: creating, updating the row to
            merge into, or failed.
        """
        candidates = list(state.candidates)
        if len(candidates) == 0:
            return state.create()
        if len(candidates) == 1:
            return state.update(candidates[0])

        docket = cast(Docket, state.params.parent)
        role = _party_type_name(state.scrape)
        for candidate in candidates:
            if candidate.party_types.filter(
                docket=docket, name__iexact=role
            ).exists():
                return state.update(candidate)
        logger.error(
            "Docket %s lists %s under several roles and none is %s; refusing "
            "to guess which party this is.",
            docket.docket_number,
            state.scrape.name,
            role,
        )
        return state.failed(
            "Ambiguous party", MergeResult.failed(Party.__name__)
        )


@dataclass(frozen=True)
class ScrapedIssue:
    """One of a case's issues, with what the merger needs beyond the issue.

    Attributes:
        issue: The issue as the scraper classified it.
        category: The code stored for the issue's category.
        subcategory: The code stored for the issue's subcategory.
        alone_in_category: Whether this is the only issue the scrape states
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
    those it joins the identity; see `lookup`.
    """

    config: ClassVar[MergerConfig[NYCoADocketIssue]] = MergerConfig(
        model=NYCoADocketIssue, key=("category", "subcategory")
    )

    category: int = Scrape(ScrapedIssue).category
    subcategory: int = Scrape(ScrapedIssue).subcategory
    category_raw: str = Scrape(ScrapedIssue).issue.category_raw
    detail: str = Scrape(ScrapedIssue).issue.detail

    @override
    def lookup(
        self,
        state: MergerState.Lookup[
            ScrapedIssue,
            RelatedParams[ParamType],
            NYCoADocketIssue,
        ],
    ) -> MergerState.LookupOutput[
        ScrapedIssue,
        RelatedParams[ParamType],
        NYCoADocketIssue,
    ]:
        """The issues already stored on this case under the same category pair.

        Narrows to the description as well when the scrape states another issue
        under that pair. Matching on the pair alone would then hand both scraped
        issues whichever row was found first, merging two issues into one; the
        description is what the Court tells them apart by, so it is what the
        merger has to as well.

        Returns:
            The candidate rows, oldest first, so that `resolve` is
            deterministic.
        """
        candidates = self.stored.filter(
            category=self.category,
            subcategory=self.subcategory,
        )
        if not state.scrape.alone_in_category:
            candidates = candidates.filter(detail=self.detail)
        return state.resolve(candidates.order_by("pk"))

    @override
    def resolve(
        self,
        state: MergerState.Resolve[
            ScrapedIssue,
            RelatedParams[ParamType],
            NYCoADocketIssue,
        ],
    ) -> MergerState.ResolveOutput[
        ScrapedIssue,
        RelatedParams[ParamType],
        NYCoADocketIssue,
    ]:
        """Pick which of the stored issues this scraped one is.

        Several rows can share a category pair -- an earlier scrape stated two
        issues under it and this one states fewer -- and all of them are
        candidates for the same issue. The row whose description still matches
        wins, so a case that kept an issue and dropped another keeps the right
        row; failing that the oldest does, and `ManyStrategy.REPLACE` on the
        relation prunes the rest.

        Args:
            state: Carries the candidates `lookup` found.

        Returns:
            The state to continue in: creating, or updating the row to
            merge into.
        """
        candidates = list(state.candidates)

        if not candidates:
            return state.create()
        detail = self.detail
        return state.update(
            next(
                (
                    candidate
                    for candidate in candidates
                    if candidate.detail == detail
                ),
                candidates[0],
            )
        )


def _case_issues(case: NYCoACase) -> Sequence[ScrapedIssue]:
    """The case's issues, each paired with the codes it is stored under.

    The codes are classified here rather than in the child merger because
    whether another issue shares an issue's category pair decides how the
    merger identifies it, and only the case sees all of them at once. See
    `ScrapedIssue`.
    """
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

    The `OneToOneField` lives on this model rather than on `Docket`, so this is
    the reverse side of the relation: `OneToOneMerger` fills in `docket` from
    the parent and matches on it, and this merger must not declare it.
    """

    config: ClassVar[MergerConfig[NYCoADocketMetadata]] = MergerConfig(
        model=NYCoADocketMetadata
    )

    # Court-PASS states a case's issues in full, so an issue that is gone from
    # the scrape is one the Court removed.
    issues: list[NYCoADocketIssue] = OneToManyRelation(
        NYCoAIssueMerger,
        cast(AttributeMerger, Fn(_case_issues)(Scrape(NYCoACase))),
        strategy=ManyStrategy.REPLACE,
    )
    decision_date: date | None = Scrape(NYCoACase).decision_date
    official_citation: str = Scrape(NYCoACase).official_citation
    lower_court_citation: str = Scrape(NYCoACase).lower_court_citation


def _date_last_filing(case: NYCoACase) -> date | None:
    """The date the case's most recent dated filing was received.

    Court-PASS only dates the filings its FILINGS table lists, so on a docket
    whose filings were all reconstructed from the file list none of them
    carries a date. Those fall back to the case's own filing date -- itself the
    earliest filing the scrape dated -- so the field states the last date known
    for the case rather than nothing at all.

    Args:
        case: The scraped case.

    Returns:
        The latest filing date, the case's filing date when no filing
        carries one, and `None` when the scrape dates nothing.
    """
    filing_dates = sorted(e.date_filed for e in case.entries if e.date_filed)
    return filing_dates[-1] if filing_dates else case.date_filed


class NYCoADocketMerger(DocketMerger[NYCoACase, None]):
    """Merger for a whole Court-PASS docket.

    This is the entry point: hand it a scraped `NYCoACase` and it merges the
    docket, its parties and their attorneys, its filings and their files, and
    the NYCoA-only metadata.

    The merge is atomic, so a case either lands in full or not at all. That is
    what makes a failure recoverable -- a re-scrape merges the case again from
    scratch -- but it also means one unstorable value can cost the whole case,
    which is why `_storable_number` drops a misread volume rather than letting
    it raise.
    """

    court_id: str = Constant(NYCOA_COURT_ID)
    docket_number_core: str = Fn(make_docket_number_core)(
        Scrape(NYCoACase).docket_number
    )
    date_filed: date | None = WithStrategy(
        Scrape(NYCoACase).date_filed, overwrite_if_present
    )
    date_argued: date | None = WithStrategy(
        Scrape(NYCoACase).argument_date, overwrite_if_present
    )
    date_last_filing: date | None = Fn(_date_last_filing)(Scrape(NYCoACase))

    parties: Sequence[Party] = PartyRelation(
        NYCoAPartyMerger, party_type=NYCoAPartyTypeMerger
    )
    nycoa_docket_entries: list[NYCoADocketEntry] = DocketEntryRelation(
        NYCoADocketEntryMerger, strategy=ManyStrategy.REPLACE
    )
    # The NYCoA metadata is spread across the case's own fields rather than
    # nested under a key of its own, so the metadata merger takes the case.
    nycoa_metadata: NYCoADocketMetadata = OneToOneRelation(
        NYCoADocketMetadataMerger, cast(AttributeMerger, Scrape(NYCoACase))
    )

    stored_files: Mapping[int, tuple[str, str]] = {}
    """The file and thumbnail each of the docket's documents pointed at before
    the merge, keyed by the document's primary key. The loader deletes the
    files of whichever of them the merge removed."""

    @override
    def update(
        self,
        state: MergerState.Update[NYCoACase, None, Docket],
    ) -> MergerState.UpdateOutput[NYCoACase, None, Docket]:
        """Note the files the docket's documents point at, then merge the case."""
        self.stored_files = {
            pk: (path or "", thumbnail or "")
            for pk, path, thumbnail in NYCoADocument.objects.filter(
                docket_entry__docket=state.instance
            ).values_list("pk", "filepath_local", "thumbnail")
        }
        return super().update(state)

    @override
    def lookup(
        self,
        state: MergerState.Lookup[
            NYCoACase,
            None,
            Docket,
        ],
    ) -> MergerState.LookupOutput[
        NYCoACase,
        None,
        Docket,
    ]:
        """The docket this case is, if CourtListener already has it.

        Returns:
            The candidate docket, of which the function returns at most
            one.
        """
        return state.resolve(
            async_to_sync(find_docket_object_query)(
                court_id=NYCOA_COURT_ID,
                pacer_case_id=None,
                docket_number=state.scrape.docket_number,
                docket_number_core=make_docket_number_core(
                    state.scrape.docket_number
                ),
                federal_defendant_number=None,
                federal_dn_judge_initials_assigned=None,
                federal_dn_judge_initials_referred=None,
                skip_dn_core_confirmation=True,
                cheap_count=False,
            ),
        )

    @staticmethod
    def validator(scrape: NYCoACase) -> bool:
        """Whether this scrape can be merged at all.

        Args:
            scrape: The scraped case.

        Returns:
            Whether the merge may proceed.
        """
        if not is_nycoa_court(scrape.court_id):
            logger.error("Unknown court id: %s", scrape.court_id)
            return False
        return bool(make_docket_number_core(scrape.docket_number))
