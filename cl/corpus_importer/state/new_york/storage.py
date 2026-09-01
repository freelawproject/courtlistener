"""Storage utilities for moving from the private bucket to the public one."""

import logging
from enum import Enum, auto
from typing import Any, cast

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db.models import FileField
from storages.backends.s3 import S3Storage

from cl.corpus_importer.state.new_york.utils import NYCOA_COURT_ID
from cl.search.state.new_york.models import RECAP_ROOT, NYCoADocument

logger = logging.getLogger(__name__)

NY_STATE_CODE: str = "ny"

PRIVATE_PREFIX: str = f"responses/dockets/{NY_STATE_CODE}/"

PUBLISHED_PREFIX: str = f"{RECAP_ROOT}/gov.uscourts.{NYCOA_COURT_ID}."
"""How far into a published key is the same for every Court-PASS document.

Everything after this is the case's docket number, and then the file's own
name; see `NYCoADocument.get_pdf_path`. Written out rather than derived,
because `is_published` has to answer for a path with no document to ask, so
`test_published_prefix_matches_pdf_path` is what keeps it honest."""

ABSENT_SOURCE: frozenset[str] = frozenset({"NoSuchKey", "NoSuchBucket", "404"})

class PublishOutcome(Enum):
    """What became of one attempt to move a file into the public bucket."""

    PUBLISHED = auto()
    MISSING = auto()
    FAILED = auto()


def is_published(path: str) -> bool:
    """Whether a stored path names a file in the bucket CourtListener serves.

    :param path: The path a document's `filepath_local` holds, or a key a
        scrape reported.
    :return: Whether the file is already where the public site expects it.
    """
    return path.startswith(PUBLISHED_PREFIX)


def is_scraped(path: str) -> bool:
    """Whether a stored path names a file the scraper left in the private
    bucket, which is the only kind of path publishing can move.

    :param path: The path a document's `filepath_local` holds, or a key a
        scrape reported.
    :return: Whether the file is sitting in the scrape bucket.
    """
    return path.startswith(PRIVATE_PREFIX)


def _document_storage() -> S3Storage:
    """The public storage from `NYCoADocument.filepath_local`."""
    field = cast(FileField, NYCoADocument._meta.get_field("filepath_local"))
    return cast(S3Storage, field.storage)


def copy_file(
    private_key: str, published_key: str, content_type: str = ""
) -> PublishOutcome:
    """Copy a scraped file from the private bucket into the public one.

    The copy is server-side, and `published_key` is deterministic, so a file
    copied twice lands on top of itself rather than beside itself. That is what
    lets the caller copy inside a transaction: a merge that rolls back leaves
    a copy nothing points at, which the retry overwrites.

    A copy that fails is only a failure if the file is not published. The move
    deletes the private original, so a merge that published a file and then
    rolled back -- or whose document row was later deleted -- leaves the file
    where it belongs with nothing in the private bucket to copy from. Finding
    it already at `published_key` is that move finishing, not an error.

    :param private_key: The key the scraper wrote the file under.
    :param published_key: The key to publish it under.
    :param content_type: The MIME type to serve the file as. Left to S3's
        default when the scrape stated none.
    :return: Whether the file is now published, and if not, why not. Anything
        other than `PublishOutcome.PUBLISHED` is logged, and the caller must
        not store `published_key` for a document whose file is not there.
    """
    storage = _document_storage()
    params: dict[str, Any] = dict(storage.get_object_parameters(published_key))
    if acl := settings.AWS_DEFAULT_ACL:
        params["ACL"] = acl
    if content_type:
        params["ContentType"] = content_type

    try:
        storage.connection.meta.client.copy_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=published_key,
            CopySource={
                "Bucket": settings.AWS_PRIVATE_STORAGE_BUCKET_NAME,
                "Key": private_key,
            },
            # The parameters above say how the published file should be
            # served, and S3 carries the source object's own metadata over
            # unless it is told to replace it.
            MetadataDirective="REPLACE",
            **params,
        )
    except (BotoCoreError, ClientError) as error:
        if storage.exists(published_key):
            logger.info(
                "Court-PASS file %s is already published as %s; nothing left "
                "to copy.",
                private_key,
                published_key,
            )
            return PublishOutcome.PUBLISHED
        logger.exception(
            "Could not publish Court-PASS file %s to %s.",
            private_key,
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
    :return: Whether the private bucket holds no such key.
    """
    if not isinstance(error, ClientError):
        return False
    code = error.response.get("Error", {}).get("Code", "")
    return str(code) in ABSENT_SOURCE


def discard_private_file(private_key: str) -> None:
    """Delete a scraped file whose published copy is committed.

    The other half of the move, split off so it runs once the merge that
    published the file has committed: until then the private bucket holds the
    only copy the retry could work from.

    :param private_key: The key to delete from the private bucket.
    """
    try:
        _document_storage().connection.meta.client.delete_object(
            Bucket=settings.AWS_PRIVATE_STORAGE_BUCKET_NAME, Key=private_key
        )
    except (BotoCoreError, ClientError):
        logger.exception(
            "Published Court-PASS file %s but could not remove the private "
            "copy.",
            private_key,
        )


def withdraw_file(published_key: str) -> None:
    """Delete a published file no document points at any more.

    :param published_key: The key to delete from the public bucket.
    """
    try:
        _document_storage().delete(published_key)
    except (BotoCoreError, ClientError):
        logger.exception(
            "Could not withdraw Court-PASS file %s; it is still published "
            "with nothing pointing at it.",
            published_key,
        )
