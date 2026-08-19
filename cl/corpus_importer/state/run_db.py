"""Fetch a jkent run database out of the scrape bucket.

A scrape run's SQLite database is archived in object storage rather than kept
on the machine that loads it, so a loader has to bring one down first: SQLite
reads a file, not a stream. `downloaded_run_database` does that, and takes the
file away again when the caller is done with it.

The run database lives in `AWS_STORAGE_BUCKET_NAME`, alongside the files the
scrape downloaded -- which is what lets a merge point a document's
`filepath_local` straight at the path the run reports.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

logger = logging.getLogger(__name__)


class RunDatabaseUnavailable(Exception):
    """A run database could not be fetched from the scrape bucket.

    Raised for every reason the fetch can fail -- a key that is not there,
    credentials that cannot read it, a transfer that broke off -- because a
    caller can do nothing about any of them but report the message.
    """


def scrape_bucket_client() -> Any:
    """A client for the bucket that holds scrape run databases.

    Reads CourtListener's S3 credentials, which in development are the
    `AWS_DEV_*` pair. Returns an untyped boto3 client; boto3 ships no stubs.
    """
    # Unset settings have to reach boto3 as `None`, not as the empty string
    # they default to. botocore reads an empty credential as an explicit
    # instruction to sign anonymously, which earns a bare 400 from the far
    # end; `None` lets it fall through to its own chain -- the instance role a
    # deployment may be relying on, or a legible "unable to locate
    # credentials" when there is nothing to find.
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )


@contextmanager
def downloaded_run_database(key: str) -> Iterator[Path]:
    """Download the run database at `key` and yield the path it landed at.

    The file is deleted when the context exits, so a caller that wants to keep
    the database has to copy it out. Run databases reach hundreds of megabytes
    and the download goes to the system temporary directory, which therefore
    needs the room.

    :param key: The database's path within `AWS_STORAGE_BUCKET_NAME`, for
        instance `nycourts_gov/2026-08-08.db`.
    :yield: Path to the downloaded database.
    :raises RunDatabaseUnavailable: If `key` names no file, or the download
        fails for any reason.
    """
    # An S3 key is an opaque string rather than a path, so the file name is
    # whatever follows the last separator -- and a key with nothing there names
    # a prefix, not a database.
    name = key.rsplit("/", 1)[-1]
    if name in ("", ".", ".."):
        raise RunDatabaseUnavailable(f"{key!r} is not a path to a database")
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    client = scrape_bucket_client()
    with TemporaryDirectory(prefix="scrape-run-") as directory:
        destination = Path(directory) / name
        logger.info("Downloading s3://%s/%s to %s", bucket, key, destination)
        try:
            client.download_file(bucket, key, str(destination))
        except (BotoCoreError, ClientError) as error:
            raise RunDatabaseUnavailable(
                f"Could not download s3://{bucket}/{key}: {error}"
            ) from error
        logger.info(
            "Downloaded s3://%s/%s, %s bytes",
            bucket,
            key,
            destination.stat().st_size,
        )
        yield destination
