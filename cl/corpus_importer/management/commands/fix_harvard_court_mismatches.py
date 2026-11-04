import csv
import json
import os
import re
from collections import Counter
from datetime import date
from functools import partial
from typing import Any, NamedTuple, TypedDict

import boto3
from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.management.base import CommandError, CommandParser

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.recap.mergers import find_docket_object
from cl.search.models import SEARCH_TYPES, Docket, OpinionCluster
from cl.search.tasks import es_save_document, index_parent_and_child_docs


class CapCourtCorrection(NamedTuple):
    """A CAP court record that pairs its abbreviation with the wrong name.

    :ivar name_abbreviation: CAP's abbreviation for the court. Unlike the
    record's name, it is correct.
    :ivar court_id: The CL court the record's cases belong to.
    :ivar imported_court_id: The CL court that resolving the record's name
    gives, where the importer put its cases.
    """

    name_abbreviation: str
    court_id: str
    imported_court_id: str


# CAP court records whose `name` is another court's name, keyed by CAP court
# ID. See: https://github.com/freelawproject/courtlistener/issues/8085
CAP_COURT_CORRECTIONS: dict[int, CapCourtCorrection] = {
    10078: CapCourtCorrection("N.D. Ill.", "ilnd", "illinoised"),
    11500: CapCourtCorrection("D.D.C.", "dcd", "cadc"),
    13228: CapCourtCorrection("S.D. Ala.", "alsd", "circtsdal"),
    14721: CapCourtCorrection("D. Minn.", "mnd", "med"),
    16092: CapCourtCorrection("S.D.N.Y.", "nysd", "ilsd"),
    17176: CapCourtCorrection("W.D. Mo.", "mowd", "moed"),
    24661: CapCourtCorrection("W.D. Ark.", "arwd", "nysd"),
    25151: CapCourtCorrection("D. Mass.", "mad", "dcd"),
    25153: CapCourtCorrection("D.P.R.", "prd", "dcd"),
}

# The cases of the CAP court records in CAP_COURT_CORRECTIONS were all decided
# from August 2014 on, so older clusters can't be affected.
FIRST_AFFECTED_DATE = date(2014, 1, 1)

CAP_PATH_RE = re.compile(
    r"law\.free\.cap\.(?P<reporter_slug>[^/]+)\.(?P<volume>[^./]+)/"
    r"[^/]+\.(?P<case_id>\d+)\.json$"
)


class DocketReport(TypedDict):
    """What happened to a docket, as written to the report.

    :ivar docket_id: The docket's ID.
    :ivar docket_number: The docket's number.
    :ivar cluster_ids: The IDs of all the docket's clusters.
    :ivar court_id: The docket's court before the fix.
    :ivar corrected_court_ids: The courts its clusters' CAP records point to.
    :ivar action: Whether the docket was moved, or why it was skipped.
    :ivar possible_duplicate_id: A docket in the corrected court that the
    importer would have matched, if any.
    """

    docket_id: int
    docket_number: str
    cluster_ids: str
    court_id: str
    corrected_court_ids: str
    action: str
    possible_duplicate_id: int | None


def fetch_volume_courts(
    client: Any, reporter_slug: str, volume: str
) -> dict[int, dict[str, Any]] | None:
    """Fetch the CAP court records of a volume's cases from CAP's R2 bucket.

    :param client: An S3 client for CAP's R2 bucket.
    :param reporter_slug: The reporter's folder in the bucket.
    :param volume: The volume's folder in the bucket.
    :return: A dict that maps CAP case IDs to their court records, or None if
    the volume's metadata can't be fetched.
    """
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
        # A fetch can fail in many ways, and one volume that can't be fetched
        # shouldn't stop the run.
        logger.warning("Can't fetch %s from CAP's bucket: %s", key, e)
        return None


def get_cap_court_correction(cap_court: dict[str, Any]) -> str | None:
    """Get the CL court for a CAP court record known to have a wrong name.

    :param cap_court: The `court` object of a CAP case.
    :return: The CL court ID if the record is a known mismatch whose
    abbreviation is the expected one, otherwise None.
    """
    if (cap_court_id := cap_court.get("id")) is None:
        return None
    if not (correction := CAP_COURT_CORRECTIONS.get(cap_court_id)):
        return None
    if cap_court.get("name_abbreviation") != correction.name_abbreviation:
        # The record no longer looks like the one that was audited, so don't
        # guess its court.
        return None

    return correction.court_id


