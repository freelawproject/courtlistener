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
from juriscraper.lib.string_utils import harmonize

from cl.citations.utils import map_reporter_db_cite_type
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
    words = []
    for word in WORD_PATTERN.findall(case_name):
        if len(word) > 1:
            # Only keep words with more than one character
            words.append(word.lower())

    # Return only valid words
    return set(words) - FALSE_POSITIVES


def check_case_names_match(west_case_name: str, cl_case_name: str) -> bool:
    """Compare two case name and decide whether they are the same or not

    Tokenize each string, capturing both words and abbreviations with periods and
    convert all words to lowercase for case-insensitive matching and check if there is
    an overlap between case names

    :param west_case_name: case name from csv
    :param cl_case_name: case name from cluster
    :return: True if they match else False
    """

    overlap = tokenize_case_name(west_case_name) & tokenize_case_name(
        cl_case_name
    )

    if not overlap:
        # if no hits no match on name - move along
        return False

    # Check for "v." in title
    if "v." not in west_case_name.lower():
        # in the matter of Smith
        # if no V. - likely an "in re" case and only match on at least 1 name
        return True

    # otherwise check if a match occurs on both sides of the V
    v_index = west_case_name.lower().index("v.")
    hit_indices = [west_case_name.lower().find(hit) for hit in overlap]

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
    logger.warning("Invalid date format: %s", date_str)
    return None


def parse_citations(citation_strings: list[str]) -> list[dict]:
    """Validate citations with Eyecite.

    :param citation_strings: List of citation strings to validate.
    :return: List of validated citation dictionaries with volume, reporter, and page.
    """
    validated_citations = []

    for cite_str in citation_strings:
        # Get citations from the string

        # We find all the citations that could match a cluster to update the case name
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

    It will remove duplicates, it could happen if we already have both citations, if we
    have multiple matches, these must be unique

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
    possible_matches = (
        Citation.objects.filter(citation_queries)
        .select_related("cluster")
        .distinct("cluster__id")
    )

    return possible_matches


def update_matched_case_name(
    matched_cluster: OpinionCluster, west_case_name: str
) -> tuple[bool, bool]:
    """Update case name of matched cluster and related docket if empty any of them

    :param matched_cluster: OpinionCluster object
    :param west_case_name: case name from csv row
    :return: tuple with boolean values if cluster and related docket case name updated
    """
    cluster_case_name_updated = False
    docket_case_name_updated = False

    if not matched_cluster.case_name:
        # Save case name in cluster when we don't have it
        matched_cluster.case_name = harmonize(west_case_name)
        matched_cluster.save()
        logger.info("Case name updated for cluster id: %s", matched_cluster.id)
        cluster_case_name_updated = True

    if not matched_cluster.docket.case_name:
        # Save case name in docket when we don't have it
        matched_cluster.docket.case_name = harmonize(west_case_name)
        matched_cluster.docket.save()
        logger.info(
            "Case name updated for docket id: %s", matched_cluster.docket.id
        )
        docket_case_name_updated = True

    return cluster_case_name_updated, docket_case_name_updated


def combine_initials(case_name: str) -> str:
    """Combine initials in case captions

    This function identifies initials (e.g., "J. D. E.") in a case name and combines
    them into a compressed format without spaces or periods (e.g., "JDE").

    :param case_name: the case caption
    :return: the cleaned case caption
    """

    initials_pattern = re.compile(r"(\b[A-Z]\.?\s?){2,}(\s|$)")

    matches = initials_pattern.finditer(case_name)
    if matches:
        for match in matches:
            initials = match.group()
            compressed_initials = re.sub(r"(?!\s$)[\s\.]", "", initials)
            case_name = case_name.replace(initials, compressed_initials)
    return case_name


def process_csv(filepath: str, delay: float, dry_run: bool) -> None:
    """Process rows from csv file

    :param filepath: path to csv file
    :param delay: delay between saves in seconds
    :param dry_run: flag to simulate update process
    """

    total_clusters_updated = 0
    total_dockets_updated = 0
    total_citations_added = 0

    logger.info("Processing %s", filepath)
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
            logger.info("Row index: %s - No docket number found.", index)
            continue

        date_filed = parse_date(date_str)
        if not date_filed:
            logger.info(
                "Row index: %s - No valid date found: %s", index, date_str
            )
            continue

        west_citations: list[str] = [cite1, cite2]
        valid_citations = parse_citations(west_citations)

        if not valid_citations:
            logger.info("Row index: %s - Missing valid citations.", index)
            continue

        # Query for possible matches using data from row
        possible_matches = query_possible_matches(
            valid_citations=valid_citations,
            docket_number=clean_docket_num,
            date_filed=date_filed,
        )

        if not possible_matches:
            logger.info("Row index: %s - No possible matches found.", index)
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
                matches.append(match.cluster)

        if len(matches) == 0:
            # No match found within possible matches, go to next row
            logger.info(
                "Row index: %s - No match found within possible matches.",
                index,
            )
            continue
        elif len(matches) > 1:
            # More than one match, log and go to next row
            matches_found = ", ".join([str(cluster.id) for cluster in matches])
            logger.warning(
                "Row index: %s - Multiple matches found: %s",
                index,
                matches_found,
            )
            continue

        # Single match found
        logger.info(
            "Row index: %s - Match found: %s - West case name: %s",
            index,
            matches[0].id,
            west_case_name,
        )

        if dry_run:
            # Dry run, don't save anything
            continue

        with transaction.atomic():
            matched_cluster = matches[0]

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

                citation["cluster_id"] = matched_cluster.id
                if Citation.objects.filter(**citation).exists():
                    # We already have the citation
                    continue
                elif Citation.objects.filter(
                    cluster_id=citation["cluster_id"],
                    reporter=citation.get("reporter"),
                ).exists():
                    # # Same reporter, different citation, revert changes
                    logger.warning(
                        "Row index: %s - Revert changes for cluster id: %s",
                        index,
                        matched_cluster.id,
                    )
                    transaction.set_rollback(True)
                    break
                else:
                    new_citation = Citation.objects.create(**citation)
                    logger.info(
                        "New citation added: %s to cluster id: %s",
                        new_citation,
                        matched_cluster.id,
                    )
                    total_citations_added += 1

            # Wait between each processed row to avoid sending to many indexing tasks
            time.sleep(delay)

    logger.info("Clusters updated: %s", total_clusters_updated)
    logger.info("Dockets updated: %s", total_dockets_updated)
    logger.info("Citations added: %s", total_citations_added)


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
