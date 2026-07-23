from pathlib import Path

import pghistory
from django.db import models
from django.utils.text import slugify

from cl.lib.decorators import document_model
from cl.lib.model_helpers import CSVExportMixin
from cl.lib.models import AbstractDateTimeModel, AbstractPDF
from cl.search.state.shared import DocketEntryType, ProcessingError

__all__ = ["FloridaDocketEntry", "FloridaDocument"]


@pghistory.track()
@document_model
class FloridaDocketEntry(AbstractDateTimeModel, CSVExportMixin):
    """
    Represents a docket entry in a Florida docket.

    :ivar docket: The Docket this entry is associated with.
    :ivar date_filed: The filing date indicated by Florida ACIS
    :ivar date_submitted: Pulled directly from Florida results
    :ivar entry_type: Mirror of Juriscraper `DocketEntryType` enum.
    :ivar entry_type_raw: Value of `entry_type_raw` in Juriscraper results. Pulled from Florida API with no modification.
    :ivar entry_name: Pulled directly from Florida results
    :ivar description: Pulled directly from Florida results
    :ivar submitted_by: FK to the case party that submitted this document.
    :ivar status: Pulled directly from Florida's `entry_status` field
    :ivar docket_entry_uuid: Pulled directly from Florida results
    """

    docket = models.ForeignKey(
        "search.Docket",
        on_delete=models.CASCADE,
        related_name="florida_docket_entries",
    )
    date_filed = models.DateTimeField(
        null=True,
        blank=True,
    )
    date_submitted = models.DateTimeField(
        null=True,
        blank=True,
    )
    entry_type = models.SmallIntegerField(choices=DocketEntryType.CHOICES)
    entry_type_raw = models.TextField(blank=True)
    entry_name = models.TextField(blank=True)
    description = models.TextField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        "people_db.Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.TextField(blank=True)
    docket_entry_uuid = models.UUIDField()

    class Meta:
        app_label = "search"
        ordering = ["-date_filed"]
        indexes = [models.Index(fields=["docket_entry_uuid"])]
        verbose_name_plural = "Florida Docket Entries"
        constraints = [
            models.UniqueConstraint(
                fields=["docket", "docket_entry_uuid"],
                name="unique_docket_entry_uuid_per_docket",
            )
        ]


@pghistory.track()
@document_model
class FloridaDocument(AbstractDateTimeModel, AbstractPDF):
    """
    Represents an attachment to a Florida docket entry.

    :ivar docket_entry: The Docket entry this document is associated with.
    :ivar content_type: The MIME type indicated by Florida ACIS
    :ivar document_name: The name of the document in Florida ACIS
    :ivar document_type: The type of the document in Florida ACIS
    :ivar description: The description of the document in Florida ACIS
    :ivar link_uuid: The attachment link UUID retrieved from Florida ACIS. Used to generate document download URL.
    :ivar url: Download URL for attachment. Derived from uuid and link_uuid. Stored for safety.
    :ivar processing_error: The processing error for the document, if any.
    """

    docket_entry = models.ForeignKey(
        FloridaDocketEntry,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    content_type = models.CharField(max_length=63, null=True, blank=True)
    document_name = models.TextField(blank=True)
    document_type = models.TextField(blank=True)
    description = models.TextField(null=True, blank=True)
    link_uuid = models.UUIDField()
    url = models.URLField(max_length=250)
    processing_error = models.SmallIntegerField(
        choices=ProcessingError.CHOICES,
        null=True,
        blank=True,
    )

    class Meta:
        app_label = "search"
        ordering = ["link_uuid"]
        indexes = [models.Index(fields=["link_uuid"])]
        constraints = [
            models.UniqueConstraint(
                fields=["docket_entry", "link_uuid"],
                name="unique_link_uuid_per_docket_entry",
            )
        ]

    def get_pdf_path(self, filename: str, thumbs: bool = False) -> str:
        slug = slugify(Path(filename).stem)
        ext = Path(filename).suffix or ".pdf"
        court_id = self.docket_entry.docket.court_id
        directory = f"{court_id}-thumbnails" if thumbs else court_id
        return str(
            Path("us/state/fl") / directory / f"gov.fl.{court_id}.{slug}{ext}"
        )
