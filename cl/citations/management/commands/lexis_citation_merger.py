import os
import re
from glob import glob
from typing import Optional

from django.core.management import BaseCommand
from pandas import DataFrame
from pandas.io.parsers import TextFileReader

from cl.citations.management.commands.citation_merger_utils import (
    add_citations,
    add_stub_case,
    find_cases_with_citations,
    load_citations_file,
    prepare_citation,
)
from cl.lib.command_utils import logger
from cl.lib.utils import human_sort


def extract_valid_citations(citations: Optional[str]) -> list:
    """Extract citations from string

    :param citations: string with multiple citations
    :return: list with valid FullCaseCitation citations
    """
    valid_citations = []

    if citations:
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


def process_lexis_data(
    data: DataFrame | TextFileReader,
    debug: bool,
    limit: int,
    start_row: Optional[int] = None,
    end_row: Optional[int] = None,
) -> None:
    """Process citations from csv file

    :param data: rows from csv file
    :param debug: if true don't save changes
    :param limit: limit number of rows to process
    :param start_row: start row
    :param end_row: end row
    :return: None
    """
    start = False if start_row else True
    end = False
    total_processed = 0

    for index, row in data.iterrows():
        if not start and start_row == index:
            start = True
        if not start:
            continue
        if end_row is not None and (end_row == index):
            end = True

        case_name = row.get("full_name")
        citations = row.get("lexis_ids_normalized")
        court = row.get("court")
        # date_decided is date_filed in courtlistener and date_filed is also
        # date_filed in courtlistener
        date_filed = row.get("date_filed")
        date_decided = row.get("date_decided")

        valid_citations = extract_valid_citations(citations)

        if len(valid_citations) > 0:
            search_results = find_cases_with_citations(
                valid_citations, court, date_filed, date_decided, case_name
            )
            if search_results:
                for search_result in search_results:
                    add_citations(
                        valid_citations,
                        search_result.pk,
                        debug,
                    )
            else:
                # We couldn't get any search result to add the citations
                if (
                    case_name
                    and valid_citations
                    and court
                    and (date_filed or date_decided)
                ):
                    add_stub_case(
                        valid_citations=valid_citations,
                        court_str=court,
                        case_name=case_name,
                        date_filed=date_filed,
                        date_decided=date_decided,
                        debug=debug,
                    )
                else:
                    logger.info(f"Insufficient data in row: {index}")

        else:
            # Add stub case if possible
            if (
                case_name
                and valid_citations
                and court
                and (date_filed or date_decided)
            ):
                add_stub_case(
                    valid_citations=valid_citations,
                    court_str=court,
                    case_name=case_name,
                    date_filed=date_filed,
                    date_decided=date_decided,
                    debug=debug,
                )
            else:
                logger.info(f"Insufficient data in row: {index}")

        total_processed += 1
        if limit and total_processed >= limit:
            logger.info(f"Finished {limit} rows")
            return

        if end:
            return


class Command(BaseCommand):
    help = "Merge citations from Westlaw dataset"

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
            help="Absolute path to a single CSV file containing the citations to add.",
        )
        parser.add_argument(
            "--csv-dir",
            type=str,
            help="The base path where to find the CSV files to process. It can be a "
            "mounted directory.",
            default="/opt/courtlistener/cl/assets/media/lexis",
        )
        parser.add_argument(
            "--start-row",
            type=int,
            help="Start row (inclusive). It only applies when you pass a single csv "
            "file.",
        )
        parser.add_argument(
            "--end-row",
            type=int,
            help="End row (inclusive). It only applies when you pass single csv file.",
        )
        parser.add_argument(
            "--limit",
            default=10000,
            type=int,
            help="Limit number of rows to process.",
            required=False,
        )

    def handle(self, *args, **options):
        files = []

        if options["csv_dir"]:
            files.extend(glob(os.path.join(options["csv_dir"], "*.csv")))
            files = human_sort(files, key=None)
            print(f"CSV files found in {options['csv_dir']}: {len(files)}")

        for file in files:
            data = load_citations_file(file)
            if not data.empty:
                process_lexis_data(data, options["debug"], options["limit"])

        if options["csv"]:
            if (
                options["start_row"] is not None
                and options["end_row"] is not None
            ):
                if options["start_row"] > options["end_row"]:
                    print("--start-row can't be greater than --end-row")
                    return

            # Handle single csv file
            data = load_citations_file(options["csv"])
            if not data.empty:
                process_lexis_data(
                    data,
                    options["debug"],
                    options["limit"],
                    options["start_row"],
                    options["end_row"],
                )
