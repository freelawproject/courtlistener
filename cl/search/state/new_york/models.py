"""Models unique to New York Court of Appeals dockets.

Mirrors the per-court pattern established by Texas / SCOTUS:

- ``NYCoADocketEntry`` — a row from Court-PASS (FILINGS table or a
  synthesized "file-only" placeholder).
- ``NYCoADocument`` — the downloadable file attached to an entry,
  one-to-one. Inherits :class:`AbstractPDF` for the standard
  ``filepath_local`` / ``plain_text`` / ``sha1`` / ``page_count`` /
  ``file_size`` / ``ocr_status`` columns.

Other NY courts (App Div departments, Supreme Court, ...) will live
alongside in this package with their own ``<Court>...`` prefixed models
when added.
"""

import pghistory
from django.db import models

from cl.lib.decorators import document_model
from cl.lib.model_helpers import CSVExportMixin
from cl.lib.models import AbstractDateTimeModel, AbstractPDF

__all__ = ["NYCoADocketEntry", "NYCoADocument"]


@pghistory.track()
@document_model
class NYCoADocketEntry(AbstractDateTimeModel, CSVExportMixin):
    """A docket entry on a New York Court of Appeals docket.

    Sourced from Court-PASS. Two origins both shape into this model:
    the FILINGS table on the docket-detail page, and one synthesized
    entry per scraped file (Court-PASS doesn't deterministically link
    files to FILINGS rows; the merger keeps them as separate entries).

    :ivar docket: The Docket this entry belongs to.
    :ivar sequence_number: Stable ordering key. For FILINGS-derived
        entries it is the ISO date plus a zero-padded index; for
        file-only entries it is the literal "file." prefix plus a
        zero-padded file index. Disjoint by prefix so the natural key
        (docket, sequence_number) never collides across origins.
    :ivar date_filed: Date the entry was received by the court.
    :ivar description: Free-text description. For FILINGS entries the
        FILINGS row's filing_type concatenated with party; for
        file-only entries the file's display name.
    :ivar filing_type: Court-PASS filing-type string when known
        (Appellant Brief, Respondent Brief, etc.). Empty for file-only
        entries.
    :ivar party_side: Party-side label when known (Appellant,
        Respondent, Amicus Curiae, etc.). Empty for file-only entries.
    """

    docket = models.ForeignKey(
        "search.Docket",
        on_delete=models.CASCADE,
    )
    sequence_number = models.CharField(
        max_length=32,
    )
    date_filed = models.DateField(
        null=True,
        blank=True,
    )
    description = models.TextField(blank=True)
    filing_type = models.TextField(blank=True)
    party_side = models.TextField(blank=True)

    class Meta:
        # Django can't reliably determine which app the model lives in
        # when defined in a submodule — see
        # https://stackoverflow.com/a/20283983/22035917
        app_label = "search"
        ordering = ["-sequence_number"]
        unique_together = [["docket", "sequence_number"]]


@pghistory.track()
@document_model
class NYCoADocument(AbstractDateTimeModel, AbstractPDF):
    """A file attached to an NYCoA docket entry (Court-PASS).

    One-to-one with the synthesized file-only ``NYCoADocketEntry``.
    FILINGS-only entries have no attached document.

    :ivar docket_entry: The entry this file is attached to.
    :ivar file_name: Raw filename from Court-PASS's gvFiles row.
    :ivar file_index: 0-based position in the files table on the
        filing-detail page.
    """

    docket_entry = models.OneToOneField(
        NYCoADocketEntry, on_delete=models.CASCADE
    )
    file_name = models.TextField(blank=True)
    file_index = models.IntegerField(
        null=True,
        blank=True,
    )

    class Meta:
        app_label = "search"
        indexes = [models.Index(fields=["filepath_local"])]
