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


def prepare_citation(citation: str) -> Union[List[FullCaseCitation], list]:
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


def dict_all_combinations(d: dict, dates_filed: list) -> list:
    """Generate all possible combinations of a dict
    :param d: dict with filters
    :param dates_filed: list with date_filed string dates
    :return: list of possible combinations of dict keys and values
    """
    results = []
    if dates_filed:
        d_copy = d.copy()
        for date_filed in dates_filed:
            # Generate filters with all date_filed possibilities
            d_copy["date_filed"] = date_filed
            for i in range(1, len(d) + 1):
                results.extend(
                    list(map(dict, itertools.combinations(d.items(), i)))
                )
    else:
        # We don't have any date_filed, generate filters
        for i in range(1, len(d) + 1):
            results.extend(
                list(map(dict, itertools.combinations(d.items(), i)))
            )

    # We remove possible duplicated filters generated when we have multiple
    # date_filed dates
    return [dict(t) for t in {tuple(d.items()) for d in results}]


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
        if not citation[0].corrected_reporter():
            reporter_type = Citation.STATE
        else:
            cite_type_str = citation[0].all_editions[0].reporter.cite_type
            reporter_type = map_reporter_db_cite_type(cite_type_str)

        try:
            if not debug:
                Citation.objects.get_or_create(
                    volume=citation[0].groups["volume"],
                    reporter=citation[0].corrected_reporter(),
                    page=citation[0].groups["page"],
                    type=reporter_type,
                    cluster_id=cluster_id,
                )
            logger.info(
                f'Citation "{citation}" added to cluster id: {cluster_id}'
            )
        except IntegrityError:
            logger.warning(
                f"Reporter mismatch for cluster: {cluster_id} on cite: {citation}"
            )


def extract_valid_citations(citations: str) -> list:
    """Extract citations from string
    :param citations: string with multiple citations
    :return: list with valid FullCaseCitation citations
    """
    valid_citations = []

    pattern = r'"([^"]*)"'
    new_citations = re.findall(pattern, citations)
    if new_citations:
        for citation in new_citations:
            validated_citation = prepare_citation(citation)
            if validated_citation:
                valid_citations.extend(validated_citation)
            else:
                logger.warning(f'Invalid citation found: "{citation}"')

    return valid_citations


def find_case_with_citations(
    valid_citations: list,
    court: str | None = None,
    date_filed: str | None = None,
    date_decided: str | None = None,
    case_name: str | None = None,
) -> OpinionCluster | None:
    """Search for possible case using citation, court, date filed and case name
    :param valid_citations: list with valid citations from csv row
    :param court: Court name
    :param date_filed: The date the case was filed
    :param date_decided: The date the case was decided, in cl is also the date
    the case was filed
    :param case_name: The case name
    :return: OpinionCluster or None
    """
    for citation in valid_citations:
        # Lexis data contains many citations, we need to find at least one
        # case with the citation, so we can add the others

        citation_search_params = {
            "citations__volume": citation[0].groups.get("volume"),
            "citations__reporter": citation[0].corrected_reporter(),
            "citations__page": citation[0].groups.get("page"),
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

        filters = {"docket__court__id": court_id, "case_name": case_name}

        # Store all possible date_filed dates
        dates_filed = []

        if date_filed and not date_decided:
            # Only add date if we have one
            prep_date_filed = prepare_date(date_filed)
            if prep_date_filed:
                dates_filed.append(prep_date_filed.strftime("%Y-%m-%d"))

        if not date_filed and date_decided:
            # Lexis dataset contains can contain the date_filed in
            # date_decided column, I found out this after taking a sample
            # from dataset and comparing it with courtlistener data
            prep_date_filed = prepare_date(date_decided)
            if prep_date_filed:
                dates_filed.append(prep_date_filed.strftime("%Y-%m-%d"))

        if date_filed and date_decided:
            prep_date_filed = prepare_date(date_filed)
            prep_date_decided = prepare_date(date_decided)
            if prep_date_filed:
                dates_filed.append(prep_date_filed.strftime("%Y-%m-%d"))
            if prep_date_decided:
                dates_filed.append(prep_date_decided.strftime("%Y-%m-%d"))

        # Remove any None value
        filters = {
            key: value for key, value in filters.items() if value is not None
        }

        # Generate all possible combinations of filters
        generated_filters = dict_all_combinations(filters, dates_filed)

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

    return None


def process_lexis_data(data: DataFrame | TextFileReader, debug: bool) -> None:
    for index, row in data.iterrows():
        case_name = row.get("full_name")
        citations = row.get("lexis_ids_normalized")
        court = row.get("court")
        # date_decided is date_filed in courtlistener and date_filed is also
        # date_filed in courtlistener
        date_filed = row.get("date_filed")
        date_decided = row.get("date_decided")

        valid_citations = extract_valid_citations(citations)

        if len(valid_citations) > 1:
            search_result = find_case_with_citations(
                valid_citations, court, date_filed, date_decided
            )
            if search_result:
                add_citations(
                    valid_citations,
                    search_result.pk,
                    debug,
                )
        elif len(valid_citations) == 1:
            # We only got one correct citation, we can't add the other
            # citations because are invalid, or we only have one citation in
            # lexis dataset
            pass
        else:
            logger.info(
                f'No results for case: "{case_name}" with citations: "{citations}"'
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
            process_lexis_data(data, options["debug"])
