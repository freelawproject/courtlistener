"""Merge a jkent scrape run into CourtListener.

    manage.py load_state_scrape nycoa nycourts_gov/2026-08-08.db --dry-run

The path is within the standard bucket for files.

Documents the load writes are dispatched for text extraction as it goes.

A load that dies partway can be picked up with `--auto-resume`, which starts
from the last row the previous load of the same run database checkpointed. The
checkpoint is dropped once a load reaches the end, so a run that finished is
never resumed by mistake.

Add a court by registering its `JKentScrapeLoader` subclass in `LOADERS`.
"""

import logging
from typing import Any

from django.core.management.base import (
    BaseCommand,
    CommandError,
    CommandParser,
)

from cl.corpus_importer.state.loader import JKentScrapeLoader
from cl.corpus_importer.state.new_york.loader import NYCoACourtPassLoader
from cl.corpus_importer.state.run_db import (
    RunDatabaseUnavailable,
    downloaded_run_database,
)
from cl.lib.indexing_utils import get_last_parent_document_id_processed

logger = logging.getLogger(__name__)

LOADERS: dict[str, type[JKentScrapeLoader[Any]]] = {
    "nycoa": NYCoACourtPassLoader,
}


def compose_redis_key(loader: str, database: str) -> str:
    """Compose the Redis key a load checkpoints its position under.

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
            "--dry-run",
            action="store_true",
            help=(
                "Run the merge in full and roll it back, to see what a load "
                "would do without writing anything."
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
            default=0,
            help=(
                "Hold the extraction queue to roughly this many tasks, "
                "waiting for the workers to catch up when it runs longer. "
                "Zero, the default, dispatches as fast as the merge goes, "
                "which over a whole run is enough to bury the queue; either "
                "set this or load with --skip-extraction."
            ),
        )
        parser.add_argument(
            "--db-delay",
            type=float,
            default=0.0,
            help=(
                "Seconds to wait after each docket, to keep a long load from "
                "monopolising the database. Zero, the default, runs flat out."
            ),
        )
        parser.add_argument(
            "--start-row",
            type=int,
            default=0,
            help="Skip this many dockets, for resuming a load by hand.",
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

    def handle(
        self,
        *args: Any,
        loader: str,
        database: str,
        limit: int | None,
        dry_run: bool,
        skip_extraction: bool,
        extraction_queue: str,
        extraction_throttle: int,
        db_delay: float,
        start_row: int,
        auto_resume: bool,
        **options: Any,
    ) -> None:
        """Download the run database, merge it, and report what it did.

        :param loader: The `LOADERS` name of the court's loader.
        :param database: The run database's path within the storage bucket.
        :param limit: Stop after this many dockets.
        :param dry_run: Merge in full and roll it back.
        :param skip_extraction: Dispatch no text extraction.
        :param extraction_queue: The celery queue to extract documents on.
        :param extraction_throttle: Tasks to hold the extraction queue to.
        :param db_delay: Seconds to wait after each docket.
        :param start_row: Dockets to skip before merging anything.
        :param auto_resume: Start from the last checkpointed row.
        :raises CommandError: If the run database cannot be fetched.
        """
        loader_class = LOADERS[loader]
        checkpoint_key = compose_redis_key(loader, database)
        if auto_resume:
            if start_row:
                logger.warning(
                    "--auto-resume is taking precedence over --start-row %s.",
                    start_row,
                )
            start_row = get_last_parent_document_id_processed(checkpoint_key)
            logger.info("Auto-resuming from row %s.", start_row)
        try:
            with downloaded_run_database(database) as path:
                report = loader_class(
                    path,
                    limit=limit,
                    dry_run=dry_run,
                    extract=not skip_extraction,
                    extraction_queue=extraction_queue,
                    extraction_throttle=extraction_throttle,
                    db_delay=db_delay,
                    start_row=start_row,
                    checkpoint_key=checkpoint_key,
                ).load()
        except RunDatabaseUnavailable as error:
            raise CommandError(str(error)) from error

        self.stdout.write(str(report))
        for label, counts in (
            ("Created", report.result.creates),
            ("Updated", report.result.updates),
        ):
            for model, pks in sorted(counts.items()):
                self.stdout.write(f"  {label} {len(pks)} {model}")
        if report.invalid or report.failed:
            self.stdout.write(
                self.style.WARNING(
                    "Some dockets did not load. See the log for details."
                )
            )
