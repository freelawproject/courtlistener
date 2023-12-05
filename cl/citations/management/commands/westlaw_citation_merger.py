import itertools
import os.path
import re
from glob import glob
from typing import List, Union

from django.core.management import BaseCommand
from django.db.models.query import QuerySet
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from juriscraper.lib.string_utils import CaseNameTweaker
from pandas import DataFrame
from pandas.io.parsers import TextFileReader

from cl.citations.management.commands.citation_merger_utils import (
    add_citations,
    add_stub_case,
    case_names_overlap,
    get_court_filter,
    load_citations_file,
    prepare_date,
)
from cl.lib.command_utils import logger
from cl.lib.utils import human_sort
from cl.search.models import OpinionCluster

cnt = CaseNameTweaker()


def dict_all_combinations(d: dict):
    """Generate all possible combinations of a dict

    :param d: dict
    :return: list of possible combinations of dict keys and values
    """
    results = []
    for i in range(1, len(d) + 1):
        results.extend(list(map(dict, itertools.combinations(d.items(), i))))
    return results


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


def extract_valid_citations(citations) -> list:
    """Extract citations from list of strings

    :param citations: list with string citations
    :return: list with valid FullCaseCitation citations
    """
    valid_citations = []
    for citation in citations:
        validated_citation = prepare_citation(citation)
        if validated_citation:
            valid_citations.extend(validated_citation)
        else:
            logger.warning(f'(Westlaw) Invalid citation found: "{citation}"')
    return valid_citations


def find_cases_with_citations(
    valid_citations: list,
    court: str | None = None,
    date_filed: str | None = None,
    case_name: str | None = None,
    docket_number: str | None = None,
) -> "QuerySet[OpinionCluster]":
    """Search for possible case using citation, court, date filed and case name

    :param valid_citations: list with valid citations from csv row
    :param court: Court name
    :param date_filed: The date the case was filed
    :param case_name: The case name
    :param docket_number: The docket number
    :return: OpinionCluster QuerySet
    """
    results_ids = []
    for citation in valid_citations:
        citation_search_params = {
            "citations__volume": citation.groups.get("volume"),
            "citations__reporter": citation.corrected_reporter(),
            "citations__page": citation.groups.get("page"),
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
                    # Case names are similar, we have a match, store the pk
                    results_ids.append(cluster_results.first().pk)

        if not results_ids:
            # If we don't get a single match with citation

            # Basic filter
            filters = {
                "case_name": case_name,
                "docket__docket_number": docket_number,
            }

            prep_date_filed = prepare_date(date_filed)
            if prep_date_filed:
                filters["date_filed"] = prep_date_filed.strftime("%Y-%m-%d")

            # Add court to filters if we have court in csv
            filters.update(get_court_filter(court))

            # Remove any None value
            filters = {
                key: value
                for key, value in filters.items()
                if value is not None
            }

            # Generate all possible combinations of filters
            generated_filters = dict_all_combinations(filters)

            # We start with complex filters and go to most basic filter which
            # can return multiple results
            generated_filters = sorted(
                generated_filters, key=lambda d: len(d.keys()), reverse=True
            )

            # Apply all possible combination of filters to try to get the case
            for queryset_filter in generated_filters:
                # cluster_results is already filtered by citation
                if cluster_results:
                    # When we have results with citation
                    results = cluster_results.filter(**queryset_filter)
                else:
                    # When we don't have any results with citation, use the
                    # other filters to try to find the case
                    results = OpinionCluster.objects.filter(**queryset_filter)
                filter_results_count = results.count()
                if filter_results_count == 1:
                    if case_name:
                        names_are_similar = case_names_overlap(
                            results.first(), case_name
                        )
                        if names_are_similar:
                            # We found a case with similar name to westlaw
                            # data, store pk
                            results_ids.append(results.first().pk)
                else:
                    # Try next filter
                    continue

            if not results_ids:
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
                                # We found a case with similar name to
                                # westlaw data
                                results_ids.append(cluster.pk)

    # Remove possible duplicated ids
    results_ids = list(set(results_ids))

    if len(results_ids) > 1:
        # Possible duplicate cases, we still add citations to cases that
        # match the search criteria
        logger.warning(
            f"(Westlaw) Possible duplicated cases with ids: {','.join(map(str, results_ids))}"
        )

    # Return a queryset of all the possible cases matched by filter and case
    # name overlap, remove duplicated ids to filter
    return OpinionCluster.objects.filter(pk__in=results_ids)


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

        citations = []
        if citation:
            citations.append(citation)
        if parallel_citation:
            citations.append(parallel_citation)

        valid_citations = extract_valid_citations(citations)

        if valid_citations:
            search_results = find_cases_with_citations(
                valid_citations, court, date_filed, case_name, docket_number
            )

            if search_results:
                for search_result in search_results:
                    add_citations(valid_citations, search_result.pk, debug)
            else:
                # We couldn't get any search result to add the citations
                if case_name and valid_citations and court and date_filed:
                    add_stub_case(
                        valid_citations, court, case_name, date_filed, debug
                    )
                else:
                    # +1 to indicate row considering the header
                    logger.info(f"(Westlaw) Invalid data in row: {index + 1}")

        else:
            # Add stub case if possible
            if case_name and valid_citations and court and date_filed:
                add_stub_case(
                    valid_citations, court, case_name, date_filed, debug
                )
            else:
                # +1 to indicate row considering the header
                logger.info(f"(Westlaw) Invalid data in row: {index + 1}")


class Command(BaseCommand):
    help = "Merge citations from westlaw dataset"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="If debug is true,then don't save new citations.",
        )
        parser.add_argument(
            "--csv",
            required=True,
            help="Absolute path to the CSV containing the citations to add.",
        )
        parser.add_argument(
            "--csv-dir",
            type=str,
            help="The base path where to find the CSV files to process. It can be a "
            "mounted directory.",
            default="/opt/courtlistener/cl/assets/media/westlaw",
        )

    def handle(self, *args, **options):
        files = []
        if options["csv_dir"]:
            files.extend(glob(os.path.join(options["csv_dir"], "*.csv")))
            files = human_sort(files, key=None)
            print(f"Files found: {len(files)}")

        if options["csv"]:
            files.append(options["csv"])

        for file in files:
            data = load_citations_file(file)
            if not data.empty:
                process_westlaw_data(data, options["debug"])
