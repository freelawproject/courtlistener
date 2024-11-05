import logging
import re
import time
from datetime import date, datetime
from typing import Set

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from eyecite.tokenizers import HyperscanTokenizer

from cl.corpus_importer.utils import winnow_case_name
from cl.lib.model_helpers import clean_docket_number
from cl.search.models import Citation

logger = logging.getLogger(__name__)
HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


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


def process_csv(
    filepath: str, delay: float, dry_run: bool, chunk_size: int
) -> None:
    """Process rows from csv file

    :param filepath: path to csv file
    :param delay: delay between saves in seconds
    :param dry_run: flag to simulate update process
    :param chunk_size: number of rows to read at a time
    """
    match_count = 0
    total = 0
    rcount = 0
    row_count = pd.read_csv(filepath).shape[0]
    logger.info(f"Total rows in CSV: {row_count}")
    start_time = datetime.now()
    logger.info(f"Start time: {start_time}")

    for chunk in pd.read_csv(filepath, chunksize=chunk_size):
        for _, row in chunk.iterrows():
            rcount += 1
            match_found = False
            try:
                # Retrieve fields and parse date
                citation, docket_num, case_title, parallel_cite, filed_date = (
                    row.get("Citation"),
                    row.get("Docket Num"),
                    row.get("Title"),
                    row.get("Parallel Cite"),
                    row.get("Filed Date"),
                )

                citation_str = citation
                parallel_cite_str = parallel_cite

                clean_cite = re.sub(r"\s+", " ", citation)
                cites = get_citations(
                    clean_cite, tokenizer=HYPERSCAN_TOKENIZER
                )
                cites = [
                    cite
                    for cite in cites
                    if isinstance(cite, FullCaseCitation)
                ]
                if not cites:
                    logger.warning(f"Invalid citation: {clean_cite}")
                    continue

                clean_cite = re.sub(r"\s+", " ", parallel_cite)
                parallel_cites = get_citations(
                    clean_cite, tokenizer=HYPERSCAN_TOKENIZER
                )
                parallel_cites = [
                    cite
                    for cite in parallel_cites
                    if isinstance(cite, FullCaseCitation)
                ]
                if not parallel_cites:
                    logger.warning(f"Invalid parallel citation: {clean_cite}")
                    continue

                main_citation = cites[0]
                parallel_cite = parallel_cites[0]

                if Citation.objects.filter(
                    volume=parallel_cite.groups["volume"],
                    reporter=parallel_cite.corrected_reporter(),
                    page=parallel_cite.groups["page"],
                ).exists():
                    continue

                if not all([main_citation, docket_num, case_title]):
                    logger.warning(
                        "Missing essential fields in row; skipping."
                    )
                    continue

                formatted_date = parse_date(filed_date)

                # Query citations in the database
                citations = Citation.objects.filter(
                    volume=main_citation.groups["volume"],
                    reporter=main_citation.corrected_reporter(),
                    page=main_citation.groups["page"],
                )
                if not citations:
                    continue
                total += 1

                for citation_obj in citations:
                    if is_match(
                        citation_obj, docket_num, formatted_date, case_title
                    ):
                        match_found = True
                        match_count += 1

                        display_match_info(
                            citation_obj,
                            case_title,
                            parallel_cite_str,
                        )

                        if not dry_run:
                            cluster_casename = (
                                citation_obj.cluster.case_name
                                if citation_obj.cluster.case_name
                                else citation_obj.cluster.case_name_full
                            )
                            docket_casename = (
                                citation_obj.cluster.docket.case_name
                                if citation_obj.cluster.docket.case_name
                                else citation_obj.cluster.docket.case_name_full
                            )
                            if len(case_title) < len(cluster_casename):
                                # Save new case name in cluster
                                logger.info(
                                    f"Case name updated for cluster id: {citation_obj.cluster_id}"
                                )
                                citation_obj.cluster.case_name = case_title
                                citation_obj.cluster.save()
                            else:
                                logger.info(
                                    f"Cluster: {citation_obj.cluster_id} already have the best name."
                                )

                            if len(case_title) < len(docket_casename):
                                # Save new case name in docket
                                logger.info(
                                    f"Case name updated for docket id: {citation_obj.cluster.docket_id}"
                                )
                                citation_obj.cluster.docket.case_name = (
                                    case_title
                                )
                                citation_obj.cluster.docket.save()

                            else:
                                logger.info(
                                    f"Docket: {citation_obj.cluster.docket_id} already have the best name."
                                )

                            # Wait between updates to avoid issues with redis memory
                            time.sleep(delay)

                        break

                if not match_found:
                    logger.info(
                        f"Failed: {citation_str} - {docket_num} - {case_title} - {parallel_cite_str} - {filed_date}"
                    )

            except Exception as e:
                logger.error(f"Unexpected error processing row {row}: {e}")

    logger.info(f"Total matches found: {match_count}")
    end_time = datetime.now()
    logger.info(f"End time: {end_time - start_time}")


