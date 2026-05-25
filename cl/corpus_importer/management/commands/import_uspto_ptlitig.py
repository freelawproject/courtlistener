import csv
import sys
from collections import defaultdict
from itertools import groupby
from operator import itemgetter
from pathlib import Path

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, transaction

from cl.corpus_importer.ptlitig import (
    add_ptlitig_docket_entries,
    make_party_list,
    merge_ptlitig_docket,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Docket

# Some PTLITIG docket-entry descriptions are longer than csv's default limit.
csv.field_size_limit(sys.maxsize)


def _load_grouped(path: Path) -> dict[str, list[dict[str, str]]]:
    """Read a PTLITIG CSV into lists of rows grouped by case_row_id."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            grouped[row["case_row_id"]].append(row)
    return grouped


def _load_nature_of_suit(path: Path) -> dict[tuple[str, str], str]:
    """Read pacer_cases.csv into a {(district_id, case_number): nos} lookup.

    pacer_cases has no case_row_id, so it is keyed on (district, case number).
    """
    nos_by_case: dict[tuple[str, str], str] = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            nos_by_case[(row["district_id"], row["case_number"])] = row["nos"]
    return nos_by_case


def import_ptlitig(input_dir: str, limit: int, offset: int) -> None:
    """Import the PTLITIG cases found in the CSV files under input_dir.

    The per-case files (patents, names, attorneys) are small enough to hold in
    memory; the much larger documents.csv is streamed in a second pass, relying
    on the file being grouped by case_row_id.
    """
    directory = Path(input_dir)

    logger.info("Loading PTLITIG CSVs from %s", directory)
    nos_by_case = _load_nature_of_suit(directory / "pacer_cases.csv")
    patents = _load_grouped(directory / "patents.csv")
    names = _load_grouped(directory / "names.csv")
    attorneys = _load_grouped(directory / "attorneys.csv")
    with (directory / "cases.csv").open(newline="") as f:
        cases = list(csv.DictReader(f))

    # Pass 1: merge docket metadata, parties, and patents for every case, and
    # remember each resulting docket so the second pass can add its entries.
    docket_ids_by_case: dict[str, int] = {}
    for i, case in enumerate(cases):
        if i < offset or (limit and i >= offset + limit):
            continue
        case_row_id = case["case_row_id"]
        nos = nos_by_case.get((case["district_id"], case["case_number"]), "")
        party_list = make_party_list(
            names.get(case_row_id, []), attorneys.get(case_row_id, [])
        )
        try:
            d = merge_ptlitig_docket(
                case, nos, patents.get(case_row_id, []), party_list
            )
        except (DatabaseError, ObjectDoesNotExist):
            # Skip a single case that fails on a data problem (e.g. an unknown
            # court or a constraint violation); let other errors surface.
            logger.exception(
                "Failed to merge PTLITIG case %s (%s %s)",
                case_row_id,
                case["district_id"],
                case["case_number"],
            )
            continue
        docket_ids_by_case[case_row_id] = d.pk
        if i and i % 1000 == 0:
            logger.info("Merged %s PTLITIG cases", i)

    # Pass 2: stream documents.csv (grouped by case_row_id) and add each case's
    # entries. add_ptlitig_docket_entries only creates the entries a docket is
    # missing, so this is a safe gap-fill even for dockets RECAP already covers.
    logger.info("Adding docket entries to %s dockets", len(docket_ids_by_case))
    with (directory / "documents.csv").open(newline="") as f:
        reader = csv.DictReader(f)
        for case_row_id, rows in groupby(
            reader, key=itemgetter("case_row_id")
        ):
            docket_id = docket_ids_by_case.get(case_row_id)
            if docket_id is None:
                continue
            try:
                with transaction.atomic():
                    add_ptlitig_docket_entries(
                        Docket.objects.get(pk=docket_id), list(rows)
                    )
            except (DatabaseError, ObjectDoesNotExist):
                # As above: skip a case whose entries fail on a data problem.
                logger.exception(
                    "Failed to add entries for PTLITIG case %s", case_row_id
                )


class Command(VerboseCommand):
    help = "Import USPTO Patent Litigation Docket Reports (PTLITIG) data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input-dir",
            required=True,
            help="Directory containing the extracted PTLITIG CSV files.",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="Number of cases to skip before importing (for resuming).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of cases to import (0 imports all).",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        import_ptlitig(
            options["input_dir"], options["limit"], options["offset"]
        )
