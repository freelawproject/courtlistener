from datetime import date, datetime

import numpy as np
import pandas as pd
from courts_db import find_court
from django.db import IntegrityError, transaction
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize
from pandas import DataFrame
from pandas.io.parsers import TextFileReader

from cl.citations.utils import map_reporter_db_cite_type
from cl.corpus_importer.utils import winnow_case_name
from cl.lib.command_utils import logger
from cl.search.models import Citation, Court, Docket, Opinion, OpinionCluster

cnt = CaseNameTweaker()


def load_citations_file(csv_path: str) -> DataFrame | TextFileReader:
    """Load csv file from absolute path

    :param csv_path: csv path
    :return: loaded data
    """

    data = pd.read_csv(csv_path, delimiter=",")
    # Replace nan in dataframe
    data = data.replace(np.nan, "", regex=True)
    logger.info(f"Found {len(data.index)} rows in csv file: {csv_path}")
    return data


def case_names_overlap(case: OpinionCluster, case_name: str) -> bool:
    """Case names not overlap

    Check if the case names have quality overlapping case name words.
    Excludes 'bad words' and other common words
    :param case: The case opinion cluster
    :param case_name: The case name from csv
    :return: Do the case names share quality overlapping words
    """

    # We combine as much data as possible for the case name to increase our
    # chances of getting a match
    cl_case_name = (
        f"{case.case_name} {case.case_name_short} {case.case_name_full}"
    )

    overlap = winnow_case_name(cl_case_name) & winnow_case_name(case_name)

    if overlap:
        return True
    return False


def prepare_date(date_str: str | None = None) -> date | None:
    """Convert dates like 'February 28, 2011' or '2011-02-28' to date object

    :param date_str: date string
    :return: date object or None
    """
    if date_str:
        valid_formats = ["%B %d, %Y", "%Y-%m-%d"]
        for date_format in valid_formats:
            try:
                date_obj = datetime.strptime(date_str, date_format)
                return date_obj.date()
            except ValueError:
                continue
        logger.warning(f"(Westlaw) Invalid date string: {date_str}")
    return None


def add_citations(
    citations: list, cluster_id: int, debug: bool = False
) -> None:
    """Add citation to OpinionCluster

    :param citations: list with valid citations
    :param cluster_id: Cluster id of found case
    :param debug: set false to save changes
    :return: None
    """

    for citation in citations:
        # Get correct reporter type before trying to add the citation
        if not citation.corrected_reporter():
            reporter_type = Citation.STATE
        else:
            cite_type_str = citation.all_editions[0].reporter.cite_type
            reporter_type = map_reporter_db_cite_type(cite_type_str)

        try:
            if not debug:
                obj, created = Citation.objects.get_or_create(
                    volume=citation.groups["volume"],
                    reporter=citation.corrected_reporter(),
                    page=citation.groups["page"],
                    type=reporter_type,
                    cluster_id=cluster_id,
                )
            else:
                # Force to show log message when debug is true, if false log
                # message will only show if new citation is created
                created = True

            if created:
                logger.info(
                    f'(Westlaw) Citation "{citation.corrected_citation()}"'
                    f" added to cluster id: {cluster_id}"
                )

        except IntegrityError:
            logger.warning(
                f"(Westlaw) Reporter mismatch for cluster: {cluster_id} on "
                f"cite: {citation.corrected_citation()}"
            )


def get_court_filter(court: str | None = None) -> dict:
    """Create dict with court filter

    :param court: court name or none
    :return: dict
    """
    if court:
        # Remove dot at end, court-db fails to find court with
        # dot at end, e.g. "Supreme Court of Pennsylvania." fails,
        # but "Supreme Court of Pennsylvania" doesn't
        court = court.strip(".")

        # Try without bankruptcy flag
        found_court = find_court(court, bankruptcy=False)

        if not found_court:
            # Try with bankruptcy flag
            found_court = find_court(court, bankruptcy=True)

        if len(found_court) >= 1:
            court_id = found_court[0]
            return {"docket__court__id": court_id}

    return {}


def add_stub_case(
    valid_citations: list,
    court_str: str,
    case_name: str,
    date_filed: str | None = None,
    debug: bool = False,
) -> None:
    """Add stub case

    :param valid_citations: List of valid citations to add
    :param court_str: Court name
    :param case_name: Case name
    :param date_filed: Date filed optional
    :param debug: if true don't save changes
    """

    # Remove dot at end
    court_name = court_str.strip(".")

    # Try without bankruptcy flag
    found_court = find_court(court_name, bankruptcy=False)

    if not found_court:
        # Try with bankruptcy flag
        found_court = find_court(court_name, bankruptcy=True)

    if len(found_court) >= 1:
        court = Court.objects.get(pk=found_court[0])
    else:
        logger.info(f"(Westlaw) Couldn't find court: {court_name}")
        return

    # Prepare date
    prep_date_filed = prepare_date(date_filed)

    if court and prep_date_filed:
        if not debug:
            with transaction.atomic():
                # Prepare case name
                case_name = harmonize(case_name)
                case_name_short = cnt.make_case_name_short(case_name)

                docket = Docket.objects.create(
                    source=0,
                    court=court,
                    case_name=case_name,
                    case_name_short=case_name_short,
                    case_name_full=case_name,
                    date_filed=prep_date_filed,
                )

                cluster = OpinionCluster.objects.create(
                    case_name=case_name,
                    case_name_short=case_name_short,
                    case_name_full=case_name,
                    docket=docket,
                    date_filed=prep_date_filed,
                    precedential_status="Unknown",
                )

                # By default, add to solr to make it searchable
                Opinion.objects.create(
                    cluster=cluster,
                    type="Lead Opinion",
                    plain_text="We don't have enough information about this "
                    "case/citation.",
                )

                add_citations(valid_citations, cluster.pk, debug)

                logger.info(
                    f"(Westlaw) Stub case added correctly, "
                    f"cluster id: {cluster.pk}"
                )
        else:
            logger.info(f"(Westlaw) Stub case added correctly")
