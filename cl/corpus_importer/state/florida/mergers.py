import logging
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any, ClassVar, cast, override
from uuid import UUID

from asgiref.sync import async_to_sync
from django.db.models import Model, QuerySet
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
    Attribute,
    Merger,
    OneToOneRelation,
    RelatedParams,
    ThroughParameters,
    overwrite,
)
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


def _florida_representative_role(
    representative: FloridaPartyRepresentative, params: ThroughParameters[Any]
) -> int:
    return Role.ATTORNEY_LEAD if representative.primary_flag else Role.UNKNOWN


class FloridaRoleMerger(
    RoleMerger[FloridaPartyRepresentative, RelatedParams[None]]
):
    role: int = Attribute(_florida_representative_role)


def _florida_pro_se(party: FloridaParty, params: None) -> int:
    return PartyType.PRO_SE_YES if party.pro_se_flag else PartyType.PRO_SE_NO


class FloridaPartyTypeMerger(
    PartyTypeMerger[FloridaParty, RelatedParams[None]]
):
    pro_se: int = Attribute(_florida_pro_se)


def _florida_party_uuid(party: FloridaParty, params: None) -> str:
    return str(party.party_uuid)


class FloridaPartyMerger(PartyMerger[FloridaParty, RelatedParams[None]]):
    key: ClassVar[Iterable[str]] = ["extra_info"]

    attorneys: list[Attorney] = AttorneyRelation(role=FloridaRoleMerger)
    extra_info: str = Attribute(_florida_party_uuid)

    def query(self) -> QuerySet[Party]:
        return super().query().order_by("date_created")

    def resolve_query(self, qs: QuerySet[Party]) -> tuple[bool, Party | None]:
        results = list(qs)
        if len(results) == 0:
            return True, None
        return True, results[0]


def _document_type(document: ScrapeFloridaDocument, params: Any) -> str:
    return document.document_type or ""


def _content_type(document: ScrapeFloridaDocument, params: Any) -> str:
    m_len = FloridaDocument._meta.get_field("content_type").max_length
    mime = document.content_type or ""
    if len(mime) > m_len:
        mime = mime[: (m_len - 3)] + "..."
    return mime


class FloridaDocumentMerger[ParamType](
    DocumentMerger[ScrapeFloridaDocument, ParamType, FloridaDocument]
):
    model: ClassVar[type[Model]] = FloridaDocument
    key: ClassVar[Iterable[str]] = ["link_uuid"]

    document_name: str = Attribute(
        lambda doc, params: doc.document_name, strategy=overwrite
    )
    document_type: str = Attribute(_document_type, strategy=overwrite)
    content_type: str = Attribute(_content_type, strategy=overwrite)
    page_count: int | None = Attribute(lambda doc, params: doc.page_count)
    file_size: int | None = Attribute(lambda doc, params: doc.file_size)
    link_uuid: UUID = Attribute(
        lambda doc, params: doc.document_link_uuid, strategy=overwrite
    )


# Retrieved 2026-07-29
FLORIDA_ENTRY_STATUS_MAP: dict[str, int] = {
    "stricken": FloridaDocketEntry.STATUS_STRICKEN,
    "vacated": FloridaDocketEntry.STATUS_VACATED,
    "docketed": FloridaDocketEntry.STATUS_DOCKETED,
}


def _entry_status(entry: ScrapeFloridaDocketEntry, params: Any) -> int:
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


def _submitted_by_name(entry: ScrapeFloridaDocketEntry, params: Any) -> str:
    # Florida sends a list, but every entry we've seen has a single submitter.
    return entry.submitted_by[0].display_name if entry.submitted_by else ""


def _submitted_by_id(
    entry: ScrapeFloridaDocketEntry, params: RelatedParams[Any]
) -> int | None:
    """Resolve the submitter to a party on this docket, matching on name the
    way `PartyMerger` does. Submitters are often court staff rather than case
    parties, so finding no match is expected and leaves the FK null."""
    name = _submitted_by_name(entry, params)
    if not name:
        return None
    docket = cast(Docket, params.parent)
    return (
        docket.parties.filter(name=name).values_list("pk", flat=True).first()
    )


class FloridaDocketEntryMerger[ParamType](
    DocketEntryMerger[
        ScrapeFloridaDocketEntry,
        ParamType,
        FloridaDocketEntry,
    ]
):
    model: ClassVar[type[Model]] = FloridaDocketEntry
    key: ClassVar[Iterable[str]] = ["docket_entry_uuid"]

    # Florida's CL field is a DateTimeField, so override the base's
    # date-only mapping with the scrape's full timestamp.
    date_filed: datetime = Attribute(
        lambda e, params: e.datetime_filed, strategy=overwrite
    )
    date_submitted: datetime = Attribute(
        lambda e, params: e.date_submitted, strategy=overwrite
    )
    entry_type_raw: str = Attribute(
        lambda e, params: e.entry_type_raw, strategy=overwrite
    )
    entry_name: str = Attribute(
        lambda e, params: e.entry_name, strategy=overwrite
    )
    description: str = Attribute(
        lambda e, params: e.entry_description, strategy=overwrite
    )
    status: int = Attribute(_entry_status, strategy=overwrite)
    submitted_by_name: str = Attribute(_submitted_by_name, strategy=overwrite)
    # Keep a party we resolved on an earlier scrape rather than clearing it
    # when this scrape can't find a match.
    submitted_by_id: int | None = Attribute(_submitted_by_id)
    docket_entry_uuid: UUID = Attribute(
        lambda e, params: e.docket_entry_uuid, strategy=overwrite
    )
    documents: list[FloridaDocument] = AttachmentRelation(
        FloridaDocumentMerger
    )


