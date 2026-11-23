"""Remove disposition text and apply other fixes to docket numbers."""

import csv
import json
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, TypedDict

from django.conf import settings
from django.core.management.base import CommandParser
from django.db import transaction

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.docket_number_cleaner import court_map, get_clean_methods
from cl.search.documents import OpinionClusterDocument
from cl.search.models import SEARCH_TYPES, Docket, OpinionCluster
from cl.search.tasks import es_save_document, index_parent_and_child_docs

# Corrections that only split the docket number from the disposition text
# appended to it. The others were checked one at a time against a source.
FIELD_SEPARATION = "same_lineage_field_separation"


@dataclass
class DocketNumberCorrection:
    """A correction to the docket number of a docket.

    :ivar record_key: The key of the correction.
    :ivar docket_id: The docket's ID.
    :ivar evidence_class: How the correction was made.
    :ivar before: The wrong docket number.
    :ivar after: The corrected docket number.
    """

    record_key: str
    docket_id: int
    evidence_class: str
    before: str
    after: str


class CorrectionReport(TypedDict):
    """What happened to a correction, as written to the report.

    :ivar record_key: The key of the correction.
    :ivar docket_id: The ID of the corrected docket.
    :ivar court_id: The docket's court.
    :ivar evidence_class: How the correction was made.
    :ivar before: The wrong docket number.
    :ivar after: The corrected docket number, in the court's format.
    :ivar current: The docket number found in the database before the
    correction.
    :ivar action: Whether the correction was applied, or why it was skipped.
    """

    record_key: str
    docket_id: int
    court_id: str
    evidence_class: str
    before: str
    after: str
    current: str
    action: str


def read_jsonl(path: str) -> Iterator[dict[str, Any]]:
    """Read the records of a JSONL file one at a time.

    :param path: The path of the file.
    :return: An iterator over the file's records.
    """
    with Path(path).open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def read_corrections(path: str) -> list[DocketNumberCorrection]:
    """Read the corrections of the package's dockets file.

    :param path: The path of dockets.jsonl.
    :return: The corrections, one per docket.
    """
    return [
        DocketNumberCorrection(
            record_key=record["record_key"],
            docket_id=record["docket_id"],
            evidence_class=record["evidence_class"],
            before=record["before"] or "",
            after=record["after"] or "",
        )
        for record in read_jsonl(path)
    ]


def read_applied_corrections(path: str) -> list[CorrectionReport]:
    """Read the applied corrections of a report from an earlier run.

    :param path: The path of the report.
    :return: The report rows of the applied corrections.
    """
    with Path(path).open(newline="") as f:
        return [
            CorrectionReport(**{**row, "docket_id": int(row["docket_id"])})
            for row in csv.DictReader(f)
            if row["action"] == "applied"
        ]


def reindex_last_changed_docket(report_path: Path, queue: str) -> None:
    """Index the clusters and opinions of the last docket an earlier run changed.

    Search updates run after a docket's change commits, so a run stopped at
    that point leaves the docket's documents stale, and a new run skips the
    docket because it's already changed. Only the last docket can be in that
    state. Indexing it again when its update did finish is harmless.

    :param report_path: The path of the earlier run's report.
    :param queue: The Celery queue to index on.
    """
    if not report_path.exists():
        return
    with report_path.open(newline="") as f:
        changed_docket_ids = [
            row["docket_id"]
            for row in csv.DictReader(f)
            if row["action"] in ("applied", "rolled back")
        ]
    if not changed_docket_ids:
        return
    cluster_ids = list(
        OpinionCluster.objects.filter(
            docket_id=changed_docket_ids[-1]
        ).values_list("pk", flat=True)
    )
    for cluster_id in cluster_ids:
        # index_parent_and_child_docs leaves an existing cluster document as
        # it is, so save the cluster document separately.
        es_save_document.si(
            cluster_id,
            "search.OpinionCluster",
            OpinionClusterDocument.__name__,
            skip_percolator_request=True,
        ).set(queue=queue).apply_async()
    if cluster_ids:
        index_parent_and_child_docs.si(cluster_ids, SEARCH_TYPES.OPINION).set(
            queue=queue
        ).apply_async()


def only_removes_disposition(before: str, after: str) -> bool:
    """Check that a correction only removes the prefix and disposition.

    For example, "No. 22908.  Reversed and remanded." -> "22908".

    :param before: The wrong docket number.
    :param after: The corrected docket number.
    :return: Whether the corrected number is the wrong one without its prefix
    and disposition.
    """
    pattern = rf"nos?\.\s+{re.escape(after)}\.\s+[a-z ]+\."
    return bool(re.fullmatch(pattern, before, flags=re.IGNORECASE))


def format_for_court(docket_number: str, court_id: str) -> str:
    """Format a docket number the way docket numbers of its court are cleaned.

    Courts whose docket numbers aren't cleaned keep the number as it is.

    :param docket_number: The docket number.
    :param court_id: The docket's court.
    :return: The formatted docket number, or an empty string if it isn't a
    docket number of the court.
    """
    if not (court_type := court_map.get(court_id)):
        return docket_number
    prelim_clean, regex_clean = get_clean_methods(court_type)
    return regex_clean(prelim_clean(docket_number))


