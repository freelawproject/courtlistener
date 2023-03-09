import re
from datetime import datetime
from typing import List, Union

from courts_db import find_court
from django.core.management import BaseCommand
from django.db import IntegrityError
from eyecite import get_citations
from eyecite.models import FullCaseCitation

from cl.citations.utils import map_reporter_db_cite_type
from cl.search.models import Citation, OpinionCluster

# TODO change prints with logger


def find_indexes(list_to_check, item_to_find):
    """Get index of all occurrences of an element in a list
    :param list_to_check: list
    :param item_to_find: element to find
    return: list with indexes or empty list
    """
    indexes = []
    for idx, value in enumerate(list_to_check):
        if value == item_to_find:
            indexes.append(idx)
    return indexes


def add_citation(citation: str, cluster_id: int) -> None:
    """Add citation to OpinionCluster
    :param citation: str citation
    :param cluster_id: Cluster id of found case
    :return: None
    """

    # Process the citation string before proceeding
    citations = prepare_citation(citation)

    if not citations:
        print(
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
        Citation.objects.get_or_create(
            volume=citations[0].groups["volume"],
            reporter=citations[0].corrected_reporter(),
            page=citations[0].groups["page"],
            type=reporter_type,
            cluster_id=cluster_id,
        )
        print(f'Citation "{citation}" added to cluster id: {cluster_id}')
    except IntegrityError:
        print(
            f"Reporter mismatch for cluster: {cluster_id} on cite: {citation}"
        )


def prepare_date(date_str: str) -> Union[None, datetime]:
    """Convert dates like 'February 28, 2011' or '2011-02-28' to date object
    :param date_str: date string
    :return: date object or None
    """
    valid_formats = ["%B %d, %Y", "%Y-%m-%d"]
    for date_format in valid_formats:
        try:
            date_obj = datetime.strptime(date_str, date_format)
            return date_obj
        except ValueError:
            print(f"Invalid date string: {date_str}")
            continue
    return None


def prepare_citation(citation: str) -> Union[List[FullCaseCitation], List]:
    """Convert str citation to valid citation objects
    :param citation: citation str
    :return: list of valid cites
    """
    clean_cite = re.sub(r"\s+", " ", citation)
    cites = get_citations(clean_cite)
    cites = [cite for cite in cites if isinstance(cite, FullCaseCitation)]
    return cites


class Command(BaseCommand):
    help = "Merge citations from westlaw"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def handle(self, *args, **options):
        # Test data

        # 8109821 8109820 8109819 8109818 8109817 8109816 8109815 8109814 8109813 8109812 8109811
        csv_reader = [
            {
                "full_name": "In re Atwood",
                "court": "Supreme Court, Appellate Division, First Department, New York.",
                "date_filed": "January 22, 1904",
                "citation": "90 A.D. 607",
                "parallel_citation": "86 N.Y.S. 1128",
                "docket_number": "",
            }
        ]
        for row in csv_reader:
            case_name = row.get("full_name")
            citation = row.get("citation")
            parallel_citation = row.get("parallel_citation")
            court = row.get("court")
            # TODO, how to use docket number? sometimes contains extra data
            #  like No. or is empty in CL
            docket_number = row.get("docket_number")
            date_filed = row.get("date_filed")

            additional_search_params = {}

            if court:
                # Add court to search params if exists
                if court.endswith("."):
                    # Remove dot at end, court-db fails to find court with
                    # dot at end, e.g. "Supreme Court of Pennsylvania." fails,
                    # but "Supreme Court of Pennsylvania" doesn't
                    court = court[:-1]

                # TODO try to get court with and without bankruptcy flag?
                found_court = find_court(court, bankruptcy=False)

                if len(found_court) >= 1:
                    court_id = found_court[0]
                    additional_search_params["docket__court__id"] = court_id

            # TODO date_filed may break thinks, we can have duplicated cases but with different date_filed because many reasons, like incorrect data or because approximated date is incorrect check in re freeman case or Webb v. State Compensation Com'r
            # if date_filed:
            #     # Add date filed to search params if exist
            #     prep_date_filed = prepare_date(date_filed)
            #     if prep_date_filed:
            #         # TODO we could use a date_filed range instead of exact
            #         #  date to give it a wider range to search
            #         additional_search_params[
            #             "date_filed"
            #         ] = prep_date_filed.strftime("%Y-%m-%d")
            #         # We have an exact date
            #         additional_search_params[
            #             "date_filed_is_approximate"] = False

            # Check that both citations are valid
            prepared_citation = prepare_citation(citation)
            prepared_parallel_citation = prepare_citation(parallel_citation)

            if prepared_citation and prepared_parallel_citation:
                # Citation and parallel citation are valid, prepare filter
                # params for citation and parallel citation
                citation_search_params = {
                    "citations__volume": prepared_citation[0].groups.get(
                        "volume"
                    ),
                    "citations__reporter": prepared_citation[
                        0
                    ].corrected_reporter(),
                    "citations__page": prepared_citation[0].groups.get("page"),
                }
                parallel_citation_search_params = {
                    "citations__volume": prepared_parallel_citation[
                        0
                    ].groups.get("volume"),
                    "citations__reporter": prepared_parallel_citation[
                        0
                    ].corrected_reporter(),
                    "citations__page": prepared_parallel_citation[
                        0
                    ].groups.get("page"),
                }

                # Add additional params to dict filters
                citation_search_params.update(additional_search_params)
                parallel_citation_search_params.update(
                    additional_search_params
                )

                # We filter by citation and parallel citation params
                citation_cluster_results = OpinionCluster.objects.filter(
                    **citation_search_params
                )

                print("citation_search_params", citation_search_params)
                print("citation_cluster_results", citation_cluster_results)

                parallel_citation_cluster_results = (
                    OpinionCluster.objects.filter(
                        **parallel_citation_search_params
                    )
                )

                print(
                    "parallel_citation_search_params",
                    parallel_citation_search_params,
                )
                print(
                    "parallel_citation_cluster_results",
                    parallel_citation_cluster_results,
                )

                # Store the count to use it in the following code
                results_count = citation_cluster_results.count()
                print("results_count", results_count)
                parallel_results_count = (
                    parallel_citation_cluster_results.count()
                )
                print("parallel_results_count", parallel_results_count)

                # Store names and the ids of the clusters obtained from
                # citation and parallel citation
                results_names = citation_cluster_results.values_list(
                    "case_name", flat=True
                )
                print("results_names", results_names)
                results_ids = citation_cluster_results.values_list(
                    "pk", flat=True
                )
                print("results_ids", results_ids)
                parallel_results_names = (
                    parallel_citation_cluster_results.values_list(
                        "case_name", flat=True
                    )
                )
                print("parallel_results_names", parallel_results_names)
                parallel_results_ids = (
                    parallel_citation_cluster_results.values_list(
                        "pk", flat=True
                    )
                )
                print("parallel_results_ids", parallel_results_ids)

                if results_count == 1 and parallel_results_count == 0:
                    print("A")
                    # Add parallel citation to cluster
                    add_citation(
                        parallel_citation, citation_cluster_results.first().pk
                    )
                elif results_count == 0 and parallel_results_count == 1:
                    print("B")
                    # Add citation to cluster with parallel citation.
                    # Note: there may be the case that we can have duplicate
                    # cases, but one has date_filed_is_approximate and the
                    # other not, we will add the citation to the case with
                    # date_filed_is_approximate is false, e.g. cluster id:
                    # 7414160 and 5350679
                    add_citation(
                        citation, parallel_citation_cluster_results.first().pk
                    )
                elif results_count == 1 and parallel_results_count == 1:
                    print("C")
                    # The case could be duplicated, compare the ids of each
                    # result
                    if (
                        citation_cluster_results.first().pk
                        != parallel_citation_cluster_results.first().pk
                    ):
                        print(
                            f'Possible duplicated cases for citations: "{citation}" with clusters: {citation_cluster_results.first().pk} and {parallel_citation_cluster_results.first().pk}'
                        )
                    else:
                        print(
                            f'Cluster {citation_cluster_results.first().pk} already have both citations "{citation}" and "{parallel_citation}"'
                        )
                elif results_count > 1 and parallel_results_count == 0:
                    print("D")
                    # We got more than one result using the citation, we can
                    # try to find the case name using csv data and try to
                    # match it with the correct case

                    # Check if case name from csv is exactly the same in
                    # case_names list and get index
                    # TODO we could implement a more complex process,
                    #  this is just a workaround to use as much of
                    #  westlaw data as possible
                    indexes_found = find_indexes(
                        list(results_names), case_name
                    )
                    if len(indexes_found) == 1:
                        # Add parallel citation to cluster obtained from list
                        case_id = results_ids[indexes_found[0]]
                        add_citation(parallel_citation, case_id)
                    elif len(indexes_found) > 1:
                        print(
                            f'Multiple results for case: "{case_name}" and citation: "{citation}"'
                        )

                elif results_count == 0 and parallel_results_count > 1:
                    print("E")
                    # We got more than one result using parallel citation,
                    # we can try to find the case name using csv data and
                    # try to match it with the correct case

                    # Check if the csv case name is exactly the same in
                    # the case_names list and get the index
                    indexes_found = find_indexes(
                        list(parallel_results_names), case_name
                    )
                    if len(indexes_found) == 1:
                        case_id = parallel_results_ids[indexes_found[0]]
                        # Add citation to parallel citation cluster
                        add_citation(citation, case_id)
                    elif len(indexes_found) > 1:
                        # Many case names have the same names, it's hard
                        # to figure out where citation belongs to
                        print(
                            f'Multiple results for case: "{case_name}" and '
                            f'parallel citation: "{parallel_citation}"'
                        )

                elif results_count == 0 and parallel_results_count == 0:
                    print("F")
                    # No match for both citations
                    print(
                        f'No results for case: "{case_name}" with '
                        f'citation: "{citation}" and parallel citation: '
                        f'"{parallel_citation}"'
                    )
                elif results_count == 1 and parallel_results_count > 1:
                    if results_ids[0] in list(parallel_results_ids):
                        # Case is in two list, therefore it has both citations
                        print(
                            f'Cluster {results_ids[0]} already have both citations "{citation}" and "{parallel_citation}"'
                        )
                elif results_count > 1 and parallel_results_count == 1:
                    # Case is in two list, therefore it has both citations
                    if parallel_results_ids[0] in list(results_ids):
                        print(
                            f'Cluster {parallel_results_ids[0]} already have both citations "{citation}" and "{parallel_citation}"'
                        )
                else:
                    pass

            elif prepared_citation and not prepared_parallel_citation:
                print(
                    f'Case: "{case_name}", invalid citation found: "{parallel_citation}"'
                )

            elif not prepared_citation and prepared_parallel_citation:
                print(
                    f'Case: "{case_name}", invalid citation found: "{citation}"'
                )

            else:
                print(
                    f'Case: "{case_name}", invalid citations found: "{citation}" and "{parallel_citation}"'
                )
