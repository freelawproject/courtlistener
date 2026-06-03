import logging
from datetime import date
from typing import Annotated, override

from asgiref.sync import async_to_sync
from juriscraper.state.florida import FloridaCase
from juriscraper.state.florida.courts import FloridaCourtID

from cl.corpus_importer.state.merger import (
    AttributeMerger,
    InputField,
    InputMap,
    Merger,
    MergeStrategy,
    OverwriteExisting,
    RelatedMerger,
    Relationship,
)
from cl.corpus_importer.state.utils import MergeResult
from cl.lib.model_helpers import make_docket_number_core
from cl.recap.mergers import (
    find_and_disaggregate_docket_object,
    find_docket_object,
)
from cl.search.models import Docket, OriginatingCourtInformation

logger = logging.getLogger(__name__)

FL_APPELLATE_COURT_ID: str = "fladistctapp"

FLORIDA_COURT_ID_MAP: dict[str, str] = {
    FloridaCourtID.SUPREME_COURT.value: "fla",
    FloridaCourtID.FIRST_COA.value: "fladistctapp1",
    FloridaCourtID.SECOND_COA.value: "fladistctapp2",
    FloridaCourtID.THIRD_COA.value: "fladistctapp3",
    FloridaCourtID.FOURTH_COA.value: "fladistctapp4",
    FloridaCourtID.FIFTH_COA.value: "fladistctapp5",
    FloridaCourtID.SIXTH_COA.value: "fladistctapp6",
}


class AddScraperSource(MergeStrategy[int]):
    """Compound the scraper source onto a non-scraper docket source, matching
    `Docket.add_scraper_source`."""

    @override
    def merge_values(self, scrape: int, db: int) -> int:
        if db in Docket.NON_SCRAPER_SOURCES():
            return db + Docket.SCRAPER
        return db


def _scraper_source(docket_data: FloridaCase) -> int:
    return Docket.SCRAPER


def _court_id(docket_data: FloridaCase) -> str:
    return FLORIDA_COURT_ID_MAP[docket_data.court_id]


def _date_last_filing(docket_data: FloridaCase) -> date | None:
    filing_dates = sorted(
        e.date_filed for e in docket_data.entries if e.date_filed
    )
    return filing_dates[-1] if filing_dates else docket_data.date_filed


def _docket_number_core(docket_data: FloridaCase) -> str:
    return make_docket_number_core(docket_data.docket_number)


def _originating_case_number(docket_data: FloridaCase) -> str:
    return docket_data.originating_cases[0].case_number


def _supreme_court_originating_case(
    docket_data: FloridaCase,
) -> FloridaCase | None:
    if docket_data.court_id != FloridaCourtID.SUPREME_COURT.value:
        return None
    return docket_data


class FloridaOriginatingCourtInformationMerger(
    Merger[FloridaCase, OriginatingCourtInformation]
):
    docket_number: Annotated[
        str,
        AttributeMerger(
            InputMap(_originating_case_number), strategy=OverwriteExisting()
        ),
    ]
    docket_number_raw: Annotated[
        str,
        AttributeMerger(
            InputMap(_originating_case_number), strategy=OverwriteExisting()
        ),
    ]

    @staticmethod
    def validate(docket_data: FloridaCase) -> bool:
        if len(docket_data.originating_cases) > 1:
            logger.warning(
                "Florida docket %s in court %s has multiple originating cases. Using the first one.",
                docket_data.docket_number,
                docket_data.court_id,
            )
        return True

    @staticmethod
    def existing(
        oci: OriginatingCourtInformation,
    ) -> OriginatingCourtInformation | None:
        return None


def merge_oci(docket: Docket, docket_data: FloridaCase) -> MergeResult:
    """Merge the originating court information for a Florida Supreme COurt docket.

    :param docket: The docket to merge the OCI for.
    :param docket_data: The scraped Florida docket information.
    :return: The result of the attempted merge operation."""
    if docket_data.court_id != FloridaCourtID.SUPREME_COURT.value:
        logger.info(
            "Skipping unnecessary OCI merge for Florida docket %s in court %s",
            docket_data.docket_number,
            docket_data.court_id,
        )
        return MergeResult.unnecessary()
    return FloridaOriginatingCourtInformationMerger.merge(
        docket_data, existing=docket.originating_court_information
    )


class FloridaDocketMerger(Merger[FloridaCase, Docket]):
    atomic = True

    court_id: Annotated[
        str,
        AttributeMerger(InputMap(_court_id), strategy=OverwriteExisting()),
    ]
    source: Annotated[
        int,
        AttributeMerger(
            InputMap(_scraper_source), strategy=AddScraperSource()
        ),
    ]
    date_filed: Annotated[
        date | None,
        AttributeMerger(
            InputField("date_filed"), strategy=OverwriteExisting()
        ),
    ]
    date_last_filing: Annotated[
        date | None,
        AttributeMerger(
            InputMap(_date_last_filing), strategy=OverwriteExisting()
        ),
    ]
    case_name: Annotated[
        str,
        AttributeMerger(InputField("case_name"), strategy=OverwriteExisting()),
    ]
    case_name_full: Annotated[
        str,
        AttributeMerger(
            InputField("case_name_full"), strategy=OverwriteExisting()
        ),
    ]
    case_name_short: Annotated[
        str,
        AttributeMerger(InputField("case_name"), strategy=OverwriteExisting()),
    ]
    docket_number: Annotated[
        str,
        AttributeMerger(
            InputField("docket_number"), strategy=OverwriteExisting()
        ),
    ]
    docket_number_core: Annotated[
        str,
        AttributeMerger(
            InputMap(_docket_number_core), strategy=OverwriteExisting()
        ),
    ]
    docket_number_raw: Annotated[
        str,
        AttributeMerger(
            InputField("docket_number"), strategy=OverwriteExisting()
        ),
    ]
    originating_court_information: Annotated[
        OriginatingCourtInformation,
        RelatedMerger(
            FloridaOriginatingCourtInformationMerger,
            InputMap(_supreme_court_originating_case),
            relationship=Relationship.OneToOne,
        ),
    ]

    @staticmethod
    def existing(docket: Docket) -> Docket | None:
        supreme_court_id = FLORIDA_COURT_ID_MAP[
            FloridaCourtID.SUPREME_COURT.value
        ]
        if docket.court_id == supreme_court_id:
            found = async_to_sync(find_docket_object)(
                court_id=docket.court_id,
                pacer_case_id=None,
                docket_number=docket.docket_number,
                federal_defendant_number=None,
                federal_dn_judge_initials_assigned=None,
                federal_dn_judge_initials_referred=None,
                docket_source=Docket.SCRAPER,
                allow_create=True,
            )
        else:
            found, changed = async_to_sync(
                find_and_disaggregate_docket_object
            )(
                court_id=docket.court_id,
                aggregate_court_id=FL_APPELLATE_COURT_ID,
                docket_number=docket.docket_number,
                docket_source=Docket.SCRAPER,
            )
            if changed:
                logger.info(
                    "Disaggregated Florida docket: %s", docket.docket_number
                )
        if found is not None and found.pk is None:
            return None
        return found


def merge_docket(docket_data: FloridaCase) -> MergeResult:
    """Merger for Florida docket data and originating court information.

    :param docket_data: The scraped Florida docket information.
    :return: The result of the attempted merge operation.
    """
    if docket_data.court_id not in FLORIDA_COURT_ID_MAP:
        logger.error("Unknown court id: %s", docket_data.court_id)
        return MergeResult.failed("Docket")
    return FloridaDocketMerger.merge(docket_data)
