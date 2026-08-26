"""Merge a jkent scrape run into CourtListener.

    manage.py load_state_scrape nycoa nycourts_gov/2026-08-08.db \\
        --ingest-throttle 100 --extraction-throttle 100

We report errors to Sentry fingerprinted by the loader and phase. We track
merges/extractions as they are in flight so that we can attempt to reconcile
successes, errors, and expectations after a load has completed to find dropped
steps.

A load that dies partway can be picked up with `--auto-resume`, which starts
from the last row the previous load of the same run database checkpointed. The
checkpoint is dropped once a load reaches the end.

Add a court by registering its `JKentScrapeLoader` subclass in
`cl.corpus_importer.state.registry`.
"""

import logging
from typing import Any

from django.core.management.base import (
    BaseCommand,
    CommandError,
    CommandParser,
)

from cl.corpus_importer.state.loader import (
    DEFAULT_IN_FLIGHT_TIME,
    DEFAULT_VERIFY_TIMEOUT,
    LoadReport,
    WaitOutcome,
)
from cl.corpus_importer.state.registry import LOADERS
from cl.corpus_importer.state.run_db import (
    RunDatabaseUnavailable,
    downloaded_run_database,
)
from cl.lib.indexing_utils import get_last_parent_document_id_processed

logger = logging.getLogger(__name__)

DEFAULT_THROTTLE = 5


def compose_redis_key(loader: str, database: str) -> str:
    """Compose the Redis key a load's checkpoint and ledger hang off.

    :param loader: The `LOADERS` name the load ran under.
    :param database: The run database's path within the storage bucket.
    :return: The Redis key.
    """
    return f"state_scrape_load:{loader}:{database}"


