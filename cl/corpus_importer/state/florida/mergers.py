import logging
from datetime import date
from typing import Any, ClassVar, override

from django.db.models import Model, QuerySet
from juriscraper.state.florida import (
    FloridaCase,
    FloridaOriginatingCase,
    FloridaParty,
    FloridaPartyRepresentative,
)
from juriscraper.state.florida.cases import FloridaCourtID

from cl.corpus_importer.state.common.docket import (
    DocketMerger,
    PartyRelation,
)
from cl.corpus_importer.state.common.party import (
    AttorneyRelation,
    PartyMerger,
    RoleMerger,
)
from cl.corpus_importer.state.florida.utils import (
    FL_APPELLATE_COURT_ID,
    FLORIDA_COURT_ID_MAP,
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
from cl.search.models import Docket, OriginatingCourtInformation

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

    parties: list[Party] = PartyRelation(party=FloridaPartyMerger)

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
