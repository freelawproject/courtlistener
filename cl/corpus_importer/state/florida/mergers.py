import logging
from collections.abc import Sequence
from datetime import date, datetime
from typing import ClassVar, cast, override
from uuid import UUID

from asgiref.sync import async_to_sync
from juriscraper.state.docket import DocketTransfer
from juriscraper.state.florida import (
    FloridaCase,
    FloridaOriginatingCase,
    FloridaParty,
    FloridaPartyRepresentative,
)
from juriscraper.state.florida import (
    FloridaDocketEntry as ScrapeFloridaDocketEntry,
)
from juriscraper.state.florida import (
    FloridaDocument as ScrapeFloridaDocument,
)
from juriscraper.state.florida.cases import FloridaCourtID

from cl.corpus_importer.state.common.case_transfer import (
    CaseTransferMerger,
    CaseTransferRelation,
    inbound_transfers,
)
from cl.corpus_importer.state.common.docket import (
    DocketEntryRelation,
    DocketMerger,
    PartyRelation,
)
from cl.corpus_importer.state.common.docket_entry import (
    AttachmentRelation,
    DocketEntryMerger,
    DocumentMerger,
)
from cl.corpus_importer.state.common.party import (
    AttorneyRelation,
    PartyMerger,
    PartyTypeMerger,
    RoleMerger,
)
from cl.corpus_importer.state.florida.utils import (
    FL_APPELLATE_COURT_ID,
    FLORIDA_COURT_ID_MAP,
    FLORIDA_TRANSFER_COURT_ID_MAP,
    make_docket_number_core,
)
from cl.corpus_importer.state.merger import (
    Ancestor,
    Constant,
    Fn,
    ManyStrategy,
    Merger,
    MergerConfig,
    MergerState,
    OneToOneRelation,
    Params,
    RelatedParams,
    Scrape,
    WithStrategy,
)
from cl.corpus_importer.state.merger.specifications import AttributeMerger
from cl.corpus_importer.state.merger.strategy import overwrite_if_present
from cl.corpus_importer.state.utils import MergeResult
from cl.people_db.models import Attorney, Party, PartyType, Role
from cl.recap.mergers import find_docket_object_query
from cl.search.models import (
    CaseTransfer,
    Court,
    Docket,
    OriginatingCourtInformation,
)
from cl.search.state.florida.models import (
    FloridaDocketEntry,
    FloridaDocument,
)

logger = logging.getLogger(__name__)


class FloridaRoleMerger(
    RoleMerger[FloridaPartyRepresentative, RelatedParams[None]]
):
    role: int = Fn(lambda v: Role.ATTORNEY_LEAD if v else Role.UNKNOWN)(
        Scrape(FloridaPartyRepresentative).primary_flag
    )


class FloridaPartyTypeMerger(
    PartyTypeMerger[FloridaParty, RelatedParams[None]]
):
    pro_se: int = Fn(
        lambda v: PartyType.PRO_SE_YES if v else PartyType.PRO_SE_NO
    )(Scrape(FloridaParty).pro_se_flag)


class FloridaPartyMerger(PartyMerger[FloridaParty, RelatedParams[None]]):
    """Florida identifies parties by UUID, stored in `extra_info`, so a party is matched on that within the docket rather than on its name.

    Two parties on one docket can share a name (e.g. a cross-appellant), and
    matching by name collapses them onto one `Party`.
    """

    config: ClassVar[MergerConfig[Party]] = MergerConfig(
        model=Party, key=("extra_info",)
    )

    attorneys: Sequence[Attorney] = AttorneyRelation(role=FloridaRoleMerger)
    extra_info: str = Fn(str)(Scrape(FloridaParty).party_uuid)

    @override
    def resolve(
        self,
        state: MergerState.Resolve[
            FloridaParty,
            RelatedParams[None],
            Party,
        ],
    ) -> MergerState.ResolveOutput[
        FloridaParty,
        RelatedParams[None],
        Party,
    ]:
        """Take the oldest match.

        A docket can hold two parties with the same UUID where an earlier
        name-based match overwrote one party's UUID with another's; preferring
        the oldest keeps those dockets merging instead of failing on the
        ambiguity.
        """
        results = list(state.candidates)
        if len(results) == 0:
            return state.create()
        return state.update(results[0])


