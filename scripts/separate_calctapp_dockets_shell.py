"""Issue #8282. Paste this whole file into `python manage.py shell`.

It moves `calctapp` dockets to the court of their district or division. The
letter of the docket number gives the court: A175811 goes to calctapp1d. It
also moves `calctapp4d` dockets to their division.
Old numbers, like "Civ. No. 288.", and Appellate Division numbers, like
"JAD13-03", stay where they are.

The paste only runs a dry run, which changes nothing.
If the dry run output matches the expected numbers, type: apply()

By default only exact numbers, like A175811, move. Numbers with extra text,
like "No. A011998" or "A072114, A074710", move only with
include_noisy=True, and only if all their district numbers have the same
letter. To see them first, type: dry_run(include_noisy=True)

A docket does not move if its target court already has a docket with the
same number. The report lists it as skipped.

apply() adds every move to REPORT_PATH. Keep that file: rollback() and
reindex() need it. If apply() stops halfway, type apply() again. It moves
only the dockets that are still in the old court. Then type reindex(), to
send every move to search again.
"""

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

import pgtrigger
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from cl.lib.celery_utils import CeleryThrottle
from cl.search.models import Docket, OpinionCluster, ParentheticalGroup
from cl.search.tasks import update_children_docs_by_query, update_es_document

DRY_RUN_REPORT_PATH = "/tmp/8282-dry-run.csv"
REPORT_PATH = "/tmp/8282-run.csv"
ROLLBACK_REPORT_PATH = "/tmp/8282-rollback.csv"
REPORT_COLUMNS = [
    "docket_id",
    "docket_number",
    "from_court_id",
    "to_court_id",
    "number_kind",
    "action",
]
BATCH_SIZE = 500
COURT_BY_LETTER = {
    "A": "calctapp1d",
    "B": "calctapp2d",
    "C": "calctapp3d",
    "D": "calctapp4d1",
    "E": "calctapp4d2",
    "G": "calctapp4d3",
    "F": "calctapp5d",
    "H": "calctapp6d",
}
LETTERS_BY_FROM_COURT = {
    "calctapp": set(COURT_BY_LETTER),
    "calctapp4d": {"D", "E", "G"},
}
CLEAN_NUMBER = re.compile(r"[A-H]\d{6}")
DISTRICT_NUMBER = re.compile(r"(?<![A-Za-z0-9])[A-H]\d{6}(?!\d)")
# Search keeps its own copy of the court fields, so a move must send them.
# The parenthetical group index keeps only court_id.
SEARCH_FIELDS = ["court_id", "court", "court_citation_string"]
CLUSTER_FIELDS_MAP = {
    "court_id": ["court_id", "court_exact"],
    "court": ["court"],
    "court_citation_string": ["court_citation_string"],
}


def district_numbers(docket_number: str) -> tuple[str, set[str]]:
    """Return the kind of a docket number and the district numbers in it."""
    if CLEAN_NUMBER.fullmatch(docket_number):
        return "clean", {docket_number}
    numbers = set(DISTRICT_NUMBER.findall(docket_number))
    return ("noisy" if numbers else "other"), numbers


def plan(include_noisy: bool) -> tuple[list[dict[str, str]], Counter]:
    """Find the dockets to move, and count the dockets that stay, by reason."""
    moves, stays = [], Counter()
    dockets = Docket.objects.filter(
        court_id__in=LETTERS_BY_FROM_COURT
    ).values_list("pk", "docket_number", "court_id")
    for pk, docket_number, court_id in dockets.iterator():
        kind, numbers = district_numbers(docket_number or "")
        letters = {number[0] for number in numbers}
        if kind == "other":
            stays[f"{court_id}: no district number"] += 1
        elif kind == "noisy" and not include_noisy:
            stays[f"{court_id}: noisy number, not included"] += 1
        elif len(letters) > 1:
            stays[f"{court_id}: mixed district letters"] += 1
        elif not letters <= LETTERS_BY_FROM_COURT[court_id]:
            stays[f"{court_id}: letter of another court"] += 1
        else:
            moves.append(
                {
                    "docket_id": str(pk),
                    "docket_number": docket_number,
                    "from_court_id": court_id,
                    "to_court_id": COURT_BY_LETTER[letters.pop()],
                    "number_kind": kind,
                }
            )
    return moves, stays


