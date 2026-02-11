import csv
import logging
import os
import time
from abc import ABC, abstractmethod
from itertools import islice

import botocore.exceptions
from celery import chain
from django.conf import settings
from django.core.management import BaseCommand, CommandError

from cl.celery_init import app
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.lib.juriscraper_utils import get_module_by_court_id
from cl.lib.storage import AWSMediaStorage

logger = logging.getLogger(__name__)


class VerboseCommand(BaseCommand):
    def handle(self, *args, **options):
        verbosity = options.get("verbosity")
        if not verbosity:
            logger.setLevel(logging.WARN)
        elif verbosity == 0:
            logger.setLevel(logging.WARN)
        elif verbosity == 1:  # default
            logger.setLevel(logging.INFO)
        elif verbosity > 1:
            logger.setLevel(logging.DEBUG)
            # This will make juriscraper's logger accept most logger calls.
            juriscraper_logger = logging.getLogger("juriscraper")
            juriscraper_logger.setLevel(logging.DEBUG)


class ScraperCommand(VerboseCommand):
    """Base class for cl.scrapers commands that use Juriscraper

    Implements the `--courts` argument to lookup for a Site object
    """

    # To be used on get_module_by_court_id
    # Defined by inheriting classes
    juriscraper_module_type = ""

    def add_arguments(self, parser):
        parser.add_argument(
            "--courts",
            dest="court_id",
            metavar="COURTID",
            type=lambda s: (
                s
                if "." in s
                else get_module_by_court_id(s, self.juriscraper_module_type)
            ),
            required=True,
            help=(
                "The court(s) to scrape and extract. One of: "
                "1. a python module or package import from the Juriscraper library, e.g."
                "'juriscraper.opinions.united_states.federal_appellate.ca1' "
                "or simply 'juriscraper.opinions' to do all opinions."
                ""
                "2. a court_id, to be used to lookup for a full module path"
                "An error will be raised if the `court_id` matches more than "
                "one module path. In that case, use the full path"
            ),
        )


@app.task(
    bind=True,
    autoretry_for=(
        botocore.exceptions.HTTPClientError,
        botocore.exceptions.ConnectionError,
    ),
    max_retries=5,
    retry_backoff=10,
    ignore_result=True,
)
def _corpus_download_task(bucket: str, s3_key: str) -> tuple[bytes, str, str]:
    """Downloads a scraped file from S3 and returns it for parsing.

    :param bucket: S3 bucket name.
    :param s3_key: S3 key to download file from.
    :return: Tuple with entries: Bytes of downloaded file, the bucket
    parameter, and the s3_key parameter."""
    logger.info("Downloading file from S3: %s", s3_key)
    storage = AWSMediaStorage(bucket_name=bucket)
    with storage.open(s3_key, "rb") as f:
        content = f.read()
    return content, bucket, s3_key


class CorpusImporterCommand(VerboseCommand, ABC):
    """Base class for `cl.corpus_importer` commands encapsulating inventory
    file reading, celery queue interactions, and redis logging.

    Uses an inventory CSV from S3 to find files to parse and ingest into the
    database. Includes ratelimiting and autoresume logic.

    Required methods are:

    - `parse_task`: Should return a Celery task which parses a `bytes` object
      into some usable format, typically using Juriscraper. Signature should be:
      `task(content: bytes, bucket_name: str, s3_key: str)`, unless you manually
      override `download_task` to return a different format.
    - `merge_task`: Should return a Celery task which takes the output of
      `parse_task` and merges it into the database. Input should be whatever the
      output of `parse_task` is.

    Required properties are:

    - `compose_redis_key`: The Redis log key to use for tracking progress.

    Optional methods are:
    - `download_task`: Should return the task used to download files from S3. A
      default implementation is provided for convenience."""

    compose_redis_key: str

    def add_arguments(self, parser):
        parser.add_argument(
            "--inventory-file",
            required=True,
            help="Path to the inventory CSV relative to MEDIA_ROOT.",
        )
        parser.add_argument(
            "--retrieval-queue",
            default="celery",
            help="Which celery queue to use for S3 retrieval.",
        )
        parser.add_argument(
            "--parsing-queue",
            default="celery",
            help="Which celery queue to use for document parsing.",
        )
        parser.add_argument(
            "--ingesting-queue",
            default="celery",
            help="Which celery queue to use for DB ingesting.",
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

    @staticmethod
    def download_task() -> app.Task:
        return _corpus_download_task

    @staticmethod
    @abstractmethod
    def parse_task() -> app.Task: ...

    @staticmethod
    @abstractmethod
    def merge_task() -> app.Task: ...

    def handle(self, *args, **options):
        super().handle(*args, **options)

        retrieval_queue = options["retrieval_queue"]
        parse_queue = options["parsing_queue"]
        ingesting_queue = options["ingesting_queue"]
        delay = options["delay"]
        inventory_rows = options["inventory_rows"]
        inventory_path = settings.MEDIA_ROOT / options["inventory_file"]

        start_row = options["start_row"]
        if options["auto_resume"]:
            start_row = get_last_parent_document_id_processed(
                self.compose_redis_key
            )
            logger.info("Auto-resuming from row %s.", start_row)

        total_rows = inventory_rows - start_row

        throttle = CeleryThrottle(
            min_items=options["throttle_min_items"],
            queue_name=ingesting_queue,
        )

        with open(inventory_path) as f:
            reader = csv.reader(f)
            for row_idx, row in islice(enumerate(reader), start_row, None):
                bucket = row[0].strip()
                s3_key = row[1].strip()

                throttle.maybe_wait()
                chain(
                    self.download_task()
                    .si(bucket, s3_key)
                    .set(queue=retrieval_queue),
                    self.parse_task().s().set(queue=parse_queue),
                    self.merge_task().s().set(queue=ingesting_queue),
                ).apply_async()
                time.sleep(delay)

                if row_idx % 100 == 0:
                    processed = row_idx - start_row
                    progress = (
                        f" ({processed / total_rows:.1%})"
                        if total_rows
                        else ""
                    )
                    logger.info(
                        "Scheduled %s rows %s. Current row: %s.",
                        row_idx,
                        progress,
                        s3_key,
                    )
                    log_last_document_indexed(row_idx, self.compose_redis_key)

        logger.info("Finished scheduling all rows from inventory.")


class CommandUtils:
    """A mixin to give some useful methods to sub classes."""

    @staticmethod
    def ensure_file_ok(file_path):
        """Check to make sure that a file path exists and is valid."""
        if not os.path.exists(file_path):
            raise CommandError(f"Unable to find file at {file_path}")
        if not os.access(file_path, os.R_OK):
            raise CommandError(f"Unable to read file at {file_path}")
