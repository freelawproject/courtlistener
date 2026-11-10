# Issue #8146. Paste this whole file into `python manage.py shell`.
# The paste only runs a dry run. It writes nothing and downloads only the CSV.
# If the dry run output matches the expected line, type: apply()
# To undo apply(), type: revert()
# apply() and revert() take about 1 hour and queue Elasticsearch updates on
# Celery for every changed cluster.
import csv
import io
import time
from datetime import date

import httpx

from cl.search.cluster_sources import ClusterSources
from cl.search.models import OpinionCluster

CSV_URL = (
    "https://github.com/user-attachments/files/33788709/"
    "columbia_date_filed_corrections_v3.csv"
)
# Seconds to wait after each save, so the Elasticsearch queue keeps up.
DELAY = 0.1


def load_rows() -> list[tuple[int, date, date]]:
    """Download and validate the whole CSV before any row runs.

    :return: (cluster_id, date_filed_old, date_filed_new) for each row.
    """
    response = httpx.get(CSV_URL, follow_redirects=True, timeout=60)
    response.raise_for_status()
    # utf-8-sig drops a BOM that would corrupt the first header.
    reader = csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))
    rows = []
    for n, row in enumerate(reader, start=2):
        try:
            old = date.fromisoformat(row["date_filed_old"])
            new = date.fromisoformat(row["date_filed_new"])
            rows.append((int(row["cluster_id"]), old, new))
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"CSV line {n}: {row} ({e})") from e
        if old == new:
            raise ValueError(f"CSV line {n}: old and new dates are equal")
    return rows


def apply_row(
    cluster_id: int, expected: date, target: date, dry_run: bool
) -> str:
    """Move one cluster's date_filed from expected to target.

    A cluster whose date is not the expected one is skipped, so a run can be
    repeated or reverted safely.

    :return: What happened to the cluster.
    """
    cluster = OpinionCluster.objects.filter(pk=cluster_id).first()
    if not cluster:
        return "missing"
    if ClusterSources.COLUMBIA_ARCHIVE not in cluster.source:
        return "not_columbia"
    if cluster.date_filed == target:
        return "already_applied"
    if cluster.date_filed != expected:
        return "stale"
    if not dry_run:
        cluster.date_filed = target
        # save(), not update(), so the signals update Elasticsearch.
        cluster.save(update_fields=["date_filed", "date_modified"])
        time.sleep(DELAY)
    return "updated"


def run(dry_run: bool, undo: bool = False) -> dict[str, int]:
    """Apply, or with undo=True revert, every CSV row."""
    rows = load_rows()
    stats = dict.fromkeys(
        ["updated", "already_applied", "stale", "not_columbia", "missing"], 0
    )
    for i, (cluster_id, old, new) in enumerate(rows, start=1):
        expected, target = (new, old) if undo else (old, new)
        stats[apply_row(cluster_id, expected, target, dry_run)] += 1
        if i % 1000 == 0:
            print(f"{i} of {len(rows)}")
    print("DRY RUN, nothing written." if dry_run else "DONE.")
    print(stats)
    return stats


def apply() -> dict[str, int]:
    """Correct the dates for real."""
    return run(dry_run=False)


def revert() -> dict[str, int]:
    """Undo apply(): put the old dates back."""
    return run(dry_run=False, undo=True)


stats = run(dry_run=True)
print("Expected: updated=27119, all else 0. If so, type: apply()")
