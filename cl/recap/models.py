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
    PROCESSING_IN_PROGRESS = 4
    QUEUED_FOR_RETRY = 5
    PROCESSING_STATUSES = (
        (AWAITING_PROCESSING, 'Awaiting processing in queue.'),
        (PROCESSING_SUCCESSFUL, 'Item processed successfully.'),
        (PROCESSING_FAILED, 'Item encountered an error while processing.'),
        (PROCESSING_IN_PROGRESS, 'Item is currently being processed.'),
        (QUEUED_FOR_RETRY, 'Item failed processing, but will be retried.'),
    )
    DOCKET = 1
    ATTACHMENT_PAGE = 2
    PDF = 3
    UPLOAD_TYPES = (
        (DOCKET, 'HTML Docket'),
        (ATTACHMENT_PAGE, 'HTML attachment page'),
        (PDF, 'PDF'),
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
    pacer_doc_id = models.CharField(
        help_text="The ID of the document in PACER.",
        max_length=32,  # Same as in RECAP
        unique=True,
        blank=True,
    )
    document_number = models.CharField(
        help_text="The docket entry number for the document.",
        max_length=32,
        blank=True,
    )
    attachment_number = models.SmallIntegerField(
        help_text="If the file is an attachment, the number is the attachment "
                  "number on the docket.",
        blank=True,
        null=True,
    )
    filepath_local = models.FileField(
        help_text="The path of the uploaded file.",
        upload_to=make_recap_processing_queue_path,
        storage=UUIDFileSystemStorage(),
        max_length=1000,
    )
    status = models.SmallIntegerField(
        help_text="The current status of this upload. Possible values are: %s" %
                  ', '.join(['(%s): %s' % (t[0], t[1]) for t in
                             PROCESSING_STATUSES]),
        default=AWAITING_PROCESSING,
        choices=PROCESSING_STATUSES,
    )
    upload_type = models.SmallIntegerField(
        help_text="The type of object that is uploaded",
        choices=UPLOAD_TYPES,
    )
    error_message = models.TextField(
        help_text="Any errors that occurred while processing an item",
        blank=True,
    )

    def __unicode__(self):
        if self.upload_type == self.DOCKET:
            return u'ProcessingQueue %s: %s case #%s (%s)' % (
                self.pk,
                self.court_id,
                self.pacer_case_id,
                self.get_upload_type_display(),
            )
        elif self.upload_type == self.PDF:
            return u'ProcessingQueue %s: %s.%s.%s.%s (%s)' % (
                self.pk,
                self.court_id,
                self.pacer_case_id or None,
                self.document_number or None,
                self.attachment_number or 0,
                self.get_upload_type_display(),
            )

    class Meta:
        permissions = (
            ("has_recap_upload_access", 'Can upload documents to RECAP.'),
        )