class Command(BaseCommand):
    help = "Merge a jkent scrape run database into CourtListener."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register the command's arguments."""
        parser.add_argument(
            "loader",
            choices=sorted(LOADERS),
            help="Which court's run database this is.",
        )
        parser.add_argument(
            "database",
            help=(
                "The run database's path within the storage bucket, such as "
                "nycourts_gov/2026-08-08.db."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Stop after this many dockets.",
        )
        parser.add_argument(
            "--ingest-queue",
            default="celery",
            help="The celery queue to merge dockets on.",
        )
        parser.add_argument(
            "--ingest-throttle",
            type=int,
            default=DEFAULT_THROTTLE,
            help=(
                "Hold the merge queue to roughly this many tasks, waiting for "
                "the workers to catch up when it runs longer. The default "
                f"({DEFAULT_THROTTLE}) is the one the SCOTUS, Texas and "
                "Florida imports use. Raise it for a backfill, where "
                "throughput matters more than leaving the queue clear. Zero "
                "turns throttling off and dispatches as fast as the run "
                "database can be read: each message carries a whole docket, "
                "around 7KB for a busy one, so an unthrottled run of a "
                "hundred thousand leaves the better part of a gigabyte in the "
                "broker until the workers drain it."
            ),
        )
        parser.add_argument(
            "--skip-extraction",
            action="store_true",
            help=(
                "Do not dispatch text extraction for the documents the load "
                "writes. For a large backfill, where "
                "`state_document_download --skip-download` paces the same "
                "work against the queue."
            ),
        )
        parser.add_argument(
            "--extraction-queue",
            default="celery",
            help="The celery queue to extract documents on.",
        )
        parser.add_argument(
            "--extraction-throttle",
            type=int,
            default=DEFAULT_THROTTLE,
            help=(
                "Hold the extraction queue to roughly this many tasks the "
                "same way. Merges dispatch their own extraction, so throttling "
                "the merge queue paces this one indirectly; this holds it to a "
                "rate of its own on top of that. Zero turns it off."
            ),
        )
        parser.add_argument(
            "--db-delay",
            type=float,
            default=0.0,
            help=(
                "Seconds to wait after each docket, to keep a long load from "
                "filling the queue faster than the workers drain it. Zero, "
                "the default, runs flat out."
            ),
        )
        parser.add_argument(
            "--start-row",
            type=int,
            default=0,
            help=(
                "Skip this many dockets, for resuming a load by hand. Cannot "
                "be combined with --auto-resume."
            ),
        )
        parser.add_argument(
            "--auto-resume",
            action="store_true",
            help=(
                "Start from the row the last load of this run database "
                "checkpointed, rather than from the beginning. A load that "
                "ran to the end leaves no checkpoint, so this starts such a "
                "run over."
            ),
        )
        parser.add_argument(
            "--skip-verification",
            action="store_true",
            help=(
                "Return as soon as every docket has been dispatched, rather "
                "than waiting to see what the merges did. Nothing then "
                "reports the dockets celery dropped, so prefer "
                "--verify-timeout for a load you only want to wait on for a "
                "while."
            ),
        )
        parser.add_argument(
            "--verify-only",
            action="store_true",
            help=(
                "Skip the load and check up on one that already ran, reading "
                "its ledger out of Redis. For picking up a run that hit "
                "--verify-timeout with its queues still moving. Needs the same "
                "loader and database arguments, since those name the ledger, "
                "but never fetches the run database itself."
            ),
        )
        parser.add_argument(
            "--in-flight-time",
            type=float,
            default=DEFAULT_IN_FLIGHT_TIME,
            help=(
                "Seconds a queue's outstanding count has to hold steady before "
                "the load concludes the rest is never coming. This is what "
                "separates work that was lost from work merely queued behind "
                "something else, so it has to be longer than the slowest "
                "legitimate step -- a merge's whole retry envelope, or the "
                "slowest extraction job -- or slow work gets reported as lost."
            ),
        )
        parser.add_argument(
            "--verify-timeout",
            type=float,
            default=DEFAULT_VERIFY_TIMEOUT,
            help=(
                "Seconds to wait on a queue whose count is still coming down "
                "before giving up. Applies per phase, so extraction is not "
                "starved by merges that ran long, and the clock starts when "
                "each wait does rather than when dispatching did. Hitting it "
                "is not a failure -- the queue was working and the load "
                "stopped watching -- so nothing is reported as lost and "
                "--verify-only can settle it later."
            ),
        )

    def handle(
        self,
        *args: Any,
        loader: str,
        database: str,
        limit: int | None,
        ingest_queue: str,
        ingest_throttle: int,
        skip_extraction: bool,
        extraction_queue: str,
        extraction_throttle: int,
        db_delay: float,
        start_row: int,
        auto_resume: bool,
        skip_verification: bool,
        verify_only: bool,
        in_flight_time: float,
        verify_timeout: float,
        **options: Any,
    ) -> None:
        """Download the run database, dispatch its merges, and report on them.

        :param loader: The `LOADERS` name of the court's loader.
        :param database: The run database's path within the storage bucket.
        :param limit: Stop after this many dockets.
        :param ingest_queue: The celery queue to merge dockets on.
        :param ingest_throttle: Tasks to hold the merge queue to.
        :param skip_extraction: Dispatch no text extraction.
        :param extraction_queue: The celery queue to extract documents on.
        :param extraction_throttle: Tasks to hold the extraction queue to.
        :param db_delay: Seconds to wait after each docket.
        :param start_row: Dockets to skip before dispatching anything.
        :param auto_resume: Start from the last checkpointed row.
        :param skip_verification: Do not wait to see what the merges did.
        :param verify_only: Check up on a load that already ran and dispatch
            nothing.
        :param in_flight_time: Seconds a queue's count must hold steady before
            what is left counts as lost.
        :param verify_timeout: Seconds to wait on a queue still coming down.
        :raises CommandError: If a pair of contradictory flags is given, or if
            the run database cannot be fetched.
        """
        loader_class = LOADERS[loader]
        run_key = compose_redis_key(loader, database)
        if verify_only and skip_verification:
            raise CommandError(
                "--verify-only and --skip-verification ask for opposite "
                "things: one does nothing but verify, the other does "
                "everything but. Pass one or the other."
            )
        if verify_only:
            # The ledger is in Redis and the run database is not read at all,
            # so there is nothing to fetch out of the bucket.
            self.report(
                loader_class(
                    database,
                    extract=not skip_extraction,
                    run_key=run_key,
                    in_flight_time=in_flight_time,
                    verify_timeout=verify_timeout,
                ).verify_only(),
                verified=True,
            )
            return
        if auto_resume:
            if start_row:
                raise CommandError(
                    f"--start-row {start_row} and --auto-resume are "
                    "mutually exclusive for clarity and simplicity."
                )
            start_row = get_last_parent_document_id_processed(run_key)
            logger.info("Auto-resuming from row %s.", start_row)
        try:
            with downloaded_run_database(database) as path:
                report = loader_class(
                    path,
                    limit=limit,
                    extract=not skip_extraction,
                    ingest_queue=ingest_queue,
                    ingest_throttle=ingest_throttle,
                    extraction_queue=extraction_queue,
                    extraction_throttle=extraction_throttle,
                    db_delay=db_delay,
                    start_row=start_row,
                    run_key=run_key,
                    verify=not skip_verification,
                    in_flight_time=in_flight_time,
                    verify_timeout=verify_timeout,
                ).load()
        except RunDatabaseUnavailable as error:
            raise CommandError(str(error)) from error

        self.report(report, verified=not skip_verification)

    def report(self, report: LoadReport, *, verified: bool) -> None:
        """Write out what the load did, for whoever ran it.

        This is a pretty summary of the run for the executer of the command.
        Everything is already logged and Sentried as necessary before we get here.

        :param report: The load's report.
        :param verified: Whether the load waited on its merges. An unverified
            load knows only what it dispatched, so saying nothing merged would
            be wrong rather than merely incomplete.
        """
        self.stdout.write(str(report))
        if not verified:
            self.stderr.write(
                self.style.WARNING(
                    "Verification was skipped: nothing here says whether "
                    "those merges ran, and nothing will report a docket "
                    "celery dropped."
                )
            )
            return
        for label, counts in (
            ("Created", report.creates),
            ("Updated", report.updates),
        ):
            for model, count in sorted(counts.items()):
                self.stdout.write(f"  {label} {count} {model}")
        if (extraction := report.extraction) is not None:
            self.stdout.write(f"  Extraction: {extraction}")
            if not extraction.complete:
                self.stderr.write(
                    self.style.WARNING(
                        f"{extraction.outstanding} documents written since "
                        "this run began still have no extracted text"
                        f"{self.humanize_outcome(extraction.wait)}. "
                        "`state_document_download --skip-download` will pick "
                        "them up."
                    )
                )
        if report.missing_count:
            # `missing` is a sample, not the set: a broker that went down
            # leaves a whole run outstanding, and nobody wants that printed.
            self.stderr.write(
                f"{report.missing_count} dockets were dispatched and never "
                f"reported back{self.humanize_outcome(report.merge_wait)}. Re-run the "
                "load over them; merging is idempotent."
            )
            for row, name in sorted(report.missing.items()):
                self.stderr.write(f"  row {row}: {name}")
            if (rest := report.missing_count - len(report.missing)) > 0:
                self.stderr.write(
                    f"  ... and {rest} more. The log names the Redis key "
                    "holding all of them."
                )
        if report.failed or report.invalid or report.refused:
            self.stderr.write(
                self.style.WARNING(
                    "Some dockets did not load. See the log for details."
                )
            )
        if not report.rows_read:
            self.stdout.write(
                "This checked a stored ledger and never opened the run "
                "database, so it cannot say how many rows were seen, invalid "
                "or refused."
            )

    @staticmethod
    def humanize_outcome(wait: WaitOutcome | None) -> str:
        """Human readable WaitOutcome for reporting.

        :param wait: How the phase's wait ended.
        :return: A clause to append, empty where there is nothing to say.
        """
        match wait:
            case WaitOutcome.STALLED:
                return (
                    ", and the queue stopped moving for long enough to say "
                    "they are not coming"
                )
            case WaitOutcome.TIMED_OUT:
                return (
                    " yet -- the queue was still coming down when this gave "
                    "up waiting, so they may well land on their own. Re-run "
                    "with --verify-only to settle it"
                )
            case _:
                return ""
