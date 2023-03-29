import itertools
import re
from datetime import date, datetime
from typing import List, Union

import pandas as pd
from courts_db import find_court
from django.core.management import BaseCommand
from django.db import IntegrityError
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from pandas import DataFrame
from pandas.io.parsers import TextFileReader

from cl.citations.utils import map_reporter_db_cite_type
from cl.corpus_importer.management.commands.harvard_opinions import (
    winnow_case_name,
)
from cl.lib.command_utils import logger
from cl.search.models import Citation, OpinionCluster


def load_csv_file(csv_path: str) -> DataFrame | TextFileReader:
    """Load csv file from absolute path
    :param csv_path: csv path
    :return: loaded data
    """

    data = pd.read_csv(csv_path, delimiter=",")
    logger.info(f"Found {len(data.index)} rows in csv file.")
    return data


def dict_all_combinations(d: dict):
    """Generate all possible combinations of a dict
    :param d: dict
    :return: list of possible combinations of dict keys and values
    """
    results = []
    for i in range(1, len(d) + 1):
        results.extend(list(map(dict, itertools.combinations(d.items(), i))))
    return results


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


def add_citation(citation: str, cluster_id: int, debug: bool = False) -> None:
    """Add citation to OpinionCluster
    :param citation: str citation
    :param cluster_id: Cluster id of found case
    :param debug: set false to save changes
    :return: None
    """

    # Process the citation string before proceeding
    citations = prepare_citation(citation)

    if not citations:
        logger.warning(
            f"The citation: {citation} you are trying to add to the cluster "
            f"id: {cluster_id} is invalid."
        )
        return

    # Get correct reporter type before trying to add the citation
    if not citations[0].corrected_reporter():
        reporter_type = Citation.STATE
    else:
        cite_type_str = citations[0].all_editions[0].reporter.cite_type
        reporter_type = map_reporter_db_cite_type(cite_type_str)

    try:
        if not debug:
            Citation.objects.get_or_create(
                volume=citations[0].groups["volume"],
                reporter=citations[0].corrected_reporter(),
                page=citations[0].groups["page"],
                type=reporter_type,
                cluster_id=cluster_id,
            )
        logger.info(f'Citation "{citation}" added to cluster id: {cluster_id}')
    except IntegrityError:
        logger.warning(
            f"Reporter mismatch for cluster: {cluster_id} on cite: {citation}"
        )


def prepare_date(date_str: str) -> date | None:
    """Convert dates like 'February 28, 2011' or '2011-02-28' to date object
    :param date_str: date string
    :return: date object or None
    """
    valid_formats = ["%B %d, %Y", "%Y-%m-%d"]
    for date_format in valid_formats:
        try:
            date_obj = datetime.strptime(date_str, date_format)
            return date_obj.date()
        except ValueError:
            logger.warning(f"Invalid date string: {date_str}")
            continue
    return None


def prepare_citation(citation: str) -> Union[List[FullCaseCitation], List]:
    """Convert str citation to valid citation objects
    :param citation: citation str
    :return: list of valid cites
    """
    clean_cite = re.sub(r"\s+", " ", citation)
    citations = get_citations(clean_cite)
    citations = [
        cite for cite in citations if isinstance(cite, FullCaseCitation)
    ]
    return citations