def _date_last_filing(docket_data: FloridaCase, params: None) -> date | None:
    filing_dates = sorted(
        e.date_filed for e in docket_data.entries if e.date_filed
    )
    return filing_dates[-1] if filing_dates else docket_data.date_filed


def _appeal_from_id(docket_data: FloridaCase, params: None) -> str | None:
    # Multiple originating cases are ambiguous, so leave the field unset.
    if len(docket_data.originating_cases) != 1:
        return None
    return FLORIDA_COURT_ID_MAP.get(
        docket_data.originating_cases[0].court_id.value, None
    )


def _appeal_from_str(docket_data: FloridaCase, params: None) -> str | None:
    # Multiple originating cases are ambiguous, so leave the field unset.
    if len(docket_data.originating_cases) != 1:
        return ""
    return docket_data.originating_cases[0].court_name


class FloridaOriginatingCourtInformationMerger(
    Merger[
        FloridaOriginatingCase,
        RelatedParams[None],
        OriginatingCourtInformation,
    ]
):
    model: ClassVar[type[Model]] = OriginatingCourtInformation

    docket_number: str = Attribute(
        lambda oc, params: oc.case_number, strategy=overwrite
    )
    docket_number_raw: str = Attribute(
        lambda oc, params: oc.case_number, strategy=overwrite
    )

    def query(self) -> QuerySet[OriginatingCourtInformation]:
        return OriginatingCourtInformation.objects.none()


def _originating_case(
    docket_data: FloridaCase, params: None
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


def _origin_court_id(transfer: DocketTransfer, params: Any) -> str | None:
    return FLORIDA_TRANSFER_COURT_ID_MAP.get(transfer.court_id)


class FloridaCaseTransferMerger(CaseTransferMerger[DocketTransfer, None]):
    origin_court_id: str = Attribute(_origin_court_id, strategy=overwrite)


def _florida_transfers(
    docket_data: FloridaCase, params: None
) -> list[DocketTransfer]:
    """Filter a case's transfers down to the ones whose far-side court has a
    CourtListener counterpart in the DB. Skipped transfers are logged but do
    not fail the merge.

    :param docket_data: The scraped Florida case.
    :return: The transfers to merge."""
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


class FloridaDocketMerger(DocketMerger[FloridaCase, None]):
    model: ClassVar[type[Model]] = Docket

    atomic = True

    court_id: str = Attribute(
        lambda d, params: FLORIDA_COURT_ID_MAP[d.court_id],
        strategy=overwrite,
    )
    date_last_filing: date | None = Attribute(
        _date_last_filing,
        strategy=overwrite,
    )
    docket_number_core: str = Attribute(
        lambda d, params: make_docket_number_core(
            d.docket_number, court_id=FLORIDA_COURT_ID_MAP[d.court_id]
        ),
        strategy=overwrite,
    )
    appeal_from_id: str | None = Attribute(_appeal_from_id, strategy=overwrite)
    appeal_from_str: str | None = Attribute(
        _appeal_from_str, strategy=overwrite
    )
    # See https://github.com/freelawproject/courtlistener/issues/7361#issuecomment-4566459292
    pacer_case_id: str = Attribute(
        lambda d, params: str(d.case_uuid), strategy=overwrite
    )
    originating_court_information: OriginatingCourtInformation = (
        OneToOneRelation(
            FloridaOriginatingCourtInformationMerger,
            _originating_case,
        )
    )

    parties: list[Party] = PartyRelation(
        FloridaPartyMerger, party_type=FloridaPartyTypeMerger
    )

    florida_docket_entries: list[FloridaDocketEntry] = DocketEntryRelation(
        FloridaDocketEntryMerger
    )

    case_transfer_destination_docket: list[CaseTransfer] = (
        CaseTransferRelation(FloridaCaseTransferMerger, _florida_transfers)
    )

    @override
    def query(self) -> QuerySet[Docket]:
        supreme_court_id = FLORIDA_COURT_ID_MAP[
            FloridaCourtID.SUPREME_COURT.value
        ]
        court_id = FLORIDA_COURT_ID_MAP[self.scrape.court_id]
        dn_core = make_docket_number_core(
            self.scrape.docket_number, court_id=court_id
        )

        query_narrow = async_to_sync(find_docket_object_query)(
            court_id=court_id,
            pacer_case_id=str(self.scrape.case_uuid),
            docket_number=self.scrape.docket_number,
            docket_number_core=dn_core,
            federal_defendant_number=None,
            federal_dn_judge_initials_assigned=None,
            federal_dn_judge_initials_referred=None,
            skip_dn_core_confirmation=True,
            cheap_count=False,
        )

        if court_id == supreme_court_id:
            return query_narrow

        if query_narrow.count() == 0:
            return async_to_sync(find_docket_object_query)(
                court_id=FL_APPELLATE_COURT_ID,
                pacer_case_id=str(self.scrape.case_uuid),
                docket_number=self.scrape.docket_number,
                docket_number_core=dn_core,
                federal_defendant_number=None,
                federal_dn_judge_initials_assigned=None,
                federal_dn_judge_initials_referred=None,
                skip_dn_core_confirmation=True,
                cheap_count=False,
            )

        return query_narrow

    @staticmethod
    def validate(scrape: FloridaCase) -> bool:
        if scrape.court_id not in FLORIDA_COURT_ID_MAP:
            logger.error("Unknown court id: %s", scrape.court_id)
            return False
        return True