def taken_numbers(
    court_id: str, numbers: set[str], ignored_ids: set[int]
) -> set[str]:
    """Return the numbers that a docket of the court already uses.

    Dockets in ignored_ids do not count. They are the dockets this script
    moved, so two duplicate `calctapp` dockets still move together.
    """
    dockets = Docket.objects.filter(court_id=court_id).filter(
        Q(docket_number__in=numbers) | Q(docket_number_raw__in=numbers)
    )
    taken = set()
    for pk, docket_number, docket_number_raw in dockets.values_list(
        "pk", "docket_number", "docket_number_raw"
    ):
        if pk not in ignored_ids:
            taken |= {docket_number, docket_number_raw} & numbers
    return taken


def update_search(docket_ids: list[int], throttle: CeleryThrottle) -> None:
    """Queue the court fields of the dockets' opinions for search.

    It also queues the dockets' parenthetical groups, which a docket save
    would update through its signals.
    """
    clusters = OpinionCluster.objects.filter(
        docket_id__in=docket_ids
    ).values_list("pk", "docket_id")
    for cluster_id, docket_id in clusters:
        throttle.maybe_wait()
        update_es_document.si(
            "OpinionClusterDocument",
            SEARCH_FIELDS,
            ("search.OpinionCluster", cluster_id),
            ("search.Docket", docket_id),
            CLUSTER_FIELDS_MAP,
            True,  # skip_percolator_request: a move must not send alerts
        ).apply_async(queue=settings.CELERY_ETL_TASK_QUEUE)
        update_children_docs_by_query.si(
            "OpinionDocument", cluster_id, SEARCH_FIELDS
        ).apply_async(queue=settings.CELERY_ETL_TASK_QUEUE)
    groups = ParentheticalGroup.objects.filter(
        opinion__cluster__docket_id__in=docket_ids
    ).values_list("pk", "opinion__cluster__docket_id")
    for group_id, docket_id in groups:
        throttle.maybe_wait()
        update_es_document.si(
            "ParentheticalGroupDocument",
            ["court_id"],
            ("search.ParentheticalGroup", group_id),
            ("search.Docket", docket_id),
            {"court_id": ["court_id"]},
            True,  # skip_percolator_request
        ).apply_async(queue=settings.CELERY_ETL_TASK_QUEUE)


def move_batch(
    rows: list[dict[str, str]],
    dry_run: bool,
    check_numbers: bool,
    moved_ids: set[int],
    writer: csv.DictWriter,
) -> list[int]:
    """Move one batch of dockets from one court to another.

    The report rows are written before the commit. If the commit fails, the
    report says "moved" for dockets that did not move, which rollback() and
    reindex() skip. The reverse, a move that the report misses, cannot happen.
    """
    from_court_id = rows[0]["from_court_id"]
    to_court_id = rows[0]["to_court_id"]
    numbers_by_id = {
        int(row["docket_id"]): district_numbers(row["docket_number"])[1]
        | {row["docket_number"]}
        for row in rows
    }
    with transaction.atomic():
        taken = set()
        if check_numbers:
            taken = taken_numbers(
                to_court_id, set().union(*numbers_by_id.values()), moved_ids
            )
        free_ids = [
            pk for pk, nums in numbers_by_id.items() if not nums & taken
        ]
        moved = []
        if not dry_run:
            moved = list(
                Docket.objects.select_for_update()
                .filter(pk__in=free_ids, court_id=from_court_id)
                .values_list("pk", flat=True)
            )
            with pgtrigger.ignore("search.Docket:update_update"):
                Docket.objects.filter(pk__in=moved).update(
                    court_id=to_court_id, date_modified=now()
                )
        for row in rows:
            pk = int(row["docket_id"])
            if numbers_by_id[pk] & taken:
                action = f"skipped: {to_court_id} already has this number"
            elif dry_run:
                action = "would move"
            elif pk in moved:
                action = "moved"
            else:
                action = f"skipped: docket is no longer in {from_court_id}"
            writer.writerow({**row, "action": action})
    moved_ids.update(moved)
    return moved


