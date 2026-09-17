"""Moving scraped files into the layout CourtListener serves them from.

A scraper that has to fetch documents within its own session leaves them in
the private bucket, before CourtListener has the primary keys a file is named
by. Once a merge has written the documents, the loader copies each file to its
final key and deletes the original. The copies are server-side, so no file is
downloaded again.
"""

import logging
from enum import Enum, auto
from typing import Any, cast

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db.models import FileField, Model
from storages.backends.s3 import S3Storage

logger = logging.getLogger(__name__)

ABSENT_SOURCE: frozenset[str] = frozenset({"NoSuchKey", "NoSuchBucket", "404"})


class PublishOutcome(Enum):
    """What became of one attempt to copy a file to its published key."""

    PUBLISHED = auto()
    MISSING = auto()
    FAILED = auto()


def file_storage(model: type[Model]) -> S3Storage:
    """The storage a document model keeps its files in.

    :param model: A model with a `filepath_local` file field.
    :return: The storage backend of that field.
    """
    field = cast(FileField, model._meta.get_field("filepath_local"))
    return cast(S3Storage, field.storage)


def copy_file(
    storage: S3Storage,
    source_bucket: str,
    source_key: str,
    published_key: str,
    content_type: str = "",
) -> PublishOutcome:
    """Copy a file to its key in the public bucket.

    Overwrites whatever is already at `published_key`, which is how a file the
    court has corrected replaces the copy published before it.

    :param storage: The storage the published file belongs to, read for the
        parameters to serve it under.
    :param source_bucket: The bucket the file is in now.
    :param source_key: The key the file is under now.
    :param published_key: The key to publish it under.
    :param content_type: The MIME type to serve the file as. Left to S3's
        default when empty.
    :return: Whether the file is now published, and if not, why not. Anything
        other than `PublishOutcome.PUBLISHED` is logged, and the caller must
        not store `published_key` for a document whose file is not there.
    """
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
    except (BotoCoreError, ClientError) as error:
        logger.exception(
            "Could not publish %s/%s to %s.",
            source_bucket,
            source_key,
            published_key,
        )
        return (
            PublishOutcome.MISSING
            if _source_absent(error)
            else PublishOutcome.FAILED
        )
    return PublishOutcome.PUBLISHED


def _source_absent(error: BotoCoreError | ClientError) -> bool:
    """Whether a failed copy failed because there was nothing at the source.

    :param error: What the copy raised.
    :return: Whether the source bucket holds no such key.
    """
    if not isinstance(error, ClientError):
        return False
    code = error.response.get("Error", {}).get("Code", "")
    return str(code) in ABSENT_SOURCE


def delete_file(storage: S3Storage, bucket: str, key: str) -> None:
    """Delete a file nothing points at any more, logging rather than raising
    when the bucket refuses, since the document it belonged to is already
    settled either way.

    :param storage: Any storage connected to the account the bucket is in.
    :param bucket: The bucket to delete from.
    :param key: The key to delete.
    """
    try:
        storage.connection.meta.client.delete_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError):
        logger.exception(
            "Could not delete %s/%s; it is still stored with nothing "
            "pointing at it.",
            bucket,
            key,
        )
