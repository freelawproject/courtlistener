import os.path
from glob import glob

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
                    logger.info(f"Invalid data in row: {index + 1}")

        else:
            # Add stub case if possible
            if case_name and valid_citations and court and date_filed:
                add_stub_case(
                    valid_citations, court, case_name, date_filed, debug
                )
            else:
                # +1 to indicate row considering the header
                logger.info(f"Invalid data in row: {index + 1}")


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
