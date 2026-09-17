from datetime import date, datetime
from zoneinfo import ZoneInfo

import pghistory
from django.db import models

from cl.lib.decorators import document_model
from cl.lib.model_helpers import CSVExportMixin
from cl.lib.models import AbstractDateTimeModel
from cl.lib.types import NonEmptyTuple
from cl.search.state.shared import (
    AbstractStateDocument,
    DocketEntryType,
)

__all__ = ["FloridaDocketEntry", "FloridaDocument"]

# Florida ACIS timestamps are stored in UTC; filing dates in storage paths
# should reflect the court's local calendar day.
# The Florida Supreme Court and all six appellate courts are located in cities
# that use Eastern Time as of 09/17/2026
FLORIDA_TIMEZONE = ZoneInfo("America/New_York")


def florida_local_date(value: datetime | None) -> date | None:
    """Convert a Florida ACIS timestamp to the court's local filing date.

    :param value: A timezone-aware datetime as stored on FloridaDocketEntry,
        or None when the entry is undated.
    :return: The date in Florida's timezone, or None.
    """
    if value is None:
        return None
    return value.astimezone(FLORIDA_TIMEZONE).date()


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
    :ivar submitted_by: FK to the case party that submitted this document may be null if the party cannot be found.
    :ivar submitted_by_name: The name of the party that submitted this entry.
    :ivar status: Mapped from Florida's `entry_status` field. Can be "stricken",
    "vacated", or "docketed", or "unknown".
    :ivar docket_entry_uuid: Pulled directly from Florida results
    """

    STATUS_STRICKEN = 0
    STATUS_VACATED = 1
    STATUS_DOCKETED = 2
    STATUS_UNKNOWN = 3
    STATUS_CHOICES = (
        (STATUS_STRICKEN, "Stricken"),
        (STATUS_VACATED, "Vacated"),
        (STATUS_DOCKETED, "Docketed"),
        (STATUS_UNKNOWN, "Unknown"),
    )

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
    entry_type = models.SmallIntegerField(
        choices=DocketEntryType.CHOICES, default=DocketEntryType.UNKNOWN
    )
    entry_type_raw = models.TextField(blank=True)
    entry_name = models.TextField(blank=True)
    description = models.TextField(blank=True)
    submitted_by = models.ForeignKey(
        "people_db.Party",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    submitted_by_name = models.TextField(blank=True)
    status = models.SmallIntegerField(
        choices=STATUS_CHOICES, default=STATUS_UNKNOWN
    )
    docket_entry_uuid = models.UUIDField()

    class Meta:
        app_label = "search"
        ordering = ["-date_filed"]
        verbose_name_plural = "Florida Docket Entries"
        constraints = [
            models.UniqueConstraint(
                fields=["docket_entry_uuid", "docket"],
                name="unique_docket_entry_uuid_per_docket",
            )
        ]


@pghistory.track()
@document_model
class FloridaDocument(AbstractDateTimeModel, AbstractStateDocument):
    """
    Represents an attachment to a Florida docket entry.

    :ivar docket_entry: The Docket entry this document is associated with.
    :ivar content_type: The MIME type indicated by Florida ACIS
    :ivar document_name: The name of the document in Florida ACIS
    :ivar document_type: The type of the document in Florida ACIS
    :ivar link_uuid: The attachment link UUID retrieved from Florida ACIS. Used to generate document download URL.
    :ivar url: Download URL for attachment. Derived from uuid and link_uuid. Stored for safety.
    """

    docket_entry = models.ForeignKey(
        FloridaDocketEntry,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    content_type = models.CharField(max_length=255, blank=True)
    document_name = models.TextField(blank=True)
    document_type = models.TextField(blank=True)
    link_uuid = models.UUIDField()

    @classmethod
    def tmp_prefix(cls) -> str:
        """Prefix for temporary download files."""
        return "fl_"

    @classmethod
    def expected_extensions(cls) -> NonEmptyTuple[str]:
        """File extensions Florida ACIS is known to serve."""
        return ".pdf", ".tiff"

    @classmethod
    def extractable_extensions(cls) -> NonEmptyTuple[str]:
        """Extensions that can be sent to text extraction"""
        return (
            ".pdf",
            ".html",
            ".wpd",
            ".txt",
            ".tiff",
        )

    async def fetch_page_count(self) -> int | None:
        """Florida ACIS gives us the page count directly, so skip sending to the microservice."""
        return self.page_count

    class Meta:
        app_label = "search"
        ordering = ["link_uuid"]
        indexes = [
            models.Index(fields=["filepath_local"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["link_uuid", "docket_entry"],
                name="unique_link_uuid_per_docket_entry",
            )
        ]

    def path_date_filed(self) -> date | None:
        """ACIS entry timestamps are stored in UTC, so convert to Florida's
        local calendar day before it goes into the storage path."""
        return florida_local_date(self.docket_entry.date_filed)
