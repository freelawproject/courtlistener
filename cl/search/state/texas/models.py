"""Models unique to Texas dockets."""

import logging
from typing import IO

import pghistory
from django.db import models

from cl.corpus_importer.state.texas.utils import is_missing_file_page
from cl.lib.decorators import document_model
from cl.lib.model_helpers import CSVExportMixin
from cl.lib.models import AbstractDateTimeModel

__all__ = ["TexasDocketEntry", "TexasDocument"]

from cl.search.state.shared import AbstractStateDocument, ProcessingError

logger = logging.getLogger(__name__)


@pghistory.track()
@document_model
class TexasDocketEntry(AbstractDateTimeModel, CSVExportMixin):
    """
    Represents a docket entry in a Texas docket.

    :ivar docket: The Docket this entry is associated with.
    :ivar appellate_brief: Whether this entry appears in the
    "Appellate Brief" table in TAMES.
    :ivar description: For appellate brief events, a short description of
    the brief.
    :ivar remarks: Field unique to the Texas Supreme Court allowing
    commentary and notes on the entry.
    :ivar disposition: Text indicating whether a motion was dismissed, denied,
    or granted.
    :ivar date_filed: The date that TAMES indicates this entry was filed.
    :ivar entry_type: The type of entry from TAMES.
    :ivar sequence_number: CL-generated field to keep entries in the same
    order they appear in TAMES. Concatenation of filing date (in ISO format)
    and the index in the TAMES table.
    """

    docket = models.ForeignKey(
        "search.Docket",
        on_delete=models.CASCADE,
    )
    appellate_brief = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    disposition = models.TextField(blank=True)
    date_filed = models.DateField(
        null=True,
        blank=True,
    )
    entry_type = models.TextField()
    sequence_number = models.CharField(
        max_length=16,
    )

    class Meta:
        # Django can't reliably determine what app a model belongs to if it's
        # in a submodule
        # See: https://stackoverflow.com/a/20283983/22035917
        app_label = "search"
        ordering = ["-sequence_number"]
        # verbose_name_plural = "Texas Docket Entries"


EXPECTED_EXTENSIONS = {".pdf", ".html", ".wpd", ".mp3"}
EXTRACTABLE_EXTENSIONS = {".pdf", ".html", ".wpd"}


@pghistory.track()
@document_model
class TexasDocument(AbstractDateTimeModel, AbstractStateDocument):
    """
    Represents an attachment to a Texas docket entry.

    :ivar docket_entry: The Docket this document is associated with.
    :ivar description: The description of this file in TAMES.
    :ivar media_id: The MediaID parameter from the download URL that TAMES
    provided. Used to perform document merging.
    :ivar media_version_id: The MediaVersionID parameter from the download
    URL that TAMES provided. Used to perform document merging.
    :ivar url: The download URL that TAMES provided for this document.
    """

    docket_entry = models.ForeignKey(
        TexasDocketEntry, on_delete=models.CASCADE
    )
    description = models.TextField(blank=True)
    media_id = models.UUIDField()
    media_version_id = models.UUIDField()

    def make_filename(self) -> str:
        """Build the stored filename from the media ID and version ID."""
        return f"{self.media_id}-{self.media_version_id}"

    @classmethod
    def tmp_prefix(cls) -> str:
        """Prefix for temporary download files."""
        return "texas_"

    @classmethod
    def expected_extensions(cls) -> set[str]:
        """File extensions TAMES is known to serve."""
        return EXPECTED_EXTENSIONS

    def can_extract(self, extension: str) -> bool:
        """Whether text extraction supports files with this extension."""
        return extension in EXTRACTABLE_EXTENSIONS

    def validate_file(self, content: IO[bytes], extension: str) -> int | None:
        """Flag downloads where TAMES returned its "missing file" HTML page
        instead of the document, so the bad URL isn't retried."""
        if extension == ".html":
            content.seek(0, 2)
            file_size = content.tell()
            content.seek(0)
            if file_size <= 25_000:
                full_content = content.read()
                content.seek(0)
                if is_missing_file_page(full_content):
                    logger.warning(
                        "Texas document download: TexasDocument %s at %s returned a missing file page.",
                        self.pk,
                        self.url,
                    )
                    return ProcessingError.BAD_URL
        return None

    class Meta:
        app_label = "search"
        indexes = [
            models.Index(fields=["media_id"]),
            models.Index(fields=["filepath_local"]),
        ]
        unique_together = [["docket_entry", "media_id"]]
