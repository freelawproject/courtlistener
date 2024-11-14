import logging
import re
import time
from datetime import date, datetime

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from eyecite.tokenizers import HyperscanTokenizer

from cl.corpus_importer.utils import add_citations_to_cluster
from cl.search.models import Citation, OpinionCluster

logger = logging.getLogger(__name__)
HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")

# Compile regex pattern once for efficiency
WORD_PATTERN = re.compile(r"\b\w+\b|\b\w+\.\b")

NUMBER_PATTERN = re.compile(r"^[+-]?[0-9]+$")

FALSE_POSITIVES = {
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

DATE_FORMATS = ("%B %d, %Y", "%d-%b-%y", "%m/%d/%Y", "%m/%d/%y", "%b. %d, %Y")


def tokenize_case_name(case_name: str) -> list[str]:
    """Tokenizes case name and removes single-character words except for letters with periods.

    :param case_name: case name to tokenize
    :return: list of words
    """
    return [
        word.lower()
        for word in WORD_PATTERN.findall(case_name)
        if len(word) > 1
    ]


def check_case_names_match(csv_case_name: str, cl_case_name: str) -> bool:
    """Compare two case name and decide whether they are the same or not

    :param csv_case_name: case name from csv
    :param cl_case_name: case name from cluster
    :return: True if they match else False
    """
    # Tokenize each string, capturing both words and abbreviations with periods and
    # convert all words to lowercase for case-insensitive matching
    csv_case_name_tokens = set(tokenize_case_name(csv_case_name))
    cluster_case_name_tokens = set(tokenize_case_name(cl_case_name))

    # Check if there is an overlap between case names and remove false positive words
    overlap = csv_case_name_tokens & cluster_case_name_tokens - FALSE_POSITIVES

    if not overlap:
        # if no hits no match on name - move along
        return False

    # Check for "v." in title
    if "v." not in csv_case_name.lower():
        # in the matter of Smith
        # if no V. - likely an "in re" case and only match on at least 1 name
        return True

    # otherwise check if a match occurs on both sides of the V
    v_index = csv_case_name.lower().index("v.")
    hit_indices = [csv_case_name.lower().find(hit) for hit in overlap]

    return min(hit_indices) < v_index < max(hit_indices)


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
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    logger.warning(f"Invalid date format: {date_str}")
    return None


def validate_citations(
    cite_1: str, cite_2: str, index: int
) -> list[FullCaseCitation]:
    """Validate citations with eyecite

    :param cite_1: first string citation
    :param cite_2: second string citation
    :param index: row index
    :return: list of valid FullCaseCitation objects
    """
    cite_one = get_citations(cite_1, tokenizer=HYPERSCAN_TOKENIZER)
    cite_two = get_citations(cite_2, tokenizer=HYPERSCAN_TOKENIZER)

    citations = cite_one + cite_two
    cites = [cite for cite in citations if isinstance(cite, FullCaseCitation)]

    if len(cites) < 2:
        # Skipping row without two citations
        return []

    if not NUMBER_PATTERN.match(
        cites[0].groups.get("volume")
    ) or not NUMBER_PATTERN.match(cites[1].groups.get("volume")):
        # Volume number is not an integer e.g. 2001-1 Trade Cases P 73,218
        logger.warning(f"Row index: {index} - Citation parsing failed.")
        return []

    return cites


def find_matches(
    valid_citations: list[FullCaseCitation],
    csv_docket_num: str,
    csv_date_filed: date,
    csv_case_name: str,
) -> list[OpinionCluster]:
    """Find matches for row data

    :param valid_citations: list of FullCaseCitation objects
    :param csv_docket_num: cleaned docket number from row
    :param csv_date_filed: formatted filed date from row
    :param csv_case_name: case name from csv row
    :return: list of tuples of matched OpinionCluster and used citation
    """
    matches: list[OpinionCluster] = []

    # Try to match row using both citations
    for citation in valid_citations:

        possible_matches = Citation.objects.filter(
            **make_citation(citation),
            cluster__docket__docket_number__contains=csv_docket_num,
            cluster__date_filed=csv_date_filed,
        )
        if not possible_matches:
            # Match not found with citation, docket number and date filed
            continue

        for match in possible_matches:
            case_name = (
                match.cluster.case_name_full
                if match.cluster.case_name_full
                else match.cluster.case_name
            )
            if check_case_names_match(csv_case_name, case_name):
                if not any(
                    cluster.id == match.cluster.id for cluster in matches
                ):
                    # Avoid duplicates
                    matches.append(match.cluster)

    return matches


def update_matched_case_name(
    matched_cluster: OpinionCluster, csv_case_name: str
) -> bool:
    """Update case name of matched cluster and related docket

    :param matched_cluster: OpinionCluster object
    :param csv_case_name: case name from csv row
    :return: tuple with boolean values if cluster and related docket case name updated
    """

    if not matched_cluster.case_name or len(csv_case_name) < len(
        matched_cluster.case_name
    ):
        # Save case name in cluster when we don't have it or when the case name in csv is smaller than the current case name
        matched_cluster.case_name = csv_case_name
        matched_cluster.save()
        logger.info(f"Case name updated for cluster id: {matched_cluster.id}")
        return True

    logger.info(
        f"Cluster id: {matched_cluster.id} already has the smallest case name."
    )

    return False


def make_citation(citation: FullCaseCitation) -> dict:
    """Get citation as a dict to use it as a filter

    It only keeps the values that we have in db, in some cases we have extra data
    e.g. 2012-635 (La.App. 3 Cir. 12/5/12) also includes date_filed when it is parsed

    :param citation:
    :return: dict with volume, reporter and page
    """
    return {
        "volume": citation.groups["volume"],
        "reporter": citation.corrected_reporter(),
        "page": citation.groups["page"],
    }


def process_csv(
    filepath: str, delay: float, dry_run: bool, chunk_size: int
) -> None:
    """Process rows from csv file

    :param filepath: path to csv file
    :param delay: delay between saves in seconds
    :param dry_run: flag to simulate update process
    :param chunk_size: number of rows to read at a time
    """

    total_clusters_updated = 0
    logger.info(f"Processing {filepath}")
    for chunk in pd.read_csv(filepath, chunksize=chunk_size):
        for row in chunk.dropna().itertuples():
            (
                index,
                csv_case_name,
                court,
                date_str,
                cite1,
                cite2,
                docket,
                volume,
            ) = row

            valid_citations = validate_citations(cite1, cite2, index)

            if not valid_citations:
                logger.info(f"Row index: {index} - No valid citations found.")
                continue

            clean_docket_num = docket.strip('="').strip('"')

            date_filed = parse_date(date_str)
            if not date_filed:
                logger.info(f"Row index: {index} - No valid date found.")
                continue

            # Query for possible matches using data from row
            matches = find_matches(
                valid_citations, clean_docket_num, date_filed, csv_case_name
            )

            if not matches or len(matches) > 1:
                if len(matches) > 1:
                    # These could be bad matches or duplicates
                    logger.warning(
                        f"Row index: {index} - Failed: too many matches: {len(matches)} - Matches: {[cluster.id for cluster in matches]}"
                    )
                else:
                    logger.info(f"Row index: {index} - No matches found.")

                # Go to next row
                continue

            # We matched the row with a cluster
            if not dry_run:
                # Update case names
                cluster_updated = update_matched_case_name(
                    matches[0], csv_case_name
                )

                if cluster_updated:
                    total_clusters_updated = +1

                # Add any of the citations if possible
                add_citations_to_cluster(
                    [cite.corrected_citation() for cite in valid_citations],
                    matches[0].id,
                )

                # Wait between each processed row to avoid sending to many indexing tasks
                time.sleep(delay)
            else:
                # Dry run, only log a message
                logger.info(
                    f"Row index: {index} - Match found: {matches[0]} - Csv case name: {csv_case_name}"
                )

    if not dry_run:
        logger.info(f"Clusters updated: {total_clusters_updated}")


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
            help="How long to wait to update each opinion cluster (in seconds, allows floating numbers).",
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