def parse_date(date_str: str) -> date | None:
    """Attempts to parse the filed date into a datetime object.

    :param date_str: date string
    :return: date object or none
    """
    for fmt in ("%B %d, %Y", "%d-%b-%y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    logger.warning(f"Invalid date format: {date_str}")
    return None


def is_match(citation, docket_num, formatted_date, case_title) -> bool:
    """Checks if the database citation matches docket number, filing date, and case
    title.

    :param citation: Citation object that matched csv citation
    :param docket_num: Docket number from csv
    :param formatted_date: Formated date from csv
    :param case_title: Case name from csv
    :return: True if match found else False
    """

    # Prepare docket numbers
    cleaned_cluster_docket_number = clean_docket_number(
        citation.cluster.docket.docket_number
    )
    cleaned_docket_num = clean_docket_number(docket_num)

    # In some cases clean_docket_number returns an empty string, try with original
    # docket numbers
    if not cleaned_cluster_docket_number:
        cleaned_cluster_docket_number = citation.cluster.docket.docket_number

    if not cleaned_docket_num:
        cleaned_docket_num = docket_num

    # Check docket number and date
    failed = 0
    if (
        cleaned_cluster_docket_number.lower() not in cleaned_docket_num.lower()
        or citation.cluster.date_filed != formatted_date
    ):
        if (
            cleaned_cluster_docket_number.lower()
            not in cleaned_docket_num.lower()
        ):
            failed += 1
        if citation.cluster.date_filed != formatted_date:
            failed += 10
        return False

    if (
        not citation.cluster.case_name_full
        or citation.cluster.case_name_full == ""
    ):
        cn = citation.cluster.case_name
    else:
        cn = citation.cluster.case_name_full

    c1 = winnow_case_name(cn)
    c2 = winnow_case_name(case_title)

    overlap = c1 & c2
    if overlap:
        cf = (
            citation.cluster.case_name_full
            if citation.cluster.case_name_full
            else citation.cluster.case_name
        )
        order1 = get_term_indices(overlap, cf)
        order2 = get_term_indices(overlap, case_title)

        return list(order1.keys()) == list(order2.keys()) and len(overlap) > 1

    return False


def get_term_indices(terms: Set, text: str) -> dict:
    """Returns a dictionary of each term's index in the text, sorted by appearance order.

    :param terms: set of terms to search for
    :param text: text to search for terms
    :return: dict of each term's index in the text
    """
    term_indices = {
        term: match.start()
        for term in terms
        if (match := re.search(r"\b" + re.escape(term) + r"\b", text.lower()))
    }
    return dict(sorted(term_indices.items(), key=lambda item: item[1]))


def display_match_info(citation, case_title, parallel_cite):
    """Displays information about a match in a structured format.

    :param citation: Citation object
    :param case_title: case name from csv
    :param parallel_cite: cite from csv
    """
    logger.info(
        f"Matched Case in DB: {citation.cluster.id} - {citation.cluster.case_name_full if citation.cluster.case_name_full else citation.cluster.case_name}"
    )
    logger.info(f"CSV Case Title: {case_title}")
    logger.info(f"Matching Citation: {citation}")
    logger.info(f"Parallel Cite: {parallel_cite}")
