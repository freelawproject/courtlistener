import logging
import re
import time
from datetime import date, datetime

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from eyecite.tokenizers import HyperscanTokenizer

from cl.search.models import Citation

logger = logging.getLogger(__name__)
HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


def find_matches(csv_case_name: str, cl_case_name: str):
    """Compare two case name and decide whether they are the same or not

    :param csv_case_name: case name from csv
    :param cl_case_name: case name from cluster
    :return: True if they match else False
    """
    # Tokenize each string, capturing both words and abbreviations with periods
    csv_case_name_words = re.findall(r"\b\w+\b|\b\w+\.\b", csv_case_name)
    cluster_case_name_words = re.findall(r"\b\w+\b|\b\w+\.\b", cl_case_name)

    # Helper function to check if word1 is an abbreviation of word2 or vice versa
    # Convert all words to lowercase for case-insensitive matching
    csv_case_name_words_lower = [
        word.lower() for word in csv_case_name_words if len(word) > 1
    ]
    cluster_case_name_words_lower = [
        word.lower() for word in cluster_case_name_words if len(word) > 1
    ]

    overlap = set(csv_case_name_words_lower) & set(
        cluster_case_name_words_lower
    )

    # print("overlap", overlap)

    false_positive_set = {
        "and",
        "personal",
        "restraint",
        "matter",
        "county",
        "city",
        "of",
        "the",
        "estate",
        "in",
        "inc",
        "re",
        "st",
        "ex",
        "rel",
        "v",
        "vs",
        "for",
        "a",
    }

    # these are valid overlaps, excluding anything in false_positive_set
    hits = [item for item in overlap if item not in false_positive_set]

    if not hits:
        # if no hits no match on name - move along
        return False

    # Check for "v." in title
    if "v." not in csv_case_name.lower():
        # in the matter of Smith
        # if no V. - likely a in re. case and only match on atleast 1 name
        return True

    # otherwise check if a match occurs on both sides of the V
    v_index = csv_case_name.lower().index("v.")
    hit_index = [csv_case_name.lower().index(hit) for hit in hits]

    if min(hit_index) < v_index < max(hit_index):
        return True

    # logger.info(f"Row index: {row_index} - No match found with: {match.cluster}")
    return False


def parse_date(date_str: str) -> date | None:
    """Attempts to parse the filed date into a datetime object.

    # January 10, 1999
    # 24-Jul-97
    # 21-Jan-94
    # 1/17/1961
    # 12/1/1960
    # 26-Sep-00
    # Feb. 28, 2001

    :param date_str: date string
    :return: date object or none
    """
    for fmt in ("%B %d, %Y", "%d-%b-%y", "%m/%d/%Y", "%m/%d/%y", "%b. %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    logger.warning(f"Invalid date format: {date_str}")
    return None


def make_citations(cite1, cite2) -> list[FullCaseCitation]:
    """Validate citations with eyecite

    :param cite1: first string citation
    :param cite2: second string citation
    :return: list of valid FullCaseCitation objects
    """
    cite_one = get_citations(cite1, tokenizer=HYPERSCAN_TOKENIZER)
    cite_two = get_citations(cite2, tokenizer=HYPERSCAN_TOKENIZER)

    citations = cite_one + cite_two
    cites = [cite for cite in citations if isinstance(cite, FullCaseCitation)]
    return cites


def process_csv(
    filepath: str, delay: float, dry_run: bool, chunk_size: int
) -> None:
    """Process rows from csv file

    :param filepath: path to csv file
    :param delay: delay between saves in seconds
    :param dry_run: flag to simulate update process
    :param chunk_size: number of rows to read at a time
    """

    logger.info(f"Processing {filepath}")
    for chunk in pd.read_csv(filepath, chunksize=chunk_size):
        for row in chunk.dropna().itertuples():
            index, title, court, date_str, cite1, cite2, docket, volume = row
            valid_citations = make_citations(cite1, cite2)

            if len(valid_citations) < 2:
                # Skipping row without two citations
                continue

            # Check if already have both citations from row
            try:
                c = Citation.objects.filter(
                    **valid_citations[0].groups
                ).values_list("cluster", flat=True)
                d = Citation.objects.filter(
                    **valid_citations[1].groups
                ).values_list("cluster", flat=True)
            except ValueError:
                logger.warning(
                    f"Row index: {index} - Citation parsing failed."
                )
                continue

            overlapping_clusters = c.intersection(d)
            if overlapping_clusters:
                logger.info(
                    f"Row index: {index} - Both citations exist for this cluster: {list(overlapping_clusters)}"
                )
                continue

            if not valid_citations:
                logger.info(f"Row index: {index} - No valid citations found.")
                continue

            clean_docket_num = docket.strip('="').strip('"')

            date_filed = parse_date(date_str)
            if not date_filed:
                logger.info(f"Row index: {index} - No valid date found.")
                continue

            # Keep non westlaw citations, use them to try to find a match
            remaining_citations = [
                cite
                for cite in valid_citations
                if cite.corrected_reporter() != "WL"
            ]

            for citation in remaining_citations:

                possible_matches = Citation.objects.filter(
                    **citation.groups,
                    cluster__docket__docket_number__contains=clean_docket_num,
                    cluster__date_filed=date_filed,
                )
                if not possible_matches:
                    # Match not found with citation, docket number and date filed
                    continue

                single_match = None
                for match in possible_matches:
                    case_name = (
                        match.cluster.case_name_full
                        if match.cluster.case_name_full
                        else match.cluster.case_name
                    )
                    match_on_caption = find_matches(title, case_name)
                    if match_on_caption:
                        if not single_match:
                            single_match = match.cluster
                            continue
                        else:
                            logger.warning(
                                f"Row index: {index} - Failed: too many matches"
                            )
                            single_match = None
                            # Exit possible_matches loop
                            break

                if single_match:
                    m = (
                        single_match.case_name_full
                        if single_match.case_name_full
                        else single_match.case_name
                    )
                    citation_to_add = [
                        cite
                        for cite in valid_citations
                        if cite.corrected_citation()
                        != citation.corrected_citation()
                    ]
                    logger.info(
                        f"Row index: {index} - Match found: {single_match} - New casename: {title} - Used citation: {citation.corrected_citation()} - To add: {citation_to_add[0].corrected_citation() if citation_to_add else 'Invalid'}"
                    )
                    # We already have matched the case using one of the citations

                    if not dry_run:
                        # Logic to save new case name and add citation

                        # Wait between each processed cluster to avoid issues with redis memory
                        time.sleep(delay)
                    else:
                        pass

                    # Exit remaining_citations loop
                    break


class Command(BaseCommand):
    help = "Match and compare case details from a CSV file with existing records in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--filepath",
            type=str,
            required=True,
            help="Path to the CSV file to process.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.1,
            help="How long to wait to update each opinion and docket (in seconds, allows floating numbers).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the update process without making changes",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=100000,
            help="The number of rows to read at a time",
        )

    def handle(self, *args, **options):
        filepath = options["filepath"]
        delay = options["delay"]
        dry_run = options["dry_run"]
        chunk_size = options["chunk_size"]

        if not filepath:
            raise CommandError(
                "Filepath is required. Use --filepath to specify the CSV file location."
            )

        process_csv(filepath, delay, dry_run, chunk_size)
