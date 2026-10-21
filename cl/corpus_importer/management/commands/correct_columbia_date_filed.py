"""Correct OpinionCluster.date_filed values that the 2016 Columbia import got
wrong (issue #8146), driven by a two-way CSV.

The CSV has one row per cluster with the columns:

    cluster_id,date_filed_old,date_filed_new,basis

Running the command moves date_filed_old to date_filed_new. Running it with
--revert moves date_filed_new back to date_filed_old. In both directions a row
is skipped when the stored value no longer matches the expected starting
value, so the file can be applied and reverted safely at any later time, and
re-running after a partial run only touches the rows that are still pending.

The whole file is parsed and validated before any write, so a malformed row
rejects the file instead of stopping a run half way.

Clusters are saved through the ORM so the Elasticsearch signals update the
related documents.
"""

import csv
import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Any

from django.core.management.base import (
    BaseCommand,
    CommandError,
    CommandParser,
)

from cl.search.cluster_sources import ClusterSources
from cl.search.models import OpinionCluster

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("cluster_id", "date_filed_old", "date_filed_new")


@dataclass
class Correction:
    """One validated CSV row."""

    cluster_id: int
    date_filed_old: date
    date_filed_new: date


@dataclass
class Stats:
    """Counters for one run of the command."""

    rows: int = 0
    updated: int = 0
    already_applied: int = 0
    missing: int = 0
    stale: int = 0
    not_columbia: int = 0


def load_rows(filepath: str) -> list[Correction]:
    """Read and validate the corrections CSV.

    Every row is parsed up front. The first malformed row raises CommandError
    with its line number, before anything is written to the database.

    :param filepath: Path to the CSV file.
    :return: The validated rows, in file order.
    """
    corrections = []
    # utf-8-sig drops a BOM that would otherwise corrupt the first header.
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        if missing := [c for c in REQUIRED_COLUMNS if c not in header]:
            raise CommandError(
                f"CSV is missing required column(s): {', '.join(missing)}"
            )
        for row in reader:
            try:
                correction = Correction(
                    cluster_id=int(row["cluster_id"]),
                    date_filed_old=date.fromisoformat(row["date_filed_old"]),
                    date_filed_new=date.fromisoformat(row["date_filed_new"]),
                )
            except (TypeError, ValueError) as e:
                raise CommandError(
                    f"Invalid row at line {reader.line_num}: {row} ({e})"
                ) from e
            if correction.date_filed_old == correction.date_filed_new:
                raise CommandError(
                    f"Row at line {reader.line_num} has identical old and "
                    f"new dates: {row}"
                )
            corrections.append(correction)
    return corrections


def apply_row(
    correction: Correction, revert: bool, dry_run: bool, stats: Stats
) -> bool:
    """Apply one correction to its cluster.

    :param correction: The validated CSV row.
    :param revert: Move date_filed_new back to date_filed_old.
    :param dry_run: Log what would change and do not save.
    :param stats: Counters to update.
    :return: True if the cluster was (or would be) updated.
    """
    expected, target = correction.date_filed_old, correction.date_filed_new
    if revert:
        expected, target = target, expected
    cluster_id = correction.cluster_id

    cluster = OpinionCluster.objects.filter(pk=cluster_id).first()
    if cluster is None:
        logger.warning("Cluster %s not found, skipping.", cluster_id)
        stats.missing += 1
        return False

    if ClusterSources.COLUMBIA_ARCHIVE not in cluster.source:
        logger.warning(
            "Cluster %s has source %s, not a Columbia cluster, skipping.",
            cluster_id,
            cluster.source,
        )
        stats.not_columbia += 1
        return False

    if cluster.date_filed == target:
        logger.info(
            "Cluster %s already has date_filed %s, skipping.",
            cluster_id,
            target,
        )
        stats.already_applied += 1
        return False

    if cluster.date_filed != expected:
        logger.warning(
            "Cluster %s has date_filed %s, expected %s, skipping.",
            cluster_id,
            cluster.date_filed,
            expected,
        )
        stats.stale += 1
        return False

    logger.info(
        "Cluster %s: date_filed %s -> %s%s",
        cluster_id,
        expected,
        target,
        " (dry run)" if dry_run else "",
    )
    stats.updated += 1
    if dry_run:
        return True

    cluster.date_filed = target
    # update_fields keeps the write small; the ES signal processor still sees
    # the change through the field tracker.
    cluster.save(update_fields=["date_filed", "date_modified"])
    return True


def process_csv(
    filepath: str,
    revert: bool,
    dry_run: bool,
    delay: float,
    start_row: int,
    limit: int | None,
) -> Stats:
    """Apply (or revert) every row of the corrections CSV.

    :param filepath: Path to the CSV file.
    :param revert: Move date_filed_new back to date_filed_old.
    :param dry_run: Log what would change and do not save.
    :param delay: Seconds to wait after each saved cluster.
    :param start_row: First row to process (zero based, inclusive).
    :param limit: Maximum number of rows to process.
    :return: The run counters. In a dry run, `updated` counts the rows that
    would be updated.
    """
    rows = load_rows(filepath)[start_row:]
    if limit is not None:
        rows = rows[:limit]

    stats = Stats()
    for correction in rows:
        stats.rows += 1
        changed = apply_row(correction, revert, dry_run, stats)
        if changed and not dry_run:
            # Throttle so we do not flood the ES indexing queue.
            time.sleep(delay)

    verb = "would be reverted" if revert else "would be updated"
    if not dry_run:
        verb = "reverted" if revert else "updated"
    logger.info("Rows processed: %s", stats.rows)
    logger.info("Clusters %s: %s", verb, stats.updated)
    logger.info("Skipped, already at target date: %s", stats.already_applied)
    logger.info("Skipped, stored date did not match: %s", stats.stale)
    logger.info("Skipped, not a Columbia cluster: %s", stats.not_columbia)
    logger.info("Skipped, cluster not found: %s", stats.missing)
    return stats


class Command(BaseCommand):
    """Apply or revert Columbia date_filed corrections from a two-way CSV."""

    help = (
        "Correct Columbia date_filed values from a two-way CSV "
        "(cluster_id, date_filed_old, date_filed_new). Use --revert to "
        "restore the old values with the same file."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        """Register the command options.

        :param parser: The argument parser to extend.
        """
        parser.add_argument(
            "--filepath",
            type=str,
            required=True,
            help="Path to the corrections CSV.",
        )
        parser.add_argument(
            "--revert",
            action="store_true",
            help="Move date_filed_new back to date_filed_old.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without saving anything.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.1,
            help="Seconds to wait after each updated cluster (floats allowed).",
        )
        parser.add_argument(
            "--start-row",
            type=int,
            default=0,
            help="First CSV row to process (zero based, inclusive).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of CSV rows to process.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the corrections with the parsed options."""
        process_csv(
            filepath=options["filepath"],
            revert=options["revert"],
            dry_run=options["dry_run"],
            delay=options["delay"],
            start_row=options["start_row"],
            limit=options["limit"],
        )
