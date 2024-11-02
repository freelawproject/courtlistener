import logging
import re
from datetime import datetime

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from eyecite.tokenizers import HyperscanTokenizer

from cl.corpus_importer.utils import winnow_case_name
from cl.search.models import Citation, OpinionCluster

logger = logging.getLogger("django.db.backends")
logger.setLevel(logging.WARNING)
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
            "--strict",
            action="store_true",
            help="Enable strict matching for docket and date.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.1,
            help="How long to wait to update each opinion and docket (in seconds, allows floating numbers).",
        )

    def handle(self, *args, **options):
        filepath = options["filepath"]
        strict = options["strict"]

        if not filepath:
            raise CommandError(
                "Filepath is required. Use --filepath to specify the CSV file location."
            )

        # self.stdout.write(self.style.NOTICE(
        #     f"Processing CSV at {filepath} with strict mode set to {strict}"))
        process_csv(filepath, strict)


def process_csv(filepath: str, strict: bool):
    chunksize = 10**5  # Adjust for memory management
    match_count = 0
    total = 0
    rcount = 0
    row_count = pd.read_csv(filepath).shape[0]
    print(f"Total rows in CSV: {row_count}")
    start_time = datetime.now()
    print(f"Start time: {start_time}")

    for chunk in pd.read_csv(filepath, chunksize=chunksize):
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

                # TODO validate for any of the reporters
                if not formatted_date or "F.3d" not in citation:
                    print("skip?")
                    continue

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
                            match_count,
                            total,
                            rcount,
                        )
                        break

                if not match_found:
                    print(
                        "\n-----------\nFailed",
                        citation_str,
                        docket_num,
                        case_title,
                        parallel_cite_str,
                        filed_date,
                    )

            except Exception as e:
                logger.error(f"Unexpected error processing row {row}: {e}")

    # self.stdout.write(
    #     self.style.SUCCESS(f"Total matches found: {match_count}"))
    print(f"Total matches found: {match_count}")
    end_time = datetime.now()
    print(f"End time: {end_time-start_time}")


def parse_date(date_str: str):
    """Attempts to parse the filed date into a datetime object."""
    for fmt in ("%B %d, %Y", "%d-%b-%y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    logger.warning(f"Invalid date format: {date_str}")
    return None


def is_match(citation, docket_num, formatted_date, case_title):
    """
    Checks if the database citation matches docket number, filing date, and case title.
    """
    # Check docket number and date
    failed = 0
    if (
        citation.cluster.docket.docket_number.lower() not in docket_num.lower()
        or citation.cluster.date_filed != formatted_date
    ):
        if (
            citation.cluster.docket.docket_number.lower()
            not in docket_num.lower()
        ):
            failed += 1
        if citation.cluster.date_filed != formatted_date:
            failed += 10
        return False

    # Compare case name overlaps if strict matching on
    if citation.cluster.case_name_full == "":
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

        return list(order1.keys()) == list(order2.keys())

    return False


def get_term_indices(terms, text: str):
    """
    Returns a dictionary of each term's index in the text, sorted by appearance order.
    """
    term_indices = {
        term: match.start()
        for term in terms
        if (match := re.search(r"\b" + re.escape(term) + r"\b", text.lower()))
    }
    return dict(sorted(term_indices.items(), key=lambda item: item[1]))


def display_match_info(
    citation, case_title, parallel_cite, match_count, total, rcount
):
    """
    Displays information about a match in a structured format.
    """
    print(
        f"\n============================= {match_count} {total} {100 * (rcount / 285417)}"
    )
    print(
        f"Matched Case in DB: {citation.cluster.id} - {citation.cluster.case_name_full if citation.cluster.case_name_full else citation.cluster.case_name}"
    )
    print(f"CSV Case Title: {case_title}")
    print(f"Matching Citation: {citation}")
    print(f"Parallel Cite: {parallel_cite}")
    # TODO save in DB
