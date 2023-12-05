import os
import re
from glob import glob

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


def process_lexis_data(data: DataFrame | TextFileReader, debug: bool) -> None:
    """Process citations from csv file

    :param data: rows from csv file
    :param debug: if true don't save changes
    :return: None
    """
    for index, row in data.iterrows():
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
                        valid_citations,
                        court,
                        case_name,
                        date_filed,
                        date_decided,
                        debug,
                    )
                else:
                    # +1 to indicate row considering the header
                    logger.info(f"Invalid data in row: {index + 1}")

        else:
            if (
                case_name
                and valid_citations
                and court
                and (date_filed or date_decided)
            ):
                # Add stub case
                add_stub_case(
                    valid_citations,
                    court,
                    case_name,
                    date_filed,
                    date_decided,
                    debug,
                )
            else:
                # +1 to indicate row considering the header
                logger.info(f"Invalid data in row: {index + 1}")


class Command(BaseCommand):
    help = "Merge citations from Westlaw dataset"

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
        parser.add_argument(
            "--csv-dir",
            type=str,
            help="The base path where to find the CSV files to process. It can be a "
            "mounted directory.",
            default="/opt/courtlistener/cl/assets/media/lexis",
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
                process_lexis_data(data, options["debug"])
