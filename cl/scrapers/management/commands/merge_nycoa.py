"""Merge an NYCoA Court-PASS kent run into CourtListener.

Usage:

    ./manage.py merge_nycoa /path/to/NYCoA-full-2026-05-19.db

After the merge, ``IngestFile`` follow-ups are dispatched to the
``process_scraper_file`` Celery task — one task per file. The task
fetches the file from S3, consults doctor for the suffix, and (for
text-bearing types) extracts plain text into ``NYCoADocument``.
"""

from pathlib import Path

from cl.lib.command_utils import VerboseCommand, logger
from cl.scrapers.mergers.state.new_york.nycoa.driver import NYCoAMerger


class Command(VerboseCommand):
    help = "Merge an NYCoA Court-PASS kent run into CourtListener."

    def add_arguments(self, parser):
        parser.add_argument(
            "kent_db",
            type=Path,
            help="Path to a kent sqlite run (read-only).",
        )
        parser.add_argument(
            "--using",
            default="default",
            help="Django database alias to write into.",
        )
        parser.add_argument(
            "--no-dispatch",
            action="store_true",
            help=(
                "Skip the post-merge IngestFile dispatch. Useful for "
                "smoke-testing the merger output without firing Celery."
            ),
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        kent_db = options["kent_db"]
        if not kent_db.exists():
            raise FileNotFoundError(f"kent.db not found: {kent_db}")

        merger = NYCoAMerger(kent_db, using=options["using"])
        outcome = merger.run()

        logger.info(
            "NYCoA merge complete. Creates=%s Updates=%s Deletes=%s "
            "Follow-ups=%d",
            {k.__name__: len(v) for k, v in outcome.creates.items()},
            {k.__name__: len(v) for k, v in outcome.updates.items()},
            {k.__name__: len(v) for k, v in outcome.deletes.items()},
            len(outcome.follow_ups),
        )

        if not options["no_dispatch"]:
            ingests = merger.dispatch_ingest_files(outcome)
            logger.info("Dispatched %d IngestFile follow-ups.", len(ingests))
