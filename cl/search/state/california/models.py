"""California state content models."""

import pghistory
from django.db import models

from cl.lib.decorators import document_model
from cl.lib.model_helpers import CSVExportMixin
from cl.lib.models import AbstractDateTimeModel
from cl.lib.types import NonEmptyTuple
from cl.search.state.shared import AbstractStateDocument


@pghistory.track()
@document_model
class CaliforniaDocketEntry(AbstractDateTimeModel, CSVExportMixin):
    """Represents a docket entry in a California docket.

    Attributes:
        docket: The Docket this entry is associated with.
        brief: Whether this entry appears in the "Briefs" table.
        description: The value in the description column on CA's site.
        notes: The value in the notes column on CA's site.
        date_filed: Date filed column from briefs table (when available).
        submitted_by: FK to the case party that submitted this document may be null if the party cannot be found (when available).
        submitted_by_name: The name of the party that submitted this entry (when available).
    """

    docket = models.ForeignKey(
        "search.Docket",
        on_delete=models.CASCADE,
        related_name="california_docket_entries",
    )
    brief = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    date_filed = models.DateTimeField(
        null=True,
        blank=True,
    )
    submitted_by = models.ForeignKey(
        "people_db.Party",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    submitted_by_name = models.TextField(blank=True)

    class Meta:
        app_label = "search"
        ordering = ["-date_filed"]
        verbose_name_plural = "California Docket Entries"


@pghistory.track()
@document_model
class CaliforniaDocument(AbstractDateTimeModel, AbstractStateDocument):
    """Represents an attachment to a California docket entry.

    Attributes:
        docket_entry: The Docket entry this document is associated with.
        document_number: Preserves ordering between scrape and DB
        description: A short description of the brief.
        document_type: Normalized document type (enum)
        document_type_raw: Raw document type text
        file_name: Name of the file provided by CA
    """

    docket_entry = models.ForeignKey(
        CaliforniaDocketEntry,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_number = models.SmallIntegerField()
    description = models.TextField(blank=True)
    document_type = models.SmallIntegerField()
    document_type_raw = models.TextField(blank=True)
    file_name = models.CharField(max_length=255)

    @classmethod
    def tmp_prefix(cls) -> str:
        """Prefix for temporary download files."""
        return "ca_"

    @classmethod
    def expected_extensions(cls) -> NonEmptyTuple[str]:
        """File extensions California is known to serve."""
        raise NotImplementedError

    @classmethod
    def extractable_extensions(cls) -> NonEmptyTuple[str]:
        """Extensions that can be sent to text extraction."""
        raise NotImplementedError

    class Meta:
        app_label = "search"
        ordering = ["document_number"]
        indexes = [
            models.Index(fields=["filepath_local"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["docket_entry", "document_number"],
                name="unique_document_number_per_docket_entry",
            )
        ]