def move_docket(docket: Docket, court_id: str) -> None:
    """Move a docket to another court and update its opinions in search.

    Saving a docket updates only `court_exact` in its clusters' search
    documents, so the other court fields of the clusters and their opinions
    are rebuilt here.

    :param docket: The docket to move.
    :param court_id: The court to move it to.
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
    """Find the dockets of clusters whose CAP court record has a wrong name.

    This looks up the CAP court record of every Harvard cluster in the courts
    that the importer picked from those names. The records come from the
    volumes' metadata in CAP's R2 bucket, so the CAP_R2_* settings must be
    set, and one file is downloaded per volume. Clusters whose CAP record
    can't be found are skipped, and how many there were is logged.

    :return: A dict that maps docket IDs to the courts their clusters belong
    to, each with the IDs of those clusters.
    """
    imported_court_ids = {
        correction.imported_court_id
        for correction in CAP_COURT_CORRECTIONS.values()
    }
    clusters = (
        OpinionCluster.objects.filter(
            docket__court_id__in=imported_court_ids,
            date_filed__gte=FIRST_AFFECTED_DATE,
        )
        .exclude(filepath_json_harvard="")
        .values_list(
            "pk", "docket_id", "docket__court_id", "filepath_json_harvard"
        )
        .order_by("pk")
    )
    # Group the clusters by CAP volume, so each volume is fetched only once.
    volumes: dict[tuple[str, str], list[tuple[int, int, str, int]]] = {}
    checked = missing = 0
    for cluster_id, docket_id, docket_court_id, path in clusters.iterator():
        checked += 1
        if not (match := CAP_PATH_RE.search(path)):
            logger.warning(
                "Can't parse the CAP path of cluster %s: %s", cluster_id, path
            )
            missing += 1
            continue
        volume_key = (match["reporter_slug"], match["volume"])
        case_id = int(match["case_id"])
        volumes.setdefault(volume_key, []).append(
            (cluster_id, docket_id, docket_court_id, case_id)
        )

    client = boto3.client(
        "s3",
        endpoint_url=settings.CAP_R2_ENDPOINT_URL,
        aws_access_key_id=settings.CAP_R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.CAP_R2_SECRET_ACCESS_KEY,
    )
    dockets: dict[int, dict[str, set[int]]] = {}
    for (reporter_slug, volume), volume_clusters in volumes.items():
        cap_courts = fetch_volume_courts(client, reporter_slug, volume)
        if cap_courts is None:
            missing += len(volume_clusters)
            continue
        for cluster_id, docket_id, docket_court_id, case_id in volume_clusters:
            if (cap_court := cap_courts.get(case_id)) is None:
                logger.warning(
                    "CAP has no case %s for cluster %s.", case_id, cluster_id
                )
                missing += 1
                continue
            court_id = get_cap_court_correction(cap_court)
            # Clusters that were already moved still match their CAP record.
            if not court_id or court_id == docket_court_id:
                continue
            dockets.setdefault(docket_id, {}).setdefault(court_id, set()).add(
                cluster_id
            )

    logger.info(
        "Checked %d clusters. Couldn't find the CAP record of %d of them.",
        checked,
        missing,
    )
    return dockets


def fix_docket(
    docket_id: int, corrections: dict[str, set[int]], dry_run: bool
) -> DocketReport:
    """Move a docket to the court that its clusters' CAP records point to.

    Only dockets that hold nothing but Harvard data, and whose clusters all
    point to the same court, are moved. Moving any other docket would take
    data that belongs to its current court along with it.

    :param docket_id: The docket to fix.
    :param corrections: The courts the docket's clusters belong to, each with
    the IDs of those clusters.
    :param dry_run: Whether to only report what would happen.
    :return: What happened to the docket.
    """
    docket = Docket.objects.get(pk=docket_id)
    cluster_ids = set(docket.clusters.values_list("pk", flat=True))
    report = DocketReport(
        docket_id=docket.pk,
        docket_number=docket.docket_number or "",
        cluster_ids=" ".join(map(str, sorted(cluster_ids))),
        court_id=docket.court_id,
        corrected_court_ids=" ".join(sorted(corrections)),
        action="",
        possible_duplicate_id=None,
    )
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


def revert_docket(row: dict[str, str], dry_run: bool) -> DocketReport:
    """Move a docket that a previous run moved back to its original court.

    A docket is moved back only if it's still in the court that run moved it
    to, so changes made to it since then aren't undone.

    :param row: The docket's row in the report of the run to revert.
    :param dry_run: Whether to only report what would happen.
    :return: What happened to the docket.
    """
    report = DocketReport(
        docket_id=int(row["docket_id"]),
        docket_number=row["docket_number"],
        cluster_ids=row["cluster_ids"],
        court_id=row["court_id"],
        corrected_court_ids=row["corrected_court_ids"],
        action="",
        possible_duplicate_id=(
            int(row["possible_duplicate_id"])
            if row["possible_duplicate_id"]
            else None
        ),
    )
    if not (docket := Docket.objects.filter(pk=report["docket_id"]).first()):
        report["action"] = "skipped: docket no longer exists"
        return report
    if docket.court_id != report["corrected_court_ids"]:
        report["action"] = "skipped: docket changed court since the run"
        return report
    if dry_run:
        report["action"] = "would revert"
        return report

    move_docket(docket, report["court_id"])
    report["action"] = "reverted"
    return report


class Command(VerboseCommand):
    """Move Harvard dockets that were imported into the wrong court."""

    help = (
        "Move Harvard dockets that were imported into the wrong court because "
        "their CAP court record has another court's name. It reads CAP's "
        "metadata from CAP's R2 bucket, so the CAP_R2_* settings must be set. "
        "Run it with --dry-run and a report first, and review the report. "
        "To undo a run, pass its report to --rollback."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        """Add the command's arguments.

        :param parser: The command's argument parser.
        """
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report what would be moved without changing anything.",
        )
        parser.add_argument(
            "--report",
            help="Path of a CSV file to write what happened to each docket. "
            "Required unless --dry-run is given.",
        )
        parser.add_argument(
            "--rollback",
            metavar="REPORT",
            help="Path of the report of a previous run. Move the dockets that "
            "run moved back to their original courts, instead of fixing.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Find the affected dockets and move the ones that can be moved, or
        revert a previous run."""
        super().handle(*args, **options)
        dry_run = options["dry_run"]
        report_path = options["report"]
        rollback_path = options["rollback"]
        # The report is the only record of each docket's original court, and
        # --rollback needs it, so don't change anything without one.
        if not dry_run and not report_path:
            raise CommandError(
                "--report is required unless --dry-run is given."
            )
        if (
            rollback_path
            and report_path
            and os.path.realpath(rollback_path)
            == os.path.realpath(report_path)
        ):
            raise CommandError(
                "--report would overwrite the --rollback report."
            )

        rows_to_revert = []
        if rollback_path:
            with open(rollback_path, newline="") as rollback_file:
                rows_to_revert = [
                    row
                    for row in csv.DictReader(rollback_file)
                    if row["action"] == "moved"
                ]

        # Open the report before anything changes, so a bad path fails early,
        # and write each docket as soon as it's done, so the report survives a
        # crash.
        with open(
            report_path or os.devnull, "w", newline="", buffering=1
        ) as report_file:
            writer = csv.DictWriter(
                report_file, fieldnames=list(DocketReport.__annotations__)
            )
            writer.writeheader()

            if rollback_path:
                jobs = [
                    partial(revert_docket, row, dry_run)
                    for row in rows_to_revert
                ]
            else:
                jobs = [
                    partial(fix_docket, docket_id, corrections, dry_run)
                    for docket_id, corrections in find_dockets_to_fix().items()
                ]
            if not jobs:
                logger.info("No dockets to change. Nothing to do.")
                return

            # Moving a docket enqueues ES updates on the ETL queue, so
            # throttle against that queue to avoid flooding it.
            throttle = CeleryThrottle(
                queue_name=settings.CELERY_ETL_TASK_QUEUE
            )
            actions: Counter[str] = Counter()
            for job in jobs:
                if not dry_run:
                    throttle.maybe_wait()
                report = job()
                logger.info(
                    "Docket %s (%s -> %s): %s",
                    report["docket_id"],
                    report["court_id"],
                    report["corrected_court_ids"],
                    report["action"],
                )
                writer.writerow(report)
                actions[report["action"]] += 1

            logger.info("Done: %s", dict(actions))
