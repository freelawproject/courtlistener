import os


from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.timezone import now

from cl.lib.storage import UUIDFileSystemStorage



class UPLOAD_TYPE:
    JSON = 1
    HTML = 2
    PDF = 3

    NAMES = (
        (JSON, 'JSON'),
        (HTML, 'HTML'),
        (PDF, 'PDF'),
    )

def make_json_data_path(instance, filename):
    # return make_path('recap-data', filename)
    return make_path('json-data', filename)

def make_pdf_path(instance, filename):
    # return make_path('recap-data', filename)
    return make_path('pdf-data', filename)


def make_path(root, filename):
    d = now()
    return os.path.join(
        root,
        '%s' % d.year,
        '%02d' % d.month,
        '%02d' % d.day,
        filename,
    )

class AbstractDocument(models.Model):


    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    upload_type = models.SmallIntegerField(
        help_text="The type of object that is uploaded",
        choices=UPLOAD_TYPE.NAMES,
    )

    class Meta:
        abstract = True

    pass


class LASCJSON(AbstractDocument):
    """This is a simple object for holding original JSON content from any court api

    We will use this maintain a copy of all json acquired from LASC which is important
    in the event we lose our database.
    """

    filepath = models.FileField(
        help_text="The path of the original json file.",
        upload_to=make_json_data_path,
        storage=UUIDFileSystemStorage(),
        max_length=150,
    )


    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    @property
    def file_contents(self):
        with open(self.filepath.path, 'r') as f:
            return f.read().decode('utf-8')

    def print_file_contents(self):
        print(self.file_contents)


class LASCPDF(AbstractDocument):
    """This is a simple object for holding original JSON content from any court api

    We will use this maintain a copy of all json acquired from LASC which is important
    in the event we lose our database.
    """

    filepath = models.FileField(
        help_text="The path of the original json file.",
        upload_to=make_pdf_path,
        storage=UUIDFileSystemStorage(),
        max_length=150,
    )


    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    @property
    def file_contents(self):
        with open(self.filepath.path, 'r') as f:
            return f.read().decode('utf-8')

    def print_file_contents(self):
        print(self.file_contents)
