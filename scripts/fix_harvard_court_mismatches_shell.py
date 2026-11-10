# Issue #8085. Paste this whole file into `python manage.py shell`.
# The paste only runs a dry run. It changes nothing, but it reads CAP metadata
# from CAP's R2 bucket (one file per volume), so it takes a few minutes.
# If the dry run output matches the expected line, type: apply()
# apply() moves the dockets and queues Elasticsearch updates on the Celery ETL
# queue. It writes REPORT_PATH, which is the only record of the old courts.
# Keep that file: rollback() needs it to undo apply().
import csv
import json
import os
import re
from collections import Counter
from datetime import date
from typing import Any

import boto3
from asgiref.sync import async_to_sync
from django.conf import settings

from cl.lib.celery_utils import CeleryThrottle
from cl.recap.mergers import find_docket_object
from cl.search.models import SEARCH_TYPES, Docket, OpinionCluster
from cl.search.tasks import es_save_document, index_parent_and_child_docs

DRY_RUN_REPORT_PATH = "/tmp/8085-dry-run.csv"
REPORT_PATH = "/tmp/8085-run.csv"
ROLLBACK_REPORT_PATH = "/tmp/8085-rollback.csv"
# CAP court records whose name is another court's name, keyed by CAP court ID:
# (CAP abbreviation, correct CL court, CL court the importer used).
CAP_COURT_CORRECTIONS = {
    10078: ("N.D. Ill.", "ilnd", "illinoised"),
    11500: ("D.D.C.", "dcd", "cadc"),
    13228: ("S.D. Ala.", "alsd", "circtsdal"),
    14721: ("D. Minn.", "mnd", "med"),
    16092: ("S.D.N.Y.", "nysd", "ilsd"),
    17176: ("W.D. Mo.", "mowd", "moed"),
    24661: ("W.D. Ark.", "arwd", "nysd"),
    25151: ("D. Mass.", "mad", "dcd"),
    25153: ("D.P.R.", "prd", "dcd"),
}
# All cases of these CAP records are from August 2014 on.
FIRST_AFFECTED_DATE = date(2014, 1, 1)
CAP_PATH_RE = re.compile(
    r"law\.free\.cap\.(?P<reporter_slug>[^/]+)\.(?P<volume>[^./]+)/"
    r"[^/]+\.(?P<case_id>\d+)\.json$"
)
REPORT_COLUMNS = [
    "docket_id",
    "docket_number",
    "cluster_ids",
    "court_id",
    "corrected_court_ids",
    "action",
    "possible_duplicate_id",
]


def fetch_volume_courts(
    client: Any, reporter_slug: str, volume: str
) -> dict[int, dict[str, Any]] | None:
    """Map a CAP volume's case IDs to their court records, or None on error."""
    key = f"{reporter_slug}/{volume}/CasesMetadata.json"
    try:
        response = client.get_object(
            Bucket=settings.CAP_R2_BUCKET_NAME, Key=key
        )
        return {
            case["id"]: case.get("court", {})
            for case in json.loads(response["Body"].read())
        }
    except Exception as e:
        # One volume that can't be fetched shouldn't stop the run.
        print(f"Can't fetch {key}: {e}")
        return None


def get_correct_court(cap_court: dict[str, Any]) -> str | None:
    """Return the correct CL court for a known bad CAP court record."""
    if not (correction := CAP_COURT_CORRECTIONS.get(cap_court.get("id"))):
        return None
    # A record that no longer looks like the audited one is left alone.
    if cap_court.get("name_abbreviation") != correction[0]:
        return None
    return correction[1]


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


def find_dockets_to_fix() -> dict[int, dict[str, set[int]]]:
    """Find dockets whose Harvard clusters have a bad CAP court record.

    :return: docket ID -> {correct court: IDs of the clusters that say so}.
    """
    clusters = (
        OpinionCluster.objects.filter(
            docket__court_id__in={
                c[2] for c in CAP_COURT_CORRECTIONS.values()
            },
            date_filed__gte=FIRST_AFFECTED_DATE,
        )
        .exclude(filepath_json_harvard="")
        .values_list(
            "pk", "docket_id", "docket__court_id", "filepath_json_harvard"
        )
        .order_by("pk")
    )
    # Group by CAP volume, so each volume is fetched once.
    volumes: dict[tuple[str, str], list[tuple[int, int, str, int]]] = {}
    checked = missing = 0
    for cluster_id, docket_id, docket_court_id, path in clusters.iterator():
        checked += 1
        if not (match := CAP_PATH_RE.search(path)):
            missing += 1
            continue
        volumes.setdefault(
            (match["reporter_slug"], match["volume"]), []
        ).append(
            (cluster_id, docket_id, docket_court_id, int(match["case_id"]))
        )
    client = boto3.client(
        "s3",
        endpoint_url=settings.CAP_R2_ENDPOINT_URL,
        aws_access_key_id=settings.CAP_R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.CAP_R2_SECRET_ACCESS_KEY,
    )
    dockets: dict[int, dict[str, set[int]]] = {}
    for (reporter_slug, volume), volume_clusters in volumes.items():
        if (
            cap_courts := fetch_volume_courts(client, reporter_slug, volume)
        ) is None:
            missing += len(volume_clusters)
            continue
        for cluster_id, docket_id, docket_court_id, case_id in volume_clusters:
            if (cap_court := cap_courts.get(case_id)) is None:
                missing += 1
                continue
            court_id = get_correct_court(cap_court)
            # Clusters that were already moved still match their CAP record.
            if not court_id or court_id == docket_court_id:
                continue
            dockets.setdefault(docket_id, {}).setdefault(court_id, set()).add(
                cluster_id
            )
    print(f"Checked {checked} clusters, {missing} without a CAP record.")
    return dockets