def _content_type(document: ScrapeFloridaDocument) -> str:
    m_len = FloridaDocument._meta.get_field("content_type").max_length
    mime = document.content_type or ""
    if m_len is not None and len(mime) > m_len:
        mime = mime[: (m_len - 3)] + "..."
    return mime


class FloridaDocumentMerger(
    DocumentMerger[
        ScrapeFloridaDocument,
        RelatedParams[list[ScrapeFloridaDocketEntry]],
        FloridaDocument,
    ]
):
    config: ClassVar[MergerConfig[FloridaDocument]] = MergerConfig(
        model=FloridaDocument, key=("link_uuid",)
    )

    document_name: str = Scrape(ScrapeFloridaDocument).document_name
    document_type: str = Fn(lambda v: v or "")(
        Scrape(ScrapeFloridaDocument).document_type
    )
    content_type: str = Fn(_content_type)(Scrape(ScrapeFloridaDocument))
    page_count: int | None = WithStrategy(
        Scrape(ScrapeFloridaDocument).page_count, overwrite_if_present
    )
    file_size: int | None = WithStrategy(
        Scrape(ScrapeFloridaDocument).file_size, overwrite_if_present
    )
    link_uuid: UUID = Scrape(ScrapeFloridaDocument).document_link_uuid

    def scrape_link_uuids(
        self,
        state: MergerState.NonTerminal[
            ScrapeFloridaDocument,
            RelatedParams[RelatedParams[list[ScrapeFloridaDocketEntry]]],
            FloridaDocketEntry,
        ],
    ) -> list[UUID]:
        """Shorthand to get the full set of link UUIDs passed as a parameter to the root merger."""
        return [
            attachment.document_link_uuid
            for entry in state.params.params.params
            for attachment in entry.attachments
        ]

    def scraped_entry(
        self,
        state: MergerState.Lookup[
            ScrapeFloridaDocument,
            RelatedParams[RelatedParams[list[ScrapeFloridaDocketEntry]]],
            FloridaDocument,
        ]
        | MergerState.Resolve[
            ScrapeFloridaDocument,
            RelatedParams[RelatedParams[list[ScrapeFloridaDocketEntry]]],
            FloridaDocument,
        ],
    ) -> ScrapeFloridaDocketEntry | None:
        """Shorthand to get the scraped docket entry for this attachment."""
        entry = cast(FloridaDocketEntry, state.params.parent)
        for scraped_entry in state.params.params.params:
            if scraped_entry.docket_entry_uuid == entry.docket_entry_uuid:
                return scraped_entry
        return None

    @override
    def lookup(
        self,
        state: MergerState.Lookup[
            ScrapeFloridaDocument,
            RelatedParams[RelatedParams[list[ScrapeFloridaDocketEntry]]],
            FloridaDocument,
        ],
    ) -> MergerState.LookupOutput[
        ScrapeFloridaDocument,
        RelatedParams[RelatedParams[list[ScrapeFloridaDocketEntry]]],
        FloridaDocument,
    ]:
        by_uuid = self.stored.filter(link_uuid=self.link_uuid)[:2]
        if len(list(by_uuid)) > 0:
            return state.resolve(by_uuid)

        scraped = self.scraped_entry(state)

        if (
            not scraped
            or [
                attachment.document_name for attachment in scraped.attachments
            ].count(state.scrape.document_name)
            != 1
        ):
            # This is a potential new document.
            return state.resolve([])

        # Stored documents whose link UUID is still in the scrape belong to
        # those attachments (even if they were renamed), so they can't be the
        # one replaced. Excluding them also keeps the candidates stable while
        # sibling attachments merge.
        candidates = self.stored.filter(
            document_name=state.scrape.document_name
        ).exclude(
            link_uuid__in=[
                attachment.document_link_uuid
                for attachment in scraped.attachments
            ]
        )

        if len(list(candidates)) != 1:
            return state.resolve([])
        return state.resolve(candidates)

    @override
    def resolve(
        self,
        state: MergerState.Resolve[
            ScrapeFloridaDocument,
            RelatedParams[RelatedParams[list[ScrapeFloridaDocketEntry]]],
            FloridaDocument,
        ],
    ) -> MergerState.ResolveOutput[
        ScrapeFloridaDocument,
        RelatedParams[RelatedParams[list[ScrapeFloridaDocketEntry]]],
        FloridaDocument,
    ]:
        scraped = self.scraped_entry(state)
        if (
            scraped is not None
            and [a.document_link_uuid for a in scraped.attachments].count(
                self.link_uuid
            )
            > 1
        ):
            de_uuid = cast(
                FloridaDocketEntry, state.params.parent
            ).docket_entry_uuid
            logger.error(
                "Multiple scraped attachments with link UUID %s in docket entry %s",
                self.link_uuid,
                de_uuid,
            )
            return state.failed(
                f"Multiple scraped attachments with link UUID {self.link_uuid} in docket entry {de_uuid}",
                MergeResult.failed(self.config.model.__name__),
            )

        return super().resolve(state)


