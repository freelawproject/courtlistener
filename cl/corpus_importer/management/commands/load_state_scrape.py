"""Merge a jkent scrape run into CourtListener.

    manage.py load_state_scrape nycoa nycourts_gov/2026-08-08.db --dry-run

The path is within the standard bucket for files.

Documents the load writes are dispatched for text extraction as it goes.

Add a court by registering its `JKentScrapeLoader` subclass in `LOADERS`.
"""

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from cl.corpus_importer.state.loader import JKentScrapeLoader
from cl.corpus_importer.state.new_york.loader import NYCoACourtPassLoader
from cl.corpus_importer.state.run_db import (
    RunDatabaseUnavailable,
    downloaded_run_database,
)

logger = logging.getLogger(__name__)

LOADERS: dict[str, type[JKentScrapeLoader[Any]]] = {
    "nycoa": NYCoACourtPassLoader,
}


class Command(BaseCommand):
    help = "Merge a jkent scrape run database into CourtListener."

    def add_arguments(self, parser) -> None:
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

    def handle(self, *args: Any, **options: Any) -> None:
        loader_class = LOADERS[options["loader"]]
        try:
            with downloaded_run_database(options["database"]) as database:
                report = loader_class(
                    database,
                    limit=options["limit"],
                    dry_run=options["dry_run"],
                    extract=not options["skip_extraction"],
                    extraction_queue=options["extraction_queue"],
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