def run_moves(
    rows: list[dict[str, str]],
    dry_run: bool,
    check_numbers: bool,
    report_path: str,
    moved_ids: set[int],
) -> Counter:
    """Move the dockets in batches, and add the result to the report."""
    # Moves queue search tasks, so wait when the ETL queue is full.
    throttle = CeleryThrottle(queue_name=settings.CELERY_ETL_TASK_QUEUE)
    by_courts = defaultdict(list)
    for row in rows:
        by_courts[(row["from_court_id"], row["to_court_id"])].append(row)
    new_file = dry_run or not Path(report_path).exists()
    with Path(report_path).open(
        "w" if dry_run else "a", newline="", buffering=1
    ) as report_file:
        writer = csv.DictWriter(report_file, fieldnames=REPORT_COLUMNS)
        if new_file:
            writer.writeheader()
        done = 0
        for courts, court_rows in sorted(by_courts.items()):
            for start in range(0, len(court_rows), BATCH_SIZE):
                batch = court_rows[start : start + BATCH_SIZE]
                moved = move_batch(
                    batch, dry_run, check_numbers, moved_ids, writer
                )
                if moved:
                    update_search(moved, throttle)
                done += len(batch)
                print(f"{done} of {len(rows)} ({courts[0]} -> {courts[1]})")
    actions = report_actions(report_path)
    print("DRY RUN, nothing changed." if dry_run else "DONE.")
    print(f"Report: {report_path}")
    return actions


def read_rows(path: str) -> list[dict[str, str]]:
    """Read the rows of a CSV file."""
    if not Path(path).exists():
        return []
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))


def report_actions(path: str) -> Counter:
    """Count the last action of each docket in a report.

    A rerun of apply() adds new rows for the dockets it skipped before, so
    only the last row of a docket counts.
    """
    last = {row["docket_id"]: row["action"] for row in read_rows(path)}
    return Counter(last.values())


def moved_rows() -> list[dict[str, str]]:
    """Return the last "moved" row of each docket in REPORT_PATH."""
    rows = {}
    for row in read_rows(REPORT_PATH):
        if row["action"] == "moved":
            rows[row["docket_id"]] = row
    return list(rows.values())


def print_summary(actions: Counter, stays: Counter) -> None:
    """Print the counts of the report actions and of the dockets that stay."""
    print("Actions:")
    for action, count in sorted(actions.items()):
        print(f"  {action}: {count}")
    print("Dockets that stay:")
    for reason, count in sorted(stays.items()):
        print(f"  {reason}: {count}")


def dry_run(include_noisy: bool = False) -> Counter:
    """Write the moves that apply() would make to DRY_RUN_REPORT_PATH."""
    moves, stays = plan(include_noisy)
    actions = run_moves(moves, True, True, DRY_RUN_REPORT_PATH, set())
    print_summary(actions, stays)
    return actions


def apply(include_noisy: bool = False) -> Counter:
    """Move the dockets for real, and queue the changes for search."""
    moves, stays = plan(include_noisy)
    moved_ids = {int(row["docket_id"]) for row in moved_rows()}
    actions = run_moves(moves, False, True, REPORT_PATH, moved_ids)
    print_summary(actions, stays)
    return actions


def rollback(dry_run: bool = False) -> Counter:
    """Undo apply(): move each docket it moved back to its old court."""
    rows = [
        {
            **row,
            "from_court_id": row["to_court_id"],
            "to_court_id": row["from_court_id"],
        }
        for row in moved_rows()
    ]
    if Path(ROLLBACK_REPORT_PATH).exists() and not dry_run:
        Path(ROLLBACK_REPORT_PATH).rename(f"{ROLLBACK_REPORT_PATH}.old")
    actions = run_moves(rows, dry_run, False, ROLLBACK_REPORT_PATH, set())
    print_summary(actions, Counter())
    return actions


def reindex() -> None:
    """Queue the court fields for search again, for every docket moved."""
    throttle = CeleryThrottle(queue_name=settings.CELERY_ETL_TASK_QUEUE)
    to_court_by_id = {
        int(row["docket_id"]): row["to_court_id"] for row in moved_rows()
    }
    current = Docket.objects.filter(pk__in=to_court_by_id).values_list(
        "pk", "court_id"
    )
    # Skip a docket that rollback() or someone else moved after apply().
    docket_ids = [
        pk for pk, court_id in current if court_id == to_court_by_id[pk]
    ]
    for start in range(0, len(docket_ids), BATCH_SIZE):
        update_search(docket_ids[start : start + BATCH_SIZE], throttle)
        print(
            f"{min(start + BATCH_SIZE, len(docket_ids))} of {len(docket_ids)}"
        )
    print("DONE.")


stats = dry_run()
print(
    "Expected, from the dev database on 2026-11-24: about 93,600 'would move'"
    " and about 130 skipped. If the numbers are close, type: apply()"
)