# Retrieved 2026-07-29
FLORIDA_ENTRY_STATUS_MAP: dict[str, int] = {
    "stricken": FloridaDocketEntry.STATUS_STRICKEN,
    "vacated": FloridaDocketEntry.STATUS_VACATED,
    "docketed": FloridaDocketEntry.STATUS_DOCKETED,
}


def _entry_status(entry: ScrapeFloridaDocketEntry) -> int:
    """Map Florida's `entry_status` string to CL's integer mirror."""
    status = FLORIDA_ENTRY_STATUS_MAP.get(
        entry.entry_status.lower().strip("*")
    )
    if status is None:
        logger.error(
            "Unrecognized Florida docket entry status: %s", entry.entry_status
        )
        return FloridaDocketEntry.STATUS_UNKNOWN
    return status


def _submitted_by_name(entry: ScrapeFloridaDocketEntry) -> str:
    # Florida sends a list, but every entry we've seen has a single submitter.
    return entry.submitted_by[0].display_name if entry.submitted_by else ""


def _submitted_by_id(
    entry: ScrapeFloridaDocketEntry, docket: Docket
) -> int | None:
    """Resolve the submitter to a party on this docket, matching on name the way `PartyMerger` does. Submitters are often court staff rather than case parties, so finding no match is expected and leaves the FK null."""
    name = _submitted_by_name(entry)
    if not name:
        return None
    return (
        docket.parties.filter(name=name).values_list("pk", flat=True).first()
    )


class FloridaDocketEntryMerger(
    DocketEntryMerger[
        ScrapeFloridaDocketEntry,
        list[ScrapeFloridaDocketEntry],
        FloridaDocketEntry,
    ]
):
    config: ClassVar[MergerConfig[FloridaDocketEntry]] = MergerConfig(
        model=FloridaDocketEntry, key=("docket_entry_uuid",)
    )

    # Florida's CL field is a DateTimeField, so override the base's
    # date-only mapping with the scrape's full timestamp. Annotated as the
    # base's `date` because an override can't narrow the declared type.
    date_filed: date = Scrape(ScrapeFloridaDocketEntry).datetime_filed
    date_submitted: datetime = Scrape(ScrapeFloridaDocketEntry).date_submitted
    entry_type_raw: str = Scrape(ScrapeFloridaDocketEntry).entry_type_raw
    entry_name: str = Scrape(ScrapeFloridaDocketEntry).entry_name
    description: str = Scrape(ScrapeFloridaDocketEntry).entry_description
    status: int = Fn(_entry_status)(Scrape(ScrapeFloridaDocketEntry))
    submitted_by_name: str = Fn(_submitted_by_name)(
        Scrape(ScrapeFloridaDocketEntry)
    )
    # Keep a party we resolved on an earlier scrape rather than clearing it
    # when this scrape can't find a match.
    submitted_by_id: int | None = WithStrategy(
        Fn(_submitted_by_id)(
            Scrape(ScrapeFloridaDocketEntry), Ancestor(Docket)
        ),
        overwrite_if_present,
    )
    docket_entry_uuid: UUID = Scrape(
        ScrapeFloridaDocketEntry
    ).docket_entry_uuid
    documents: list[FloridaDocument] = AttachmentRelation(
        FloridaDocumentMerger, strategy=ManyStrategy.REPLACE
    )


