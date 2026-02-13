import json
from collections.abc import Iterable
from pathlib import Path

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
        "Downloading docket HTML from S3: (Bucket: %s; Path: %s)",
        docket[0],
        docket[1],
    )
    with storage.open(docket[1], "rb") as f:
        content = f.read()

    storage = AWSMediaStorage(bucket_name=docket_headers[0])
    logger.info(
        "Downloading docket headers from S3: (Bucket: %s; Path: %s)",
        docket_headers[0],
        docket_headers[1],
    )
    with storage.open(docket_headers[1], "r") as f:
        headers = json.load(f)

    storage = AWSMediaStorage(bucket_name=docket_meta[0])
    logger.info(
        "Downloading docket meta from S3: (Bucket: %s; Path: %s)",
        docket_meta[0],
        docket_meta[1],
    )
    with storage.open(docket_meta[1], "r") as f:
        meta = TexasDocketMeta.model_validate_json(f.read())

    return content, headers, meta


class Command(CorpusImporterCommand):
    help = "Import Texas dockets from S3 using an inventory CSV."

    compose_redis_key = "texas_docket_import:log"

    @staticmethod
    def transform_inventory_iterator(
        csv_reader: Iterable[list[str]],
    ) -> Iterable[tuple[tuple[str, str], tuple[str, str], tuple[str, str]]]:
        html_rows = filter(
            lambda r: Path(r[1]).suffix == ".html",
            map(lambda r: (r[0].strip(), r[1].strip()), csv_reader),
        )

        previous_key_stem = None
        for html_row in html_rows:
            html_bucket, html_key = html_row
            html_path = Path(html_key)
            docket_name = html_path.stem
            if previous_key_stem and docket_name.startswith(previous_key_stem):
                continue
            else:
                previous_key_stem = docket_name
            header_key = str(
                html_path.with_name(f"{docket_name}_headers.json")
            )
            meta_key = str(html_path.with_name(f"{docket_name}_meta.json"))
            yield (
                (html_bucket, html_key),
                (html_bucket, header_key),
                (html_bucket, meta_key),
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
