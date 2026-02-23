import csv
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import date
from itertools import islice
from typing import final

from celery import chain
from django.conf import settings
from pydantic import BaseModel, field_validator

from cl.celery_init import app
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)


class TexasDocketMeta(BaseModel):
    case_number: str
    case_url: str
    date_filed: date
    style: str
    v: str
    case_type: str
    coa_case_number: str
    trial_court_case_number: str
    trial_court_county: str
    trial_court: str
    appellate_court: str
    court_code: str

    @field_validator("date_filed", mode="before")
    def date_filed_validator(cls, v):
        return date(*(time.strptime(v, "%m/%d/%Y")[0:3]))


class CorpusImporterCommand(VerboseCommand, ABC):
    """Base class for `cl.corpus_importer` commands encapsulating inventory\
        file reading, celery queue interactions, and redis logging.

    Uses an inventory CSV from S3 to find files to parse and ingest into the\
        database. Includes ratelimiting and autoresume logic.

    Required methods are:

    - `merge_task`: Should return a Celery task which takes the output of
        `download_task`, parses it, and merges it into the database. Input\
         should be whatever the output of `download_task` is.

    Required properties are:

    - `compose_redis_key`: The Redis log key to use for tracking progress.

    Optional methods are:
    - `download_task`: Should return the task used to download files from S3.\
        A default implementation is provided for convenience."""

    compose_redis_key: str

    @final
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
        parser.add_argument(
            "--test-random",
            type=bool,
            default=False,
            help="Randomly select rows from the inventory file to import.",
        )

    @staticmethod
    def download_task() -> app.Task:
        from cl.corpus_importer.tasks import default_corpus_download_task

        return default_corpus_download_task

    @staticmethod
    @abstractmethod
    def merge_task() -> app.Task: ...

    @staticmethod
    def transform_inventory_iterator(
        csv_reader: Iterable[list[str]],
    ) -> Iterable:
        """
        Optionally performs transformations on the inventory CSV file\
            before passing it to the download Celery task. Can be used for\
            instance to merge consecutive rows which represent the same docket\
            into one object.

        :param csv_reader: The `csv.Reader` object to use to read the CSV.

        :return: The transformed inventory CSV iterator. The item of the\
            iterable should be a list of arguments to be passed to the\
            download task."""
        return map(lambda row: [row[0].strip(), row[1].strip()], csv_reader)

    @final
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
                self.compose_redis_key
            )
            logger.info("Auto-resuming from row %s.", start_row)

        total_rows = inventory_rows - start_row

        throttle = CeleryThrottle(
            min_items=options["throttle_min_items"],
            queue_name=ingesting_queue,
        )

        with open(inventory_path, encoding="utf-8") as f:
            download_inputs = self.transform_inventory_iterator(csv.reader(f))
            if options["test_random"]:
                logger.warning(
                    "In testing mode. Randomly selecting rows from the inventory file."
                )
                download_inputs = filter(
                    lambda _: random.random() < 0.001, download_inputs
                )
            for row_idx, download_args in islice(
                enumerate(download_inputs), start_row, None
            ):
                throttle.maybe_wait()
                chain(
                    self.download_task()
                    .si(*download_args)
                    .set(queue=retrieval_queue),
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
                        download_args,
                    )
                    log_last_document_indexed(row_idx, self.compose_redis_key)

        logger.info("Finished scheduling all rows from inventory.")