def _date_last_filing(docket_data: FloridaCase) -> date | None:
    filing_dates = sorted(
        e.date_filed for e in docket_data.entries if e.date_filed
    )
    return filing_dates[-1] if filing_dates else docket_data.date_filed


def _appeal_from_id(docket_data: FloridaCase) -> str | None:
    # Multiple originating cases are ambiguous, so leave the field unset.
    if len(docket_data.originating_cases) != 1:
        return None
    return FLORIDA_COURT_ID_MAP.get(
        docket_data.originating_cases[0].court_id.value, None
    )


def _appeal_from_str(docket_data: FloridaCase) -> str | None:
    # Multiple originating cases are ambiguous, so leave the field unset.
    if len(docket_data.originating_cases) != 1:
        return ""
    return docket_data.originating_cases[0].court_name


class FloridaOriginatingCourtInformationMerger(
    Merger[
        FloridaOriginatingCase,
        RelatedParams[list[ScrapeFloridaDocketEntry]],
        OriginatingCourtInformation,
    ]
):
    config: ClassVar[MergerConfig[OriginatingCourtInformation]] = MergerConfig(
        model=OriginatingCourtInformation
    )

    docket_number: str = Scrape(FloridaOriginatingCase).case_number
    docket_number_raw: str = Scrape(FloridaOriginatingCase).case_number

    @override
    def lookup(
        self,
        state: MergerState.Lookup[
            FloridaOriginatingCase,
            RelatedParams[list[ScrapeFloridaDocketEntry]],
            OriginatingCourtInformation,
        ],
    ) -> MergerState.LookupOutput[
        FloridaOriginatingCase,
        RelatedParams[list[ScrapeFloridaDocketEntry]],
        OriginatingCourtInformation,
    ]:
        return state.create()


def _originating_case(
    docket_data: FloridaCase, params: list[ScrapeFloridaDocketEntry]
) -> FloridaOriginatingCase | None:
    if docket_data.court_id != FloridaCourtID.SUPREME_COURT.value:
        return None
    if not docket_data.originating_cases:
        return None
    if len(docket_data.originating_cases) > 1:
        logger.warning(
            "Florida docket %s in court %s has multiple originating cases. Using the first one.",
            docket_data.docket_number,
            docket_data.court_id,
        )
    return docket_data.originating_cases[0]


class FloridaCaseTransferMerger(
    CaseTransferMerger[DocketTransfer, RelatedParams[None]]
):
    origin_court_id: str | None = Constant(FLORIDA_TRANSFER_COURT_ID_MAP).get(
        Scrape(DocketTransfer).court_id
    )


def _florida_transfers(
    docket_data: FloridaCase, params: None
) -> list[DocketTransfer]:
    """Filter a case's transfers down to the ones whose far-side court has a CourtListener counterpart in the DB. Skipped transfers are logged but do not fail the merge.

    Args:
        docket_data: The scraped Florida case.
        params: Unused.

    Returns:
        The transfers to merge.
    """
    transferable: list[DocketTransfer] = []
    transfers: list[DocketTransfer] = inbound_transfers(docket_data, params)
    for transfer in transfers:
        court_id = FLORIDA_TRANSFER_COURT_ID_MAP.get(transfer.court_id)
        if court_id is None:
            logger.info(
                "Skipping CaseTransfer for Florida docket %s: no matching court for Juriscraper court %s",
                docket_data.docket_number,
                transfer.court_id,
            )
            continue
        if not Court.objects.filter(pk=court_id).exists():
            logger.error(
                "Court with ID %s not found while creating CaseTransfer for Florida docket %s",
                court_id,
                docket_data.docket_number,
            )
            continue
        transferable.append(transfer)
    return transferable


