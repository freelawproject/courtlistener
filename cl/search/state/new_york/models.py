"""Models unique to New York Court of Appeals (Court-PASS) dockets."""

import pghistory
from django.db import models

from cl.lib.decorators import document_model
from cl.lib.model_helpers import CSVExportMixin
from cl.lib.models import AbstractDateTimeModel, AbstractPDF

__all__ = [
    "NYCoADocketMetadata",
    "NYCoADocketEntry",
    "NYCoADocument",
]


@pghistory.track()
class NYCoADocketMetadata(AbstractDateTimeModel):
    """New York Court of Appeals-specific metadata associated with a docket.

    These fields capture information that only applies to NYCoA cases, so we
    keep them in a separate model instead of adding them directly to the Docket
    namespace.
    """

    docket = models.OneToOneField(
        "search.Docket",
        help_text="The docket this NYCoA metadata applies to.",
        related_name="nycoa_metadata",
        on_delete=models.CASCADE,
    )
    issue = models.TextField(
        help_text=(
            "The issue categories the Court of Appeals associated with this "
            "case."
        ),
        blank=True,
    )
    summary = models.TextField(
        help_text="The detailed issue descriptions for this case.",
        blank=True,
    )
    decision_date = models.DateField(
        help_text="The date this case was decided, if it has been decided.",
        blank=True,
        null=True,
        auto_now=False,
    )
    opinion_by = models.TextField(
        help_text="The author of the opinion, for decided cases.",
        null=True,
        blank=True,
    )
    official_citation = models.CharField(
        help_text="The official citation, for decided cases.",
        max_length=255,
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return f"NYCoA metadata for docket {self.docket_id}"

    class Meta:
        app_label = "search"
        verbose_name = "NYCoA Docket Metadata"
        verbose_name_plural = "NYCoA Docket Metadata"


@pghistory.track()
@document_model
class NYCoADocketEntry(AbstractDateTimeModel, CSVExportMixin):
    """Represents a docket entry (filing) on a New York Court of Appeals docket.

    :ivar docket: The Docket this entry is associated with.
    :ivar page: The Court-PASS page this entry was scraped from. Entries are
    numbered independently per page, so two entries from different pages can
    share a ``sequence_number``; ``page`` is therefore part of the natural key.
    :ivar filing_type: The filing type from the Court-PASS FILINGS table
    (e.g. "Appellant Brief"). Blank for entries that only carry a document.
    :ivar party: The party associated with the filing, if any.
    :ivar date_received: The date Court-PASS recorded the filing as received.
    :ivar sequence_number: CL-generated field to keep entries in a stable
    order. Concatenation of a filing date (in ISO format) and the entry's
    per-page index, mirroring the convention used for Texas dockets.
    """

    class EntryPage(models.IntegerChoices):
        DOCUMENTS_PAGE = 1, "Documents page"
        FILINGS_PAGE = 2, "Filings page"

    docket = models.ForeignKey(
        "search.Docket",
        related_name="nycoa_docket_entries",
        on_delete=models.CASCADE,
    )
    page = models.IntegerField(
        help_text=(
            "The Court-PASS page this entry was scraped from. Entries are "
            "numbered independently per page, so this is part of the natural "
            "key."
        ),
        choices=EntryPage.choices,
    )
    filing_type = models.TextField(blank=True)
    party = models.TextField(blank=True)
    date_received = models.DateField(null=True, blank=True, auto_now=False)
    sequence_number = models.CharField(max_length=16)

    class Meta:
        app_label = "search"
        ordering = ["page", "sequence_number"]
        verbose_name_plural = "NYCoA Docket Entries"
        unique_together = [["docket", "page", "sequence_number"]]


@pghistory.track()
@document_model
class NYCoADocument(AbstractDateTimeModel, AbstractPDF):
    """Represents a file attached to a New York Court of Appeals docket entry.

    :ivar docket_entry: The docket entry this document is associated with.
    :ivar file_name: The filename as shown on the Court-PASS filing-detail
    page.
    :ivar document_number: The 1-based document number for the file, numbered
    from the bottom of the Court-PASS files table up.
    :ivar available: Whether the file is available (False for sealed or
    not-available files).
    """

    docket_entry = models.ForeignKey(
        NYCoADocketEntry,
        related_name="documents",
        on_delete=models.CASCADE,
    )
    file_name = models.TextField(blank=True)
    document_number = models.IntegerField()
    available = models.BooleanField(default=True)

    class Meta:
        app_label = "search"
        indexes = [
            models.Index(fields=["filepath_local"]),
        ]
        unique_together = [["docket_entry", "document_number"]]
