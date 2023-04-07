import itertools
import re
from datetime import date, datetime
from typing import List, Union

import numpy as np
import pandas as pd
from courts_db import find_court
from django.core.management import BaseCommand
from django.db import IntegrityError, transaction
from django.db.models.query import QuerySet
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize
from pandas import DataFrame
from pandas.io.parsers import TextFileReader

from cl.citations.utils import map_reporter_db_cite_type
from cl.corpus_importer.management.commands.harvard_opinions import (
    winnow_case_name,
)
from cl.lib.command_utils import logger
from cl.search.models import Citation, Court, Docket, Opinion, OpinionCluster

cnt = CaseNameTweaker()


def load_csv_file(csv_path: str) -> DataFrame | TextFileReader:
    """Load csv file from absolute path
    :param csv_path: csv path
    :return: loaded data
    """

    data = pd.read_csv(csv_path, delimiter=",")
    # Replace nan in dataframe
    data = data.replace(np.nan, "", regex=True)
    logger.info(
        f"(Westlaw) Found {len(data.index)} rows in csv file: {csv_path}"
    )
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
