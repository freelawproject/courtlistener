import logging
from datetime import date
from typing import ClassVar, override

from asgiref.sync import async_to_sync
from django.db.models import Model, QuerySet
from juriscraper.state.florida import FloridaCase, FloridaOriginatingCase
from juriscraper.state.florida.cases import FloridaCourtID

from cl.corpus_importer.state.florida.utils import (
    FL_APPELLATE_COURT_ID,
    FLORIDA_COURT_ID_MAP,
    make_docket_number_core,
)
from cl.corpus_importer.state.merger import (
    Attribute,
    Merger,
    OneToOneRelation,
    overwrite,
)
from cl.recap.mergers import find_docket_object_query
from cl.search.models import Docket, OriginatingCourtInformation

logger = logging.getLogger(__name__)


def add_scraper_source(scrape: int | None, db: int | None) -> int:
    if not db:
        db = 0
    if db in Docket.NON_SCRAPER_SOURCES():
        return db + Docket.SCRAPER
    return db


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
    Merger[FloridaOriginatingCase, None, OriginatingCourtInformation]
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


class FloridaDocketMerger(Merger[FloridaCase, None, Docket]):
    model: ClassVar[type[Model]] = Docket

    atomic = True

    court_id: str = Attribute(
        lambda d, params: FLORIDA_COURT_ID_MAP[d.court_id],
        strategy=overwrite,
    )
    source: int = Attribute(
        lambda _, params: Docket.SCRAPER,
        strategy=add_scraper_source,
    )
    date_filed: date | None = Attribute(
        lambda d, params: d.date_filed,
        strategy=overwrite,
    )
    date_last_filing: date | None = Attribute(
        _date_last_filing,
        strategy=overwrite,
    )
    case_name: str = Attribute(
        lambda d, params: d.case_name, strategy=overwrite
    )
    case_name_full: str = Attribute(
        lambda d, params: d.case_name_full,
        strategy=overwrite,
    )
    case_name_short: str = Attribute(
        lambda d, params: d.case_name, strategy=overwrite
    )
    docket_number: str = Attribute(
        lambda d, params: d.docket_number,
        strategy=overwrite,
    )
    docket_number_raw: str = Attribute(
        lambda d, params: d.docket_number, strategy=overwrite
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
            )

        return query_narrow

    @staticmethod
    def validate(scrape: FloridaCase) -> bool:
        if scrape.court_id not in FLORIDA_COURT_ID_MAP:
            logger.error("Unknown court id: %s", scrape.court_id)
            return False
        return True
