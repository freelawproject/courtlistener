from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import now

from cl.lib.storage import UUIDFileSystemStorage
from cl.search.models import Court


def make_recap_processing_queue_path(instance, filename):
    d = now()
    return 'recap_processing_queue/%s/%02d/%02d/%s' % (d.year, d.month, d.day,
                                                       filename)


class ProcessingQueue(models.Model):
    AWAITING_PROCESSING = 1
    PROCESSING_SUCCESSFUL = 2
    PROCESSING_FAILED = 3
    PROCESSING_STATUSES = (
        (AWAITING_PROCESSING, 'Awaiting processing by celery task.'),
        (PROCESSING_SUCCESSFUL, 'Item processed successfully.'),
        (PROCESSING_FAILED, 'Item encountered an error while processing.'),
    )
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
    court = models.ForeignKey(
        Court,
        help_text="The court where the upload was from",
        related_name='recap_processing_queue',
    )
    uploader = models.ForeignKey(
        User,
        help_text="The user that uploaded the item to RECAP.",
        related_name='recap_processing_queue',
    )
    pacer_case_id = models.CharField(
        help_text="The cased ID provided by PACER.",
        max_length=100,
    )
    document_number = models.CharField(
        help_text="If the file is a document, the number is the "
                  "document_number in RECAP docket.",
        max_length=32,
    )
    attachment_number = models.SmallIntegerField(
        help_text="If the file is an attachment, the number is the attachment "
                  "number in RECAP docket.",
        blank=True,
        null=True,
    )
    filepath_local = models.FileField(
        help_text="The path of the uploaded file.",
        upload_to=make_recap_processing_queue_path,
        storage=UUIDFileSystemStorage(),
        max_length=1000,
        blank=True,
    )
    status = models.SmallIntegerField(
        help_text="The current status of this upload.",
        choices=PROCESSING_STATUSES,
    )

    class Meta:
        permissions = (
            ("has_recap_upload_access", 'Can upload documents to RECAP.'),
        )
