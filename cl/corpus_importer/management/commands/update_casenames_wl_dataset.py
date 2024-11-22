import logging
import re
import time
from datetime import date, datetime

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, QuerySet
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from eyecite.tokenizers import HyperscanTokenizer

from cl.citations.utils import map_reporter_db_cite_type
from cl.corpus_importer.utils import add_citations_to_cluster
from cl.search.models import Citation, OpinionCluster

logger = logging.getLogger(__name__)
HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")

# Compile regex pattern once for efficiency
WORD_PATTERN = re.compile(r"\b\w+\b|\b\w+\.\b")

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
    "vs",
    "for",
}

DATE_FORMATS = (
    "%B %d, %Y",
    "%d-%b-%y",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%b. %d, %Y",
    "%Y-%m-%d",
)


def tokenize_case_name(case_name: str) -> set[str]:
    """Tokenizes case name and removes single-character words except for letters with periods.

    Also removes false positive words

    :param case_name: case name to tokenize
    :return: list of words
    """
    return (
        set(
            [
                word.lower()
                for word in WORD_PATTERN.findall(case_name)
                if len(word) > 1
            ]
        )
        - FALSE_POSITIVES
    )


def check_case_names_match(csv_case_name: str, cl_case_name: str) -> bool:
    """Compare two case name and decide whether they are the same or not

    :param csv_case_name: case name from csv
    :param cl_case_name: case name from cluster
    :return: True if they match else False
    """
    # Tokenize each string, capturing both words and abbreviations with periods and
    # convert all words to lowercase for case-insensitive matching and check if there
    # is an overlap between case names
    overlap = tokenize_case_name(csv_case_name) & tokenize_case_name(
        cl_case_name
    )

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

    January 10, 1999
    24-Jul-97
    21-Jan-94
    1/17/1961
    12/1/1960
    26-Sep-00
    Feb. 28, 2001
    2007-01-24

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


def parse_citations(citation_strings: list[str]) -> list[dict]:
    """Validate citations with Eyecite.

    :param citation_strings: List of citation strings to validate.
    :return: List of validated citation dictionaries with volume, reporter, and page.
    """
    validated_citations = []

    for cite_str in citation_strings:
        # Get citations from the string
        found_cites = get_citations(cite_str, tokenizer=HYPERSCAN_TOKENIZER)
        if not found_cites:
            continue

        citation = found_cites[0]

        # Ensure we have valid citations to process
        if isinstance(citation, FullCaseCitation):
            volume = citation.groups.get("volume")

            # Validate the volume
            if not volume or not volume.isdigit():
                continue

            if not citation.corrected_reporter():
                reporter_type = Citation.STATE
            else:
                cite_type_str = citation.all_editions[0].reporter.cite_type
                reporter_type = map_reporter_db_cite_type(cite_type_str)

            # Append the validated citation as a dictionary
            validated_citations.append(
                {
                    "volume": citation.groups["volume"],
                    "reporter": citation.corrected_reporter(),
                    "page": citation.groups["page"],
                    "type": reporter_type,
                }
            )

    return validated_citations


def query_possible_matches(
    valid_citations: list[dict], docket_number: str, date_filed: date
) -> QuerySet[Citation]:
    """Find matches for row data

    :param valid_citations: list of FullCaseCitation objects
    :param docket_number: cleaned docket number from row
    :param date_filed: formatted filed date from row

    :return: list of matched OpinionCluster
    """

    citation_queries = Q()

    for citation in valid_citations:
        citation_query = Q(**citation) & Q(
            cluster__docket__docket_number__contains=docket_number,
            cluster__date_filed=date_filed,
        )
        citation_queries |= citation_query
    possible_matches = Citation.objects.filter(
        citation_queries
    ).select_related("cluster")

    return possible_matches


def update_matched_case_name(
    matched_cluster: OpinionCluster, csv_case_name: str
) -> tuple[bool, bool]:
    """Update case name of matched cluster and related docket if empty any of them

    :param matched_cluster: OpinionCluster object
    :param csv_case_name: case name from csv row
    :return: tuple with boolean values if cluster and related docket case name updated
    """
    cluster_case_name_updated = False
    docket_case_name_updated = False

    if not matched_cluster.case_name:
        # Save case name in cluster when we don't have it
        matched_cluster.case_name = csv_case_name
        matched_cluster.save()
        logger.info(f"Case name updated for cluster id: {matched_cluster.id}")
        cluster_case_name_updated = True

    if not matched_cluster.docket.case_name:
        # Save case name in docket when we don't have it
        matched_cluster.docket.case_name = csv_case_name
        matched_cluster.docket.save()
        logger.info(
            f"Case name updated for docket id: {matched_cluster.docket.id}"
        )
        docket_case_name_updated = True

    return cluster_case_name_updated, docket_case_name_updated


