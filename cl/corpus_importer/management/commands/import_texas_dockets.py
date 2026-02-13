import json
from collections.abc import Iterable
from itertools import batched

import botocore.exceptions

from cl.celery_init import app
from cl.corpus_importer.management.utils import (
    CorpusImporterCommand,
    TexasDocketMeta,
)
from cl.corpus_importer.tasks import merge_texas_docket, parse_texas_docket
from cl.lib.command_utils import logger
from cl.lib.decorators import time_call
from cl.lib.storage import AWSMediaStorage


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
@time_call(logger)
def _texas_corpus_download_task(
    self: app.Task,
    docket: tuple[str, str],
    docket_headers: tuple[str, str],
    docket_meta: tuple[str, str],
) -> tuple[bytes, dict[str, str], TexasDocketMeta]:
    """Downloads a scraped file from S3 and returns it for parsing.

    :param docket: Tuple of S3 bucket name and key where docket HTML is stored.
    :param docket_headers: Tuple of S3 bucket name and key where docket
      response headers are stored.
    :param docket_meta: Tuple of S3 bucket name and key where docket metadata
      is stored.
    :return: Tuple with entries: Bytes of downloaded file, dictionary with
      response headers, and docket metadata."""
    storage = AWSMediaStorage(bucket_name=docket[0])
    logger.info(
        "Downloading HTML file from S3: (Bucket: %s; Path: %s)",
        docket[0],
        docket[1],
    )
    with storage.open(docket[1], "rb") as f:
        content = f.read()

    storage = AWSMediaStorage(bucket_name=docket_headers[0])
    logger.info("Downloading docket headers from S3: %s", docket_headers[1])
    with storage.open(docket_headers[1], "r") as f:
        headers = json.load(f)

    storage = AWSMediaStorage(bucket_name=docket_meta[0])
    logger.info("Downloading docket meta from S3: %s", docket_meta[1])
    with storage.open(docket_meta[1], "r") as f:
        meta = TexasDocketMeta.model_validate_json(f.read())

    return content, headers, meta


class Command(CorpusImporterCommand):
    help = "Import Texas dockets from S3 using an inventory CSV."

    compose_redis_key = "texas_docket_import:log"

    @staticmethod
    def inventory_row_batch_to_download(
        batch: tuple[list[str], ...],
    ) -> tuple[tuple[str, str], tuple[str, str], tuple[str, str]]:
        """Extracts S3 buckets and paths from a batch of three entries from the
        Texas inventory file. These will point to: the docket HTML, the docket
        response headers, and metadata about the docket."""
        return (
            (batch[0][0].strip(), batch[0][1].strip()),
            (batch[1][0].strip(), batch[1][1].strip()),
            (batch[2][0].strip(), batch[2][1].strip()),
        )

    @staticmethod
    def transform_inventory_iterator(
        csv_reader: Iterable[list[str]],
    ) -> Iterable[tuple[tuple[str, str], tuple[str, str], tuple[str, str]]]:
        return map(
            Command.inventory_row_batch_to_download, batched(csv_reader, 3)
        )

    @staticmethod
    def download_task() -> app.Task:
        return _texas_corpus_download_task

    @staticmethod
    def parse_task() -> app.Task:
        return parse_texas_docket

    @staticmethod
    def merge_task() -> app.Task:
        return merge_texas_docket
