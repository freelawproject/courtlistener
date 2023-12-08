import os.path
from glob import glob
from typing import Optional

from django.core.management import BaseCommand
from juriscraper.lib.string_utils import CaseNameTweaker
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

cnt = CaseNameTweaker()


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
            logger.warning(f'Invalid citation found: "{citation}"')
    return valid_citations


def process_westlaw_data(
    data: DataFrame | TextFileReader,
    debug: bool,
    limit: int,
    start_row: Optional[int] = None,
    end_row: Optional[int] = None,
) -> None:
    """
    Process citations from csv file

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
                valid_citations=valid_citations,
                court=court,
                date_filed=date_filed,
                case_name=case_name,
                docket_number=docket_number,
            )

            if search_results:
                for search_result in search_results:
                    add_citations(valid_citations, search_result.pk, debug)
            else:
                # We couldn't get any search result to add the citations
                if case_name and valid_citations and court and date_filed:
                    add_stub_case(
                        valid_citations=valid_citations,
                        court_str=court,
                        case_name=case_name,
                        date_filed=date_filed,
                        debug=debug,
                    )
                else:
                    # +1 to indicate row considering the header
                    logger.info(f"Invalid data in row: {index}")

        else:
            # Add stub case if possible
            if case_name and valid_citations and court and date_filed:
                add_stub_case(
                    valid_citations=valid_citations,
                    court_str=court,
                    case_name=case_name,
                    date_filed=date_filed,
                    debug=debug,
                )
            else:
                # +1 to indicate row considering the header
                logger.info(f"Invalid data in row: {index}")

        total_processed += 1
        if limit and total_processed >= limit:
            logger.info(f"Finished {limit} rows")
            return

        if end:
            return


class Command(BaseCommand):
    help = "Merge citations from westlaw dataset"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="If debug is true, then don't save new citations.",
        )
        parser.add_argument(
            "--csv",
            required=True,
            help="Absolute path to a single CSV file containing the citations to add.",
        )
        parser.add_argument(
            "--csv-dir",
            type=str,
            help="The base path where to find the CSV files to process. It can be a "
            "mounted directory.",
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
            print(f"Files found in --csv-dir: {len(files)}")

        for file in files:
            data = load_citations_file(file)
            if not data.empty:
                process_westlaw_data(data, options["debug"], options["limit"])

        if options["csv"]:
            if (
                options["start_row"] is not None
                and options["end_row"] is not None
            ):
                if options["start_row"] > options["end_row"]:
                    print("--start-row can't be greater than --end-row")
                    return

            data = load_citations_file(options["csv"])
            if not data.empty:
                process_westlaw_data(
                    data,
                    options["debug"],
                    options["limit"],
                    options["start_row"],
                    options["end_row"],
                )
