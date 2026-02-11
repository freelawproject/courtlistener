import csv
import time

from celery import chain
from django.conf import settings

from cl.corpus_importer.tasks import (
    download_and_parse_scotus_docket,
    process_scotus_docket,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)


def compose_redis_key() -> str:
    """Compose a Redis key for SCOTUS importer log.
    :return: A Redis key as a string.
    """
    return "scotus_docket_import:log"


class Command(VerboseCommand):
    help = "Import SCOTUS dockets from S3 using an inventory CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--inventory-file",
            required=True,
            help="Path to the inventory CSV relative to MEDIA_ROOT.",
        )
        parser.add_argument(
            "--retrieval-queue",
            default="celery",
            help="Which celery queue to use for S3 retrieval",
        )
        parser.add_argument(
            "--ingesting-queue",
            default="celery",
            help="Which celery queue to use for DB ingesting",
        )
        parser.add_argument(
            "--throttle-min-items",
            type=int,
            default=5,
            help="CeleryThrottle min_items parameter.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="Seconds to sleep between scheduling tasks.",
        )
        parser.add_argument(
            "--start-row",
            type=int,
            default=0,
            help="Row number to start from (for manual resume).",
        )
        parser.add_argument(
            "--inventory-rows",
            type=int,
            required=True,
            help="Total number of rows in the inventory CSV. Used to "
            "log progress percentage.",
        )
        parser.add_argument(
            "--auto-resume",
            action="store_true",
            default=False,
            help="Resume from last row stored in Redis.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        retrieval_queue = options["retrieval_queue"]
        ingesting_queue = options["ingesting_queue"]
        delay = options["delay"]
        inventory_rows = options["inventory_rows"]
        inventory_path = settings.MEDIA_ROOT / options["inventory_file"]

        start_row = options["start_row"]
        if options["auto_resume"]:
            start_row = get_last_parent_document_id_processed(
                compose_redis_key()
            )
            logger.info("Auto-resuming from row %s.", start_row)

        throttle = CeleryThrottle(
            min_items=options["throttle_min_items"],
            queue_name=ingesting_queue,
        )

        with open(inventory_path) as f:
            reader = csv.reader(f)
            for row_idx, row in enumerate(reader):
                if row_idx < start_row:
                    # Skip row if auto-resume is enabled
                    continue

                bucket = row[0].strip()
                s3_key = row[1].strip()

                throttle.maybe_wait()
                chain(
                    download_and_parse_scotus_docket.si(bucket, s3_key).set(
                        queue=retrieval_queue
                    ),
                    process_scotus_docket.s().set(queue=ingesting_queue),
                ).apply_async()
                time.sleep(delay)

                if row_idx % 100 == 0:
                    progress = f" ({row_idx / inventory_rows:.1%})"
                    logger.info(
                        "Scheduled %s rows %s. Current row: %s.",
                        row_idx,
                        progress,
                        s3_key,
                    )
                    log_last_document_indexed(row_idx, compose_redis_key())

        logger.info("Finished scheduling all rows from inventory.")
