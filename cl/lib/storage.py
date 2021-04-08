import itertools
import os
import uuid
from typing import Optional

from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage
from storages.backends.s3boto3 import S3Boto3Storage


def get_name_by_incrementing(
    instance: Storage,
    name: str,
    max_length: Optional[int] = None,
) -> str:
    """Generate usable file name for storage iterating if needed.

    Returns a filename that is available in the storage mechanism,
    taking the provided filename into account.

    This maintains the old behavior of get_available_name that was available
    prior to Django 1.5.9. This behavior increments the file name by adding _1,
    _2, etc., but was removed because incrementing the file names in this
    manner created a security vector if users were able to upload (many) files.

    We are only able to use it in places where users are not uploading files,
    and we are instead creating them programmatically (for example, via a
    scraper).

    For more detail, see:

    https://docs.djangoproject.com/en/1.8/releases/1.5.9/#file-upload-denial-of-service

    :param instance: The instance of the storage class being used
    :param max_length: The name will not exceed max_length, if provided
    :param name: File name of the object being saved
    :return: The filepath
    """
    dir_name, file_name = os.path.split(name)
    file_root, file_ext = os.path.splitext(file_name)
    count = itertools.count(1)
    while instance.exists(name):
        # file_ext includes the dot.
        name = os.path.join(
            dir_name, "%s_%s%s" % (file_root, next(count), file_ext)
        )
    return name


class IncrementingFileSystemStorage(FileSystemStorage):
    """A storage class that increments the filename."""

    def get_available_name(
        self,
        name: str,
        max_length: Optional[int] = None,
    ) -> str:
        return get_name_by_incrementing(self, name, max_length)


class UUIDFileSystemStorage(FileSystemStorage):
    """Implements a simple UUID file system storage.

    Useful when you don't care what the name of the file is, but you want it to
    be unique. Keeps the path from upload_to param and the extension of the
    original file.
    """

    def get_available_name(
        self,
        name: str,
        max_length: Optional[int] = None,
    ) -> str:
        dir_name, file_name = os.path.split(name)
        _, file_ext = os.path.splitext(file_name)
        return os.path.join(dir_name, uuid.uuid4().hex + file_ext)


class AWSMediaStorage(S3Boto3Storage):
    """Implements AWS file system storage with a few overrides"""

    location = ""
    AWS_DEFAULT_ACL = settings.AWS_DEFAULT_ACL
    file_overwrite = True
    custom_domain = False

    def get_available_name(
        self,
        name: str,
        max_length: Optional[int] = None,
    ) -> str:
        return get_name_by_incrementing(self, name, max_length)
