# Issue #8085. Paste this whole file into `python manage.py shell`.
# It downloads the CSV of changes attached to the issue from CHANGES_URL. Each
# row is a docket to move: docket_id, docket_number, cluster_ids,
# from_court_id and to_court_id.
# The paste only runs a dry run, which changes nothing.
# If the dry run output matches the expected line, type: apply()
# apply() moves the dockets and queues Elasticsearch updates on the Celery ETL
# queue. It writes REPORT_PATH, which records every change it made.
# Keep that file: rollback() needs it to undo apply().
import csv
import io
import os
from collections import Counter

import requests
from django.conf import settings

from cl.lib.celery_utils import CeleryThrottle
from cl.search.models import SEARCH_TYPES, Docket
from cl.search.tasks import es_save_document, index_parent_and_child_docs

CHANGES_URL = (
    "https://github.com/user-attachments/files/35108858/8085-court-changes.csv"
)
DRY_RUN_REPORT_PATH = "/tmp/8085-dry-run.csv"
REPORT_PATH = "/tmp/8085-run.csv"
ROLLBACK_REPORT_PATH = "/tmp/8085-rollback.csv"
REPORT_COLUMNS = [
    "docket_id",
    "docket_number",
    "cluster_ids",
    "from_court_id",
    "to_court_id",
    "action",
]


def move_docket(docket: Docket, court_id: str) -> None:
    """Move a docket to another court and update its opinions in search.

    Saving a docket only updates `court_exact` in search, so the other court
    fields are rebuilt here.
    """
    docket.court_id = court_id
    docket.save()
    cluster_ids = list(docket.clusters.values_list("pk", flat=True))
    for cluster_id in cluster_ids:
        es_save_document.si(
            cluster_id,
            "search.OpinionCluster",
            "OpinionClusterDocument",
            skip_percolator_request=True,
        ).apply_async(queue=settings.CELERY_ETL_TASK_QUEUE)
    index_parent_and_child_docs.si(
        cluster_ids, SEARCH_TYPES.OPINION
    ).apply_async(queue=settings.CELERY_ETL_TASK_QUEUE)


def apply_change(row: dict[str, str], dry_run: bool) -> dict[str, str]:
    """Move a docket as a row of changes says, or say why it was skipped.

    The docket only moves if it still looks as it did when the CSV was made,
    so a docket that changed since then is never moved by mistake.
    """
    report = {column: row[column] for column in REPORT_COLUMNS[:-1]}
    if not (docket := Docket.objects.filter(pk=row["docket_id"]).first()):
        action = "skipped: docket no longer exists"
    elif docket.court_id != row["from_court_id"]:
        action = f"skipped: docket is in {docket.court_id}"
    elif docket.source != Docket.HARVARD:
        action = "skipped: docket has data from other sources"
    elif (
        " ".join(
            map(str, sorted(docket.clusters.values_list("pk", flat=True)))
        )
        != row["cluster_ids"]
    ):
        action = "skipped: docket's clusters changed"
    elif dry_run:
        action = "would move"
    else:
        move_docket(docket, row["to_court_id"])
        action = "moved"
    return {**report, "action": action}


def read_rows(path: str) -> list[dict[str, str]]:
    """Read the rows of a CSV file."""
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def download_changes() -> list[dict[str, str]]:
    """Download the CSV of changes from the issue and read its rows."""
    response = requests.get(CHANGES_URL, timeout=60)
    response.raise_for_status()
    return list(csv.DictReader(io.StringIO(response.text)))


def run_rows(
    rows: list[dict[str, str]], dry_run: bool, report_path: str
) -> Counter:
    """Apply each row and write its result to the report right away."""
    # Moves queue Elasticsearch tasks, so wait when the ETL queue is full.
    throttle = CeleryThrottle(queue_name=settings.CELERY_ETL_TASK_QUEUE)
    actions: Counter[str] = Counter()
    with open(report_path, "w", newline="", buffering=1) as report_file:
        writer = csv.DictWriter(report_file, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        for i, row in enumerate(rows, start=1):
            if not dry_run:
                throttle.maybe_wait()
            report = apply_change(row, dry_run)
            writer.writerow(report)
            actions[report["action"]] += 1
            if i % 250 == 0:
                print(f"{i} of {len(rows)}")
    print("DRY RUN, nothing changed." if dry_run else "DONE.")
    print(f"Report: {report_path}")
    print(dict(actions))
    return actions


def apply() -> Counter | None:
    """Move the dockets for real.

    It refuses to run twice, because a second run would overwrite the report
    that rollback() needs.
    """
    if os.path.exists(REPORT_PATH):
        print(f"STOP. {REPORT_PATH} exists, so apply() already ran.")
        return None
    return run_rows(download_changes(), False, REPORT_PATH)


def rollback(dry_run: bool = False) -> Counter:
    """Undo apply(), by moving each docket it moved back to its old court."""
    rows = [
        {
            **row,
            "from_court_id": row["to_court_id"],
            "to_court_id": row["from_court_id"],
        }
        for row in read_rows(REPORT_PATH)
        if row["action"] == "moved"
    ]
    return run_rows(rows, dry_run, ROLLBACK_REPORT_PATH)


stats = run_rows(download_changes(), True, DRY_RUN_REPORT_PATH)
print("Expected: 3187 'would move', nothing skipped. If so, type: apply()")