def fix_docket_number(
    correction: DocketNumberCorrection, dry_run: bool
) -> CorrectionReport:
    """Correct the docket number of a docket if it's still wrong.

    A docket number that changed since the package was made is left alone.
    docket_number_raw is left alone too: it's the number as the source
    printed it, and scrapers find dockets by it.

    :param correction: The correction.
    :param dry_run: Whether to only report what would happen.
    :return: What happened to the correction.
    """
    report = CorrectionReport(
        record_key=correction.record_key,
        docket_id=correction.docket_id,
        court_id="",
        evidence_class=correction.evidence_class,
        before=correction.before,
        after=correction.after,
        current="",
        action="",
    )
    if (
        correction.evidence_class == FIELD_SEPARATION
        and not only_removes_disposition(correction.before, correction.after)
    ):
        report["action"] = "skipped: correction changes more than the format"
        return report
    docket = (
        Docket.objects.select_for_update()
        .filter(pk=correction.docket_id)
        .first()
    )
    if docket is None:
        report["action"] = "skipped: docket not found"
        return report

    report["court_id"] = docket.court_id
    after = report["after"] = format_for_court(
        correction.after, docket.court_id
    )
    if not after:
        report["action"] = "skipped: not a docket number of the court"
        return report
    current = report["current"] = docket.docket_number or ""
    if current == after:
        report["action"] = "skipped: already corrected"
        return report
    if current != correction.before:
        report["action"] = "skipped: value changed since the package was made"
        return report

    if dry_run:
        report["action"] = "would apply"
        return report
    docket.docket_number = after
    docket.save(update_fields=["docket_number", "date_modified"])
    report["action"] = "applied"
    return report


def rollback_docket_number(
    applied: CorrectionReport, dry_run: bool
) -> CorrectionReport:
    """Put back the wrong docket number of a correction applied earlier.

    A docket number that changed since the correction was applied is left
    alone.

    :param applied: The report row of the applied correction.
    :param dry_run: Whether to only report what would happen.
    :return: What happened to the correction.
    """
    report = CorrectionReport(**{**applied, "current": "", "action": ""})
    docket = (
        Docket.objects.select_for_update()
        .filter(pk=applied["docket_id"])
        .first()
    )
    if docket is None:
        report["action"] = "skipped: docket not found"
        return report

    current = report["current"] = docket.docket_number or ""
    if current == applied["before"]:
        report["action"] = "skipped: already rolled back"
        return report
    if current != applied["after"]:
        report["action"] = (
            "skipped: value changed since the correction was applied"
        )
        return report

    if dry_run:
        report["action"] = "would roll back"
        return report
    docket.docket_number = applied["before"]
    docket.save(update_fields=["docket_number", "date_modified"])
    report["action"] = "rolled back"
    return report


class Command(VerboseCommand):
    """Apply a package of docket number corrections."""

    help = (
        "Apply a package of corrections to docket numbers, most of which "
        "have the disposition appended. Pass the package's dockets.jsonl. "
        "Only docket numbers that still match the package's 'before' values "
        "are changed. Run it with --dry-run and a report first, and review "
        "the report. After a crash, run it again with the same --report, so "
        "it can repair the search documents of the last changed docket. Pass "
        "a report to --rollback to put back the docket numbers it applied."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        """Add the command's arguments.

        :param parser: The command's argument parser.
        """
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument(
            "--dockets",
            help="Path of the package's dockets.jsonl file.",
        )
        source.add_argument(
            "--rollback",
            help="Path of a report from an earlier run. Its applied "
            "corrections are rolled back, unless the docket number changed since.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report what would be changed without changing anything.",
        )
        parser.add_argument(
            "--report",
            required=True,
            help="Path of a CSV file to append what happened to each "
            "correction to. It's what --rollback reads.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Apply the corrections that still apply, or roll back applied ones."""
        super().handle(*args, **options)

        # Read the input before anything changes, so a bad file fails early.
        if options["rollback"]:
            fixes = [
                partial(rollback_docket_number, row)
                for row in read_applied_corrections(options["rollback"])
            ]
        else:
            fixes = [
                partial(fix_docket_number, correction)
                for correction in read_corrections(options["dockets"])
            ]

        if not options["dry_run"]:
            reindex_last_changed_docket(
                Path(options["report"]), settings.CELERY_ETL_TASK_QUEUE
            )

        # Append, so a run after a crash keeps the rows of the dockets the
        # crashed run changed.
        with Path(options["report"]).open(
            "a", newline="", buffering=1
        ) as report_file:
            writer = csv.DictWriter(
                report_file, fieldnames=list(CorrectionReport.__annotations__)
            )
            if report_file.tell() == 0:
                writer.writeheader()

            # Each saved docket queues search index updates on this queue.
            throttle = CeleryThrottle(
                queue_name=settings.CELERY_ETL_TASK_QUEUE
            )
            actions: Counter[tuple[str, str]] = Counter()
            for fix in fixes:
                if not options["dry_run"]:
                    throttle.maybe_wait()
                # Write the row before the change commits, so a crash can't
                # leave a changed docket out of the report that --rollback
                # reads. A row for a change that didn't commit is harmless.
                with transaction.atomic():
                    report = fix(dry_run=options["dry_run"])
                    writer.writerow(report)
                logger.info(
                    "Docket %s (%s -> %s): %s",
                    report["docket_id"],
                    report["before"],
                    report["after"],
                    report["action"],
                )
                actions[(report["evidence_class"], report["action"])] += 1

            for (evidence_class, action), count in sorted(actions.items()):
                logger.info("%s: %s: %d", evidence_class, action, count)
