import logging
from datetime import date
from typing import Any, ClassVar

from django.db.models import Model, QuerySet
from juriscraper.state.florida import (
    FloridaCase,
    FloridaOriginatingCase,
    FloridaParty,
)
from juriscraper.state.florida.cases import FloridaCourtID

from cl.corpus_importer.state.florida.utils import (
    FLORIDA_COURT_ID_MAP,
    make_docket_number_core,
)
from cl.corpus_importer.state.merger import (
    AttributeMerger,
    Merger,
    OneToOneMerger,
    overwrite,
)
from cl.people_db.models import Person
from cl.search.models import Docket, OriginatingCourtInformation

logger = logging.getLogger(__name__)

FL_APPELLATE_COURT_ID: str = "fladistctapp"


def add_scraper_source(scrape: int | None, db: int | None) -> int:
    if not db:
        db = 0
    if db in Docket.NON_SCRAPER_SOURCES():
        return db + Docket.SCRAPER
    return db


class FloridaPartyMerger(Merger[FloridaParty, Person, None]):
    model: ClassVar[type[Model]] = Person


def _date_last_filing(docket_data: FloridaCase, params: Any) -> date | None:
    filing_dates = sorted(
        e.date_filed for e in docket_data.entries if e.date_filed
    )
    return filing_dates[-1] if filing_dates else docket_data.date_filed


def _appeal_from_id(docket_data: FloridaCase, params: Any) -> str | None:
    # Multiple originating cases are ambiguous, so leave the field unset.
    if len(docket_data.originating_cases) != 1:
        return None
    return FLORIDA_COURT_ID_MAP.get(
        docket_data.originating_cases[0].court_id.value, None
    )


def _appeal_from_str(docket_data: FloridaCase, params: Any) -> str | None:
    # Multiple originating cases are ambiguous, so leave the field unset.
    if len(docket_data.originating_cases) != 1:
        return ""
    return docket_data.originating_cases[0].court_name


class FloridaOriginatingCourtInformationMerger(
    Merger[FloridaOriginatingCase, OriginatingCourtInformation, None]
):
    model: ClassVar[type[Model]] = OriginatingCourtInformation

    docket_number: str = AttributeMerger[FloridaOriginatingCase, str, None](
        lambda oc, params: oc.case_number, strategy=overwrite
    )
    docket_number_raw: str = AttributeMerger[
        FloridaOriginatingCase, str, None
    ](lambda oc, params: oc.case_number, strategy=overwrite)

    def query(self) -> QuerySet[OriginatingCourtInformation]:
        return OriginatingCourtInformation.objects.none()


def _originating_case(
    docket_data: FloridaCase, *args, **kwargs
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


class FloridaDocketMerger(Merger[FloridaCase, Docket, None]):
    model: ClassVar[type[Model]] = Docket

    atomic = True

    court_id: str = AttributeMerger[FloridaCase, str, None](
        lambda d, params: FLORIDA_COURT_ID_MAP[d.court_id],
        strategy=overwrite,
    )
    source: int = AttributeMerger(
        lambda _, params: Docket.SCRAPER,
        strategy=add_scraper_source,
    )
    date_filed: date | None = AttributeMerger[FloridaCase, date | None, None](
        lambda d, params: d.date_filed,
        strategy=overwrite,
    )
    date_last_filing: date | None = AttributeMerger(
        _date_last_filing,
        strategy=overwrite,
    )
    case_name: str = AttributeMerger[FloridaCase, str, None](
        lambda d, params: d.case_name, strategy=overwrite
    )
    case_name_full: str = AttributeMerger[FloridaCase, str, None](
        lambda d, params: d.case_name_full,
        strategy=overwrite,
    )
    case_name_short: str = AttributeMerger[FloridaCase, str, None](
        lambda d, params: d.case_name, strategy=overwrite
    )
    docket_number: str = AttributeMerger[FloridaCase, str, None](
        lambda d, params: d.docket_number,
        strategy=overwrite,
    )
    docket_number_raw: str = AttributeMerger[FloridaCase, str, None](
        lambda d, params: d.docket_number, strategy=overwrite
    )
    docket_number_core: str = AttributeMerger[FloridaCase, str, None](
        lambda d, params: make_docket_number_core(
            d.docket_number, court_id=FLORIDA_COURT_ID_MAP[d.court_id]
        ),
        strategy=overwrite,
    )
    appeal_from_id: str | None = AttributeMerger(
        _appeal_from_id, strategy=overwrite
    )
    appeal_from_str: str | None = AttributeMerger(
        _appeal_from_str, strategy=overwrite
    )
    # See https://github.com/freelawproject/courtlistener/issues/7361#issuecomment-4566459292
    pacer_case_id: str = AttributeMerger(
        lambda d, params: d.case_uuid, strategy=overwrite
    )
    originating_court_information: OriginatingCourtInformation = (
        OneToOneMerger[
            FloridaCase,
            FloridaOriginatingCase,
            OriginatingCourtInformation,
            None,
        ](
            FloridaOriginatingCourtInformationMerger,
            _originating_case,
        )
    )

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