def combine_initials(case_name: str) -> str:
    """Combine initials in case captions

    :param case_name: the case caption
    :return: the cleaned case caption
    """

    pattern = r"((?:[A-Z]\.?\s?){2,})(\s|$)"

    return re.sub(pattern, lambda m: m.group(0).replace(".", ""), case_name)


def process_csv(filepath: str, delay: float, dry_run: bool) -> None:
    """Process rows from csv file

    :param filepath: path to csv file
    :param delay: delay between saves in seconds
    :param dry_run: flag to simulate update process
    """

    total_clusters_updated = 0
    total_dockets_updated = 0

    logger.info(f"Processing {filepath}")
    df = pd.read_csv(filepath).dropna()
    for row in df.itertuples():
        (
            index,
            west_case_name,
            court,
            date_str,
            cite1,
            cite2,
            docket,
            volume,
        ) = row

        clean_docket_num = docket.strip('="').strip('"')
        if not clean_docket_num:
            logger.info(f"Row index: {index} - No docket number found.")
            continue

        date_filed = parse_date(date_str)
        if not date_filed:
            logger.info(
                f"Row index: {index} - No valid date found: {date_str}"
            )
            continue

        valid_citations = parse_citations([cite1, cite2])

        if not valid_citations:
            logger.info(f"Row index: {index} - Missing two valid citations.")
            continue

        # Query for possible matches using data from row
        possible_matches = query_possible_matches(
            valid_citations=valid_citations,
            docket_number=clean_docket_num,
            date_filed=date_filed,
        )

        if not possible_matches:
            logger.info(f"Row index: {index} - No matches found.")
            continue

        matches = []
        for match in possible_matches:
            cl_case_name = (
                match.cluster.case_name_full
                if match.cluster.case_name_full
                else match.cluster.case_name
            )

            west_case_name = combine_initials(west_case_name)
            cl_case_name = combine_initials(cl_case_name)

            case_name_match = check_case_names_match(
                west_case_name, cl_case_name
            )
            if case_name_match:
                matches.append(match)

        if len(matches) != 1:
            logger.warning(
                f"Row index: {index} - Failed, Matches found: {len(matches)} - Matches: {[cluster.id for cluster in matches]}"
            )
            continue

        logger.info(
            f"Row index: {index} - Match found: {matches[0].cluster_id} - Csv case name: {west_case_name}"
        )

        if dry_run:
            # Dry run, don't save anything
            continue

        with transaction.atomic():
            matched_cluster = matches[0].cluster

            # Update case names
            cluster_updated, docket_updated = update_matched_case_name(
                matched_cluster, west_case_name
            )

            if cluster_updated:
                total_clusters_updated = +1

            if docket_updated:
                total_dockets_updated = +1

            # Add any of the citations if possible
            for citation in valid_citations:
                if Citation.objects.filter(
                    cluster_id=matched_cluster.id,
                    reporter=citation.get("reporter"),
                ).exists():
                    # Avoid adding a citation if we already have a citation from the
                    # citation's reporter.
                    logger.info(
                        f"Can't add: {citation.get('volume')} {citation.get('reporter')} {citation.get('page')} to cluster id: {matched_cluster.id}. There is already "
                        f"a citation from that reporter."
                    )
                    continue
                citation["cluster_id"] = matched_cluster.id
                Citation.objects.get_or_create(**citation)

            add_citations_to_cluster(
                [
                    f"{cite.get('volume')} {cite.get('reporter')} {cite.get('page')}"
                    for cite in valid_citations
                ],
                matches[0].cluster_id,
            )

            # Wait between each processed row to avoid sending to many indexing tasks
            time.sleep(delay)

    if not dry_run:
        logger.info(f"Clusters updated: {total_clusters_updated}")
        logger.info(f"Dockets updated: {total_dockets_updated}")


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

    def handle(self, *args, **options):
        filepath = options["filepath"]
        delay = options["delay"]
        dry_run = options["dry_run"]

        if not filepath:
            raise CommandError(
                "Filepath is required. Use --filepath to specify the CSV file location."
            )

        process_csv(filepath, delay, dry_run)
