import uuid

import os
from django.core.files.storage import FileSystemStorage
import itertools
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class IncrementingFileSystemStorage(FileSystemStorage):
    """This maintains the old behavior of get_available_name that was available
    prior to Django 1.5.9. This behavior increments the file name by adding _1,
    _2, etc., but was removed because incrementing the file names in this
    manner created a security vector if users were able to upload files.

    We are only able to use it in places where users are not uploading files,
    and we are instead creating them programatically (for example, via a
    scraper).

    For more detail, see:

    https://docs.djangoproject.com/en/1.8/releases/1.5.9/#file-upload-denial-of-service
    """

    def get_available_name(self, name, max_length=None):
        """
        Returns a filename that's free on the target storage system, and
        available for new content to be written to.
        """
        dir_name, file_name = os.path.split(name)
        file_root, file_ext = os.path.splitext(file_name)
        # If the filename already exists, add an underscore and a number (before
        # the file extension, if one exists) to the filename until the generated
        # filename doesn't exist.
        count = itertools.count(1)
        while self.exists(name):
            # file_ext includes the dot.
            name = os.path.join(dir_name,
                                "%s_%s%s" % (file_root, next(count), file_ext))

        return name


class UUIDFileSystemStorage(FileSystemStorage):
    """Implements a simple UUID file system storage.
    
    Useful when you don't care what the name of the file is, but you want it to
    be unique. Keeps the path from upload_to param and the extension of the
    original file.
    """
    def get_available_name(self, name, max_length=None):
        dir_name, file_name = os.path.split(name)
        _, file_ext = os.path.splitext(file_name)
        return os.path.join(dir_name, uuid.uuid4().hex + file_ext)


class AWSMediaStorage(S3Boto3Storage):
    """Implements AWS file system storage.

    We use AWSMediaStorage to upload LASC PDF files to AWS.
    """
    location = ""
    AWS_DEFAULT_ACL = settings.AWS_DEFAULT_ACL
    file_overwrite = True
    custom_domain = False