def fix_docket(
    docket_id: int, corrections: dict[str, set[int]], dry_run: bool
) -> dict[str, Any]:
    """Move a docket to its correct court, or say why it was skipped.

    Only dockets with nothing but Harvard data, whose clusters all point to
    one court, are moved. Others would take data of their court with them.
    """
    docket = Docket.objects.get(pk=docket_id)
    cluster_ids = set(docket.clusters.values_list("pk", flat=True))
    report = {
        "docket_id": docket.pk,
        "docket_number": docket.docket_number or "",
        "cluster_ids": " ".join(map(str, sorted(cluster_ids))),
        "court_id": docket.court_id,
        "corrected_court_ids": " ".join(sorted(corrections)),
        "action": "",
        "possible_duplicate_id": None,
    }
    if len(corrections) > 1:
        report["action"] = "skipped: clusters belong to different courts"
        return report
    court_id, corrected_cluster_ids = corrections.popitem()
    if docket.source != Docket.HARVARD:
        report["action"] = "skipped: docket has data from other sources"
        return report
    if corrected_cluster_ids != cluster_ids:
        report["action"] = (
            "skipped: docket has clusters that weren't confirmed"
        )
        return report
    if docket.docket_number and (
        duplicate := async_to_sync(find_docket_object)(
            court_id,
            None,
            docket.docket_number,
            None,
            None,
            None,
            allow_create=False,
        )
    ):
        report["possible_duplicate_id"] = duplicate.pk
    if dry_run:
        report["action"] = "would move"
        return report
    move_docket(docket, court_id)
    report["action"] = "moved"
    return report


def revert_docket(row: dict[str, str], dry_run: bool) -> dict[str, Any]:
    """Move a docket that apply() moved back to its old court.

    A docket that changed court since apply() is left alone.
    """
    report = {**row, "action": ""}
    if not (docket := Docket.objects.filter(pk=int(row["docket_id"])).first()):
        report["action"] = "skipped: docket no longer exists"
        return report
    if docket.court_id != row["corrected_court_ids"]:
        report["action"] = "skipped: docket changed court since the run"
        return report
    if dry_run:
        report["action"] = "would revert"
        return report
    move_docket(docket, row["court_id"])
    report["action"] = "reverted"
    return report


def run_jobs(jobs: list, dry_run: bool, report_path: str) -> Counter:
    """Run each job and write its row to the report as soon as it is done."""
    # Moves queue Elasticsearch tasks, so wait when the ETL queue is full.
    throttle = CeleryThrottle(queue_name=settings.CELERY_ETL_TASK_QUEUE)
    actions: Counter[str] = Counter()
    with open(report_path, "w", newline="", buffering=1) as report_file:
        writer = csv.DictWriter(report_file, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        for i, (job, args) in enumerate(jobs, start=1):
            if not dry_run:
                throttle.maybe_wait()
            report = job(*args, dry_run)
            writer.writerow(report)
            actions[report["action"]] += 1
            if i % 250 == 0:
                print(f"{i} of {len(jobs)}")
    print("DRY RUN, nothing changed." if dry_run else "DONE.")
    print(f"Report: {report_path}")
    print(dict(actions))
    return actions


def run(dry_run: bool) -> Counter:
    """Find the affected dockets and move the ones that can be moved."""
    jobs = [
        (fix_docket, (docket_id, corrections))
        for docket_id, corrections in find_dockets_to_fix().items()
    ]
    return run_jobs(
        jobs, dry_run, DRY_RUN_REPORT_PATH if dry_run else REPORT_PATH
    )


def apply() -> Counter | None:
    """Move the dockets for real.

    It refuses to run twice, because a second run would overwrite the report
    that rollback() needs.
    """
    if os.path.exists(REPORT_PATH):
        print(f"STOP. {REPORT_PATH} exists, so apply() already ran.")
        return None
    return run(dry_run=False)


def rollback(dry_run: bool = False) -> Counter:
    """Undo apply(), using the report it wrote to REPORT_PATH."""
    with open(REPORT_PATH, newline="") as f:
        rows = [row for row in csv.DictReader(f) if row["action"] == "moved"]
    jobs = [(revert_docket, (row,)) for row in rows]
    return run_jobs(jobs, dry_run, ROLLBACK_REPORT_PATH)


stats = run(dry_run=True)
print("Expected: about 3187 'would move', 66 skipped. If so, type: apply()")
