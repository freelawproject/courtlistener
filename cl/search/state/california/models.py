"""California state content models."""

from datetime import date
from typing import override

import pghistory
from django.db import models
from zoneinfo import ZoneInfo

from cl.lib.decorators import document_model
from cl.lib.model_helpers import CSVExportMixin
from cl.lib.models import AbstractDateTimeModel
from cl.lib.types import NonEmptyTuple
from cl.search.state.shared import AbstractStateDocument

CALIFORNIA_TIMEZONE = ZoneInfo("America/Los_Angeles")


class CADocumentType(models.IntegerChoices):
    """Normalized type of a California document."""

    UNKNOWN = 0, "Unknown"
    AMICUS_CURIAE_BRIEF = 1, "Amicus curiae brief"
    ANSWER_BRIEF_ON_THE_MERITS = (
        2,
        "Answer brief on the merits",
    )
    OPENING_BRIEF_ON_THE_MERITS = (
        3,
        "Opening brief on the merits",
    )
    REPLY_BRIEF_ON_THE_MERITS = (
        4,
        "Reply brief on the merits",
    )
    PETITION_FOR_REVIEW = 5, "Petition for review"
    SUPPLEMENTAL_BRIEF = 6, "Supplemental brief"
    REQUEST_FOR_JUDICIAL_NOTICE = (
        7,
        "Request for judicial notice",
    )
    ANSWER_TO_PETITION_FOR_REVIEW = (
        8,
        "Answer to petition for review",
    )
    RESPONSE_TO_AMICUS_CURIAE_BRIEF = (
        9,
        "Response to amicus curiae brief",
    )
    FOCUS_ISSUES_LETTER = 10, "Focus issues letter"
    REPLY_TO_ANSWER_TO_PETITION_FOR_REVIEW = (
        11,
        "Reply to answer to petition for review",
    )
    REPLY_BRIEF = 12, "Reply brief"
    BRIEF = 13, "Brief"
    OPENING_BRIEF = 14, "Opening brief"
    ADDITIONAL_AUTHORITIES_LETTER = (
        15,
        "Additional authorities letter",
    )
    OPPOSITION = 16, "Opposition"
    NOTICE_OF_ERRATA = 17, "Notice of errata"
    LETTER_BRIEF = 18, "Letter brief"
    REPLY_TO_SUPPLEMENTAL_BRIEF = (
        19,
        "Reply to supplemental brief",
    )
    SUPPLEMENTAL_REPLY_BRIEF = (
        20,
        "Supplemental reply brief",
    )
    SUPPLEMENTAL_LETTER_BRIEF = (
        21,
        "Supplemental letter brief",
    )
    REQUEST_TO_ANSWER_QUESTION_OF_STATE_LAW = (
        22,
        "Request to answer question of state law",
    )
    WRITTEN_RETURN = 23, "Written return"
    NEW_AUTHORITIES_LETTER = (
        24,
        "New authorities letter",
    )
    SUPPLEMENTAL_OPENING_BRIEF = (
        25,
        "Supplemental opening brief",
    )
    MOTION = 26, "Motion"
    TRAVERSE = 27, "Traverse"
    LETTER = 28, "Letter"
    JOINDER_TO_BRIEF_ON_THE_MERITS = (
        29,
        "Joinder to brief on the merits",
    )
    PETITION_FOR_WRIT_OF_HABEAS_CORPUS = (
        30,
        "Petition for writ of habeas corpus",
    )
    JOINDER_TO_PETITION = 31, "Joinder to petition"
    INFORMAL_RESPONSE = 32, "Informal response"
    RESPONSE_BRIEF_RE_REFEREES_REPORT = (
        33,
        "Response brief re referee's report",
    )
    REPLY_TO_INFORMAL_RESPONSE = (
        34,
        "Reply to informal response",
    )
    EXHIBITS = 35, "Exhibits"
    SUPPLEMENTAL_AUTHORITIES_LETTER = (
        36,
        "Supplemental authorities letter",
    )
    ORDER = 37, "Order"


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
    document_type = models.SmallIntegerField(
        choices=CADocumentType, default=CADocumentType.UNKNOWN
    )
    document_type_raw = models.TextField(blank=True)
    file_name = models.CharField(max_length=255)

    @classmethod
    def tmp_prefix(cls) -> str:
        """Prefix for temporary download files."""
        return "ca_"

    @classmethod
    def expected_extensions(cls) -> NonEmptyTuple[str]:
        """File extensions California is known to serve."""
        return (".pdf",)

    @override
    def path_date_filed(self) -> date | None:
        """Convert to California's local calendar day before storing."""
        if self.docket_entry.date_filed is None:
            return None
        return self.docket_entry.date_filed.astimezone(
            CALIFORNIA_TIMEZONE
        ).date()

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
