import logging
from datetime import date
from typing import ClassVar

from asgiref.sync import async_to_sync
from django.db.models import Model
from juriscraper.state.florida import FloridaCase
from juriscraper.state.florida.cases import FloridaCourtID

from cl.corpus_importer.state.florida.utils import (
    FLORIDA_COURT_ID_MAP,
    make_docket_number_core,
)
from cl.corpus_importer.state.merger import (
    AttributeMerger,
    Merger,
    RelatedMerger,
    overwrite,
)
from cl.recap.mergers import (
    find_and_disaggregate_docket_object,
    find_docket_object,
)
from cl.search.models import Docket, OriginatingCourtInformation

logger = logging.getLogger(__name__)

FL_APPELLATE_COURT_ID: str = "fladistctapp"


def add_scraper_source(scrape: int | None, db: int | None) -> int:
    if not db:
        db = 0
    if db in Docket.NON_SCRAPER_SOURCES():
        return db + Docket.SCRAPER
    return db


def _date_last_filing(docket_data: FloridaCase) -> date | None:
    filing_dates = sorted(
        e.date_filed for e in docket_data.entries if e.date_filed
    )
    return filing_dates[-1] if filing_dates else docket_data.date_filed


def _originating_case_number(docket_data: FloridaCase) -> str | None:
    if not docket_data.originating_cases:
        return None
    return docket_data.originating_cases[0].case_number


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
    Merger[FloridaCase, OriginatingCourtInformation]
):
    model: ClassVar[type[Model]] = OriginatingCourtInformation

    docket_number: str = AttributeMerger(
        _originating_case_number, strategy=overwrite
    )
    docket_number_raw: str = AttributeMerger(
        _originating_case_number, strategy=overwrite
    )

    @staticmethod
    def validate(docket_data: FloridaCase) -> bool:
        if len(docket_data.originating_cases) > 1:
            logger.warning(
                "Florida docket %s in court %s has multiple originating cases. Using the first one.",
                docket_data.docket_number,
                docket_data.court_id,
            )
        return True

    @classmethod
    def get_existing(
        cls, oci: FloridaCase, _
    ) -> OriginatingCourtInformation | None:
        return None


class FloridaDocketMerger(Merger[FloridaCase, Docket]):
    model: ClassVar[type[Model]] = Docket

    atomic = True

    court_id: str = AttributeMerger[FloridaCase, str](
        lambda d: FLORIDA_COURT_ID_MAP[d.court_id],
        strategy=overwrite,
    )
    source: int = AttributeMerger(
        lambda _: Docket.SCRAPER,
        strategy=add_scraper_source,
    )
    date_filed: date | None = AttributeMerger[FloridaCase, date | None](
        lambda d: d.date_filed,
        strategy=overwrite,
    )
    date_last_filing: date | None = AttributeMerger(
        _date_last_filing,
        strategy=overwrite,
    )
    case_name: str = AttributeMerger[FloridaCase, str](
        lambda d: d.case_name, strategy=overwrite
    )
    case_name_full: str = AttributeMerger[FloridaCase, str](
        lambda d: d.case_name_full,
        strategy=overwrite,
    )
    case_name_short: str = AttributeMerger[FloridaCase, str](
        lambda d: d.case_name, strategy=overwrite
    )
    docket_number: str = AttributeMerger[FloridaCase, str](
        lambda d: d.docket_number,
        strategy=overwrite,
    )
    docket_number_raw: str = AttributeMerger[FloridaCase, str](
        lambda d: d.docket_number, strategy=overwrite
    )
    docket_number_core: str = AttributeMerger[FloridaCase, str](
        lambda d: make_docket_number_core(
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
        lambda d: d.case_uuid, strategy=overwrite
    )
    originating_court_information: OriginatingCourtInformation = RelatedMerger[
        FloridaCase, OriginatingCourtInformation
    ](
        FloridaOriginatingCourtInformationMerger,
        lambda d: d,
        gate=lambda docket_data: (
            docket_data.court_id == FloridaCourtID.SUPREME_COURT.value
            and bool(docket_data.originating_cases)
        ),
    )

    @classmethod
    def get_existing(cls, docket: FloridaCase, _) -> Docket | None:
        supreme_court_id = FLORIDA_COURT_ID_MAP[
            FloridaCourtID.SUPREME_COURT.value
        ]
        court_id = FLORIDA_COURT_ID_MAP[docket.court_id]

        if court_id == supreme_court_id:
            return async_to_sync(find_docket_object)(
                court_id=court_id,
                pacer_case_id=str(docket.case_uuid),
                docket_number=docket.docket_number,
                federal_defendant_number=None,
                federal_dn_judge_initials_assigned=None,
                federal_dn_judge_initials_referred=None,
                docket_source=Docket.SCRAPER,
                allow_create=False,
            )
        found, changed = async_to_sync(find_and_disaggregate_docket_object)(
            court_id=court_id,
            aggregate_court_id=FL_APPELLATE_COURT_ID,
            docket_number=docket.docket_number,
            docket_source=Docket.SCRAPER,
            allow_create=False,
        )
        if changed:
            logger.info(
                "Disaggregated Florida docket: %s", docket.docket_number
            )
        return found

    @staticmethod
    def validate(docket_data: FloridaCase) -> bool:
        if docket_data.court_id not in FLORIDA_COURT_ID_MAP:
            logger.error("Unknown court id: %s", docket_data.court_id)
            return False
        return True
