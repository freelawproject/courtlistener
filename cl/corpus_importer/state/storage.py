"""Moving scraped files into the layout CourtListener serves them from.

A scraper that has to fetch documents within its own session leaves them in
the private bucket, before CourtListener has the primary keys a file is named
by. Once a merge has written the documents, the loader copies each file to its
final key and deletes the original. The copies are server-side, so no file is
downloaded again.
"""

import logging
from enum import Enum, auto
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from cl.lib.storage import AWSMediaStorage

logger = logging.getLogger(__name__)

ABSENT_SOURCE: frozenset[str] = frozenset({"NoSuchKey", "NoSuchBucket", "404"})


class PublishOutcome(Enum):
    """What became of one attempt to copy a file to its published key."""

    PUBLISHED = auto()
    MISSING = auto()
    FAILED = auto()


def copy_file(
    source_bucket: str,
    source_key: str,
    published_key: str,
    content_type: str = "",
) -> PublishOutcome:
    """Copy a file to its key in the public bucket.

    Overwrites whatever is already at `published_key`, which is how a file the
    court has corrected replaces the copy published before it.

    :param source_bucket: The bucket the file is in now.
    :param source_key: The key the file is under now.
    :param published_key: The key to publish it under.
    :param content_type: The MIME type to serve the file as. Left to S3's
        default when empty.
    :return: Whether the file is now published, and if not, why not. Anything
        other than `PublishOutcome.PUBLISHED` is logged, and the caller must
        not store `published_key` for a document whose file is not there.
    """
    storage = AWSMediaStorage()
    params: dict[str, Any] = dict(storage.get_object_parameters(published_key))
    if acl := settings.AWS_DEFAULT_ACL:
        params["ACL"] = acl
    if content_type:
        params["ContentType"] = content_type
    try:
        storage.connection.meta.client.copy_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=published_key,
            CopySource={"Bucket": source_bucket, "Key": source_key},
            # The parameters above say how the published file should be
            # served, and S3 carries the source object's own metadata over
            # unless it is told to replace it.
            MetadataDirective="REPLACE",
            **params,
        )
    except ClientError as error:
        _log_failure(source_bucket, source_key, published_key)
        code = str(error.response.get("Error", {}).get("Code", ""))
        if code in ABSENT_SOURCE:
            return PublishOutcome.MISSING
        return PublishOutcome.FAILED
    except BotoCoreError:
        _log_failure(source_bucket, source_key, published_key)
        return PublishOutcome.FAILED
    return PublishOutcome.PUBLISHED


def _log_failure(
    source_bucket: str, source_key: str, published_key: str
) -> None:
    """Log the copy that just raised, with the exception being handled."""
    logger.exception(
        "Could not publish %s/%s to %s.",
        source_bucket,
        source_key,
        published_key,
    )


def delete_file(bucket: str, key: str) -> None:
    """Delete a file nothing points at any more, logging rather than raising
    when the bucket refuses, since the document it belonged to is already
    settled either way.

    :param bucket: The bucket to delete from.
    :param key: The key to delete.
    """
    try:
        AWSMediaStorage().connection.meta.client.delete_object(
            Bucket=bucket, Key=key
        )
    except (BotoCoreError, ClientError):
        logger.exception(
            "Could not delete %s/%s; it is still stored with nothing "
            "pointing at it.",
            bucket,
            key,
        )
