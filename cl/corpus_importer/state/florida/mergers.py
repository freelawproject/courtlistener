import logging
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any, ClassVar, override
from uuid import UUID

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
from cl.people_db.models import Attorney, Party, Role
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


class FloridaPartyMerger(PartyMerger[FloridaParty, RelatedParams[None]]):
    attorneys: list[Attorney] = AttorneyRelation(role=FloridaRoleMerger)


def _document_type(document: ScrapeFloridaDocument, params: Any) -> str:
    return document.document_type or ""


class FloridaDocumentMerger[ParamType](
    DocumentMerger[ScrapeFloridaDocument, ParamType, FloridaDocument]
):
    model: ClassVar[type[Model]] = FloridaDocument
    key: ClassVar[Iterable[str]] = ["link_uuid"]

    document_name: str = Attribute(
        lambda doc, params: doc.document_name, strategy=overwrite
    )
    document_type: str = Attribute(_document_type, strategy=overwrite)
    content_type: str | None = Attribute(lambda doc, params: doc.content_type)
    page_count: int | None = Attribute(lambda doc, params: doc.page_count)
    file_size: int | None = Attribute(lambda doc, params: doc.file_size)
    link_uuid: UUID = Attribute(
        lambda doc, params: doc.document_link_uuid, strategy=overwrite
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
    status: str = Attribute(
        lambda e, params: e.entry_status, strategy=overwrite
    )
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

    parties: list[Party] = PartyRelation(FloridaPartyMerger)

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
        query = Docket.objects.filter(
            docket_number_core=make_docket_number_core(
                self.scrape.docket_number
            )
        )
        query_narrow = query.filter(court_id=court_id)
        query_narrow_with_uuid = query_narrow.filter(
            pacer_case_id=str(self.scrape.case_uuid)
        )

        if query_narrow_with_uuid.exists():
            return query_narrow_with_uuid

        if court_id == supreme_court_id:
            return query_narrow

        query_broad = query.filter(court_id=FL_APPELLATE_COURT_ID)
        query_broad_with_uuid = query_broad.filter(
            pacer_case_id=str(self.scrape.case_uuid)
        )
        if query_broad_with_uuid.exists():
            return query_broad_with_uuid

        return query_broad

    @staticmethod
    def validate(scrape: FloridaCase) -> bool:
        if scrape.court_id not in FLORIDA_COURT_ID_MAP:
            logger.error("Unknown court id: %s", scrape.court_id)
            return False
        return True