class FloridaDocketMerger(
    DocketMerger[FloridaCase, list[ScrapeFloridaDocketEntry]]
):
    config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

    court_id: str = Constant(FLORIDA_COURT_ID_MAP)[
        Scrape(FloridaCase).court_id
    ]
    date_last_filing: date | None = Fn(_date_last_filing)(Scrape(FloridaCase))
    docket_number_core: str = Fn(make_docket_number_core)(
        Scrape(FloridaCase).docket_number,
        Constant(FLORIDA_COURT_ID_MAP)[Scrape(FloridaCase).court_id],
    )
    appeal_from_id: str | None = Fn(_appeal_from_id)(Scrape(FloridaCase))
    appeal_from_str: str | None = Fn(_appeal_from_str)(Scrape(FloridaCase))
    # See https://github.com/freelawproject/courtlistener/issues/7361#issuecomment-4566459292
    pacer_case_id: str = Fn(str)(Scrape(FloridaCase).case_uuid)
    originating_court_information: OriginatingCourtInformation = (
        OneToOneRelation(
            FloridaOriginatingCourtInformationMerger,
            cast(
                AttributeMerger,
                Fn(_originating_case)(
                    Scrape(FloridaCase), Params(list[ScrapeFloridaDocketEntry])
                ),
            ),
        )
    )

    parties: Sequence[Party] = PartyRelation(
        FloridaPartyMerger, party_type=FloridaPartyTypeMerger
    )

    florida_docket_entries: list[FloridaDocketEntry] = DocketEntryRelation(
        FloridaDocketEntryMerger
    )

    case_transfer_destination_docket: list[CaseTransfer] = (
        CaseTransferRelation(FloridaCaseTransferMerger, _florida_transfers)
    )

    @override
    def lookup(
        self,
        state: MergerState.Lookup[
            FloridaCase,
            list[ScrapeFloridaDocketEntry],
            Docket,
        ],
    ) -> MergerState.LookupOutput[
        FloridaCase,
        list[ScrapeFloridaDocketEntry],
        Docket,
    ]:
        supreme_court_id = FLORIDA_COURT_ID_MAP[
            FloridaCourtID.SUPREME_COURT.value
        ]
        court_id = FLORIDA_COURT_ID_MAP[state.scrape.court_id]
        dn_core = make_docket_number_core(
            state.scrape.docket_number, court_id=court_id
        )

        query_narrow = async_to_sync(find_docket_object_query)(
            court_id=court_id,
            pacer_case_id=str(state.scrape.case_uuid),
            docket_number=state.scrape.docket_number,
            docket_number_core=dn_core,
            federal_defendant_number=None,
            federal_dn_judge_initials_assigned=None,
            federal_dn_judge_initials_referred=None,
            skip_dn_core_confirmation=True,
            cheap_count=False,
        )

        if court_id == supreme_court_id:
            return state.resolve(query_narrow)

        if query_narrow.count() == 0:
            query_narrow = async_to_sync(find_docket_object_query)(
                court_id=FL_APPELLATE_COURT_ID,
                pacer_case_id=str(state.scrape.case_uuid),
                docket_number=state.scrape.docket_number,
                docket_number_core=dn_core,
                federal_defendant_number=None,
                federal_dn_judge_initials_assigned=None,
                federal_dn_judge_initials_referred=None,
                skip_dn_core_confirmation=True,
                cheap_count=False,
            )

        return state.resolve(query_narrow)

    @staticmethod
    def validator(scrape: FloridaCase) -> bool:
        if scrape.court_id not in FLORIDA_COURT_ID_MAP:
            logger.error("Unknown court id: %s", scrape.court_id)
            return False
        return True
