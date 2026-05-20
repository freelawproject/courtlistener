import logging
from typing import Any

from asgiref.sync import async_to_sync
from django.db import transaction
from juriscraper.state.florida import FloridaCase
from juriscraper.state.florida.courts import FloridaCourtID

from cl.corpus_importer.state.utils import MergeResult
from cl.lib.model_helpers import make_docket_number_core
from cl.recap.mergers import (
    find_and_disaggregate_docket_object,
    find_docket_object,
)
from cl.search.models import Docket, OriginatingCourtInformation

logger = logging.getLogger(__name__)

FL_APPELLATE_COURT_ID: str = "fladistctapp"
FL_APPELLATE_COURTS: set[str] = {
    FloridaCourtID.FIRST_COA.value,
    FloridaCourtID.SECOND_COA.value,
    FloridaCourtID.THIRD_COA.value,
    FloridaCourtID.FOURTH_COA.value,
    FloridaCourtID.FIFTH_COA.value,
    FloridaCourtID.SIXTH_COA.value,
}

FLORIDA_COURT_ID_MAP: dict[str, str] = {
    FloridaCourtID.SUPREME_COURT.value: "fla",
    FloridaCourtID.FIRST_COA.value: "fladistctapp1",
    FloridaCourtID.SECOND_COA.value: "fladistctapp2",
    FloridaCourtID.THIRD_COA.value: "fladistctapp3",
    FloridaCourtID.FOURTH_COA.value: "fladistctapp4",
    FloridaCourtID.FIFTH_COA.value: "fladistctapp5",
    FloridaCourtID.SIXTH_COA.value: "fladistctapp6",
}


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
    oci: OriginatingCourtInformation = docket.originating_court_information
    created = False
    if not oci:
        created = True
        oci = OriginatingCourtInformation()
    if len(docket_data.originating_cases) > 1:
        logger.warning(
            "Florida docket %s in court %s has multiple originating cases. Using the first one.",
            docket_data.docket_number,
            docket_data.court_id,
        )
    originating_case = docket_data.originating_cases[0]
    oci.docket_number = originating_case.case_number
    oci.docket_number_raw = originating_case.case_number
    oci.save()
    if created:
        docket.save()
        return MergeResult.created("OriginatingCourtInformation", oci.pk)
    return MergeResult.updated("OriginatingCourtInformation", oci.pk)


def merge_docket(docket_data: FloridaCase) -> MergeResult[Any | None]:
    """Merger for Florida docket data and originating court information.

    :param docket_data: The scraped Florida docket information.
    :return: The result of the attempted merge operation.
    """
    with transaction.atomic():
        if docket_data.court_id not in FLORIDA_COURT_ID_MAP:
            logger.error("Unknown court id: %s", docket_data.court_id)
            return MergeResult.failed("Docket")
        court_id = FLORIDA_COURT_ID_MAP[docket_data.court_id]
        match docket_data.court_id:
            case FloridaCourtID.SUPREME_COURT.value:
                docket = async_to_sync(find_docket_object)(
                    court_id=court_id,
                    pacer_case_id=None,
                    docket_number=docket_data.docket_number,
                    federal_defendant_number=None,
                    federal_dn_judge_initials_assigned=None,
                    federal_dn_judge_initials_referred=None,
                    docket_source=Docket.SCRAPER,
                    allow_create=True,
                )
                changed = False
            case _ if docket_data.court_id in FL_APPELLATE_COURTS:
                docket, changed = async_to_sync(
                    find_and_disaggregate_docket_object
                )(
                    court_id=court_id,
                    aggregate_court_id=FL_APPELLATE_COURT_ID,
                    docket_number=docket_data.docket_number,
                    docket_source=Docket.SCRAPER,
                )
                if changed:
                    logger.info(
                        "Disaggregated Florida docket: %s",
                        docket_data.docket_number,
                    )
            case _:
                logger.error("Unknown court id: %s", docket_data.court_id)
                return MergeResult.failed("Docket")
        if docket is None:
            logger.error(
                "Failed to find or create docket object for Florida docket %s",
                docket_data.docket_number,
            )
            return MergeResult.failed("Docket")
        if docket.source in Docket.NON_SCRAPER_SOURCES():
            docket.add_scraper_source()

        # Florida does not give us the judge who presided over the case

        docket.date_filed = docket_data.date_filed
        filing_dates = sorted(
            e.date_filed for e in docket_data.entries if e.date_filed
        )
        docket.date_last_filing = (
            filing_dates[-1] if filing_dates else docket_data.date_filed
        )
        docket.case_name = docket_data.case_name
        docket.case_name_full = docket_data.case_name_full
        docket.case_name_short = docket_data.case_name
        docket.docket_number = docket_data.docket_number
        # Docket technically does this on save, but setting it here lets us skip all
        # the branches there.
        docket.docket_number_core = make_docket_number_core(
            docket_data.docket_number
        )
        docket.docket_number_raw = docket_data.docket_number
        docket_created = not changed and docket.pk is None
        docket.save()
        docket_result = (
            MergeResult.created("Docket", docket.pk)
            if docket_created
            else MergeResult.updated("Docket", docket.pk)
        )
        oci_result = merge_oci(docket, docket_data)
    # Merge parties, docket entries, etc.
    return docket_result | oci_result