def find_case_with_citation(
    citation_str: str,
    court: str | None = None,
    date_filed: str | None = None,
    case_name: str | None = None,
    docket_number: str | None = None,
) -> OpinionCluster | None:
    """Search for possible case using citation, court, date filed and case name
    :param citation_str: Citation str
    :param court: Court name
    :param date_filed: The date the case was filed
    :param case_name: The case name
    :param docket_number: The docket number
    :return: OpinionCluster or None
    """
    prepared_citation = prepare_citation(citation_str)

    if prepared_citation:
        citation_search_params = {
            "citations__volume": prepared_citation[0].groups.get("volume"),
            "citations__reporter": prepared_citation[0].corrected_reporter(),
            "citations__page": prepared_citation[0].groups.get("page"),
        }

        # Filter by citation
        cluster_results = OpinionCluster.objects.filter(
            **citation_search_params
        )

        # Store the count to use it in the following code
        results_count = cluster_results.count()
        if results_count == 1:
            if case_name:
                names_are_similar = case_names_overlap(
                    cluster_results.first(), case_name
                )
                if names_are_similar:
                    # Case names are similar, we have a match
                    return cluster_results.first()

        court_id = None
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

        filters = {
            "docket__court__id": court_id,
            "case_name": case_name,
            "docket__docket_number": docket_number,
        }

        if date_filed:
            # Only add date if we have one
            prep_date_filed = prepare_date(date_filed)
            if prep_date_filed:
                filters["date_filed"] = prep_date_filed.strftime("%Y-%m-%d")

        # Remove any None value
        filters = {
            key: value for key, value in filters.items() if value is not None
        }

        # Generate all possible combinations of filters
        generated_filters = dict_all_combinations(filters)

        obj = None

        # Apply all possible combination of filters to try to get the case
        for queryset_filter in generated_filters:
            # cluster_results is already filtered by citation
            results = cluster_results.filter(**queryset_filter)
            filter_results_count = results.count()
            if filter_results_count == 1:
                obj = results.first()
                break
            else:
                # Try next filter
                continue

        if not obj:
            # We couldn't find a match using filters, if only filtering by
            # citation gave us a large queryset, lets try to compare each
            # result with case name to try to find a match
            if results_count > 1:
                for cluster in cluster_results:
                    if case_name:
                        names_are_similar = case_names_overlap(
                            cluster, case_name
                        )
                        if names_are_similar:
                            # We found a case with similar name to westlaw data
                            return cluster

        # Perform extra check to be sure that we have the correct case
        if obj:
            if case_name:
                names_are_similar = case_names_overlap(obj, case_name)
                if names_are_similar:
                    # We got a match
                    return obj

        return None

    else:
        logger.warning(f'Invalid citation found: "{citation_str}"')

        # No result at all
        return None


def process_westlaw_data(
    data: DataFrame | TextFileReader, debug: bool
) -> None:
    """
    Process citations from csv file
    :param data: rows from csv file
    :param debug: if true don't save changes
    :return: None
    """
    for index, row in data.iterrows():
        case_name = row.get("Title")
        citation = row.get("Citation")
        parallel_citation = row.get("Parallel Cite")
        court = row.get("Court Line")
        docket_number = row.get("Docket Num")
        date_filed = row.get("Filed Date")

        # Find a match for each citation, westlaw data only have two citations
        # in the csv files
        citation_cluster_result = find_case_with_citation(
            citation, court, date_filed, case_name, docket_number
        )
        parallel_citation_cluster_result = find_case_with_citation(
            parallel_citation, court, date_filed, case_name, docket_number
        )

        if citation_cluster_result and not parallel_citation_cluster_result:
            # Add citation to cluster
            add_citation(
                parallel_citation,
                citation_cluster_result.pk,
                debug,
            )
        elif not citation_cluster_result and parallel_citation_cluster_result:
            # Add citation to cluster
            add_citation(
                citation,
                parallel_citation_cluster_result.pk,
                debug,
            )
        elif citation_cluster_result and parallel_citation_cluster_result:
            # The case could be duplicated, compare the id of each result
            if (
                citation_cluster_result.pk
                != parallel_citation_cluster_result.pk
            ):
                logger.warning(
                    f'Possible duplicated cases for citations: "{citation}" '
                    f"with cluster: {citation_cluster_result.pk} and "
                    f"{parallel_citation_cluster_result.pk} "
                )
            else:
                logger.info(
                    f"Cluster {citation_cluster_result.pk} already have both "
                    f'citations "{citation}" and "{parallel_citation}" '
                )
        else:
            # No results
            logger.info(
                f'No results for case: "{case_name}" with '
                f'citation: "{citation}" or parallel citation: '
                f'"{parallel_citation}"'
            )


class Command(BaseCommand):
    help = "Merge citations from westlaw dataset"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="If debug is true,then  don't save new citations.",
        )
        parser.add_argument(
            "--csv",
            required=True,
            help="Absolute path to the CSV containing the citations to add.",
        )

    def handle(self, *args, **options):
        data = load_csv_file(options["csv"])
        if not data.empty:
            process_westlaw_data(data, options["debug"])
