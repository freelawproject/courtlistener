import csv
import random
import time
from abc import abstractmethod
from collections.abc import Iterable
from datetime import date
from itertools import islice
from typing import ClassVar

from celery import Task, chain
from django.conf import settings
from pydantic import BaseModel, Field, field_validator

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import (
    AbstractCommand,
    VerboseCommand,
    logger,
)
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


class CorpusImporterCommand(AbstractCommand, VerboseCommand):
    """Base class for `cl.corpus_importer` commands encapsulating inventory\
        file reading, celery queue interactions, and redis logging.

    Uses an inventory CSV from S3 to find files to parse and ingest into the\
        database. Includes ratelimiting and autoresume logic.

    Required methods are:

    - `merge_task`: Should return a Celery task which takes the output of\
        `download_task`, parses it, and merges it into the database. Input\
        should be whatever the output of `download_task` is. Must accept a\
        `download_attachments` boolean keyword argument indicating whether\
        docket entry attachments should be downloaded as part of the merging\
        process.

    Required properties are:

    - `compose_redis_key`: The Redis log key to use for tracking progress.

    Optional methods are:
    - `download_task`: Should return the task used to download files from S3.\
        A default implementation is provided for convenience."""

    compose_redis_key: ClassVar[str]

    inventory_file: str = Field(
        alias="inventory_file",
        description="Path to the inventory CSV relative to MEDIA_ROOT.",
    )
    retrieval_queue: str = Field(
        alias="retrieval-queue",
        default="celery",
        description="Which celery queue to use for S3 retrieval.",
    )
    ingesting_queue: str = Field(
        alias="ingesting-queue",
        default="celery",
        description="Which celery queue to use for DB ingesting.",
    )
    throttle_min_items: int = Field(
        alias="throttle-min-items",
        default=5,
        description="CeleryThrottle min_items parameter.",
    )
    delay: float = Field(
        alias="delay",
        default=1.0,
        description="Seconds to sleep between scheduling tasks.",
    )
    start_row: int = Field(
        alias="start-row",
        default=0,
        description="Row number to start from (for manual resume).",
    )
    inventory_rows: int = Field(
        alias="inventory-rows",
        description="Total number of rows in the inventory CSV. Used to "
        "log progress percentage.",
    )
    auto_resume: bool = Field(
        alias="auto-resume",
        default=False,
        description="Resume from last row stored in Redis.",
    )
    test_random: bool = Field(
        alias="test-random",
        default=False,
        description="Randomly select rows from the inventory file to import.",
    )
    download_attachments: bool = Field(
        alias="download-attachments",
        default=False,
        description="Whether to download docket entry attachments as part of this command.",
    )

    @staticmethod
    def download_task() -> Task:
        from cl.corpus_importer.tasks import default_corpus_download_task

        return default_corpus_download_task

    @staticmethod
    @abstractmethod
    def merge_task() -> Task: ...

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

    def run(self):
        inventory_path = settings.MEDIA_ROOT / self.inventory_file

        start_row = self.start_row
        if self.auto_resume:
            start_row = get_last_parent_document_id_processed(
                self.compose_redis_key
            )
            logger.info("Auto-resuming from row %s.", start_row)

        total_rows = self.inventory_rows - start_row

        throttle = CeleryThrottle(
            min_items=self.throttle_min_items,
            queue_name=self.ingesting_queue,
        )

        with open(inventory_path, encoding="utf-8") as f:
            download_inputs = self.transform_inventory_iterator(csv.reader(f))
            if self.test_random:
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
                    .set(queue=self.retrieval_queue),
                    self.merge_task()
                    .s(download_attachments=self.download_attachments)
                    .set(queue=self.ingesting_queue),
                ).apply_async()
                time.sleep(self.delay)

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
