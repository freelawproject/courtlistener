"""Models unique to New York Court of Appeals (Court-PASS) dockets."""

from pathlib import Path
from typing import Self

import pghistory
from django.db import models

from cl.lib.decorators import document_model
from cl.lib.model_helpers import CSVExportMixin
from cl.lib.models import AbstractDateTimeModel
from cl.search.state.new_york.vocabularies import (
    ISSUE_CATEGORY_CHOICES,
    ISSUE_SUBCATEGORY_CHOICES,
    UNKNOWN,
    FilingDocType,
    FilingRole,
    FilingType,
)
from cl.search.state.shared import AbstractStateDocument

__all__ = [
    "NYCoADocketEntry",
    "NYCoADocketIssue",
    "NYCoADocketMetadata",
    "NYCoADocument",
]


@pghistory.track()
@document_model
class NYCoADocketMetadata(AbstractDateTimeModel):
    """
    Represents the New York Court of Appeals-specific metadata for a docket.

    These fields only apply to NYCoA cases, so they live here instead of
    widening the shared `Docket` model.

    The issues the Court assigned to the case hang off this model, one row
    each, as `NYCoADocketIssue`.

    :ivar docket: The Docket this NYCoA metadata applies to.
    :ivar decision_date: The date this case was decided, if it has been
    decided.
    :ivar official_citation: The official citation, for decided cases.
    :ivar lower_court_citation: The "Reported Below" citation for the decision
    under review, when Court-PASS reports one.
    """

    docket = models.OneToOneField(
        "search.Docket",
        on_delete=models.CASCADE,
        related_name="nycoa_metadata",
    )
    decision_date = models.DateField(null=True, blank=True)
    official_citation = models.CharField(max_length=255, blank=True)
    lower_court_citation = models.CharField(max_length=255, blank=True)

    class Meta:
        app_label = "search"
        verbose_name = "NYCoA Docket Metadata"
        verbose_name_plural = "NYCoA Docket Metadata"

    def __str__(self) -> str:
        return f"NYCoA metadata for docket {self.docket_id}"


@pghistory.track()
@document_model
class NYCoADocketIssue(AbstractDateTimeModel):
    """
    Represents one issue the New York Court of Appeals assigned to a case.

    The Court states an issue as a category and a subcategory joined by a
    double dash, and describes most of them in a paragraph of detail. A case
    usually has one issue but may have several.

    :ivar metadata: The NYCoA docket metadata this issue belongs to.
    :ivar category: The issue's category.
    :ivar subcategory: The issue's subcategory. Unknown on the issues the Court
    states as a bare category.
    :ivar category_raw: The issue exactly as Court-PASS stated it, category and
    subcategory together.
    :ivar detail: The Court's description of the issue. Blank when Court-PASS
    stated none. Deliberately outside the key, because the Court does assign a
    case two issues under one category pair, told apart only by this, and it
    also rewords a description it has already published, so which of the two a
    scrape is looking at is the merger's call rather than the database's.
    """

    metadata = models.ForeignKey(
        NYCoADocketMetadata,
        on_delete=models.CASCADE,
        related_name="issues",
    )
    category = models.SmallIntegerField(
        choices=ISSUE_CATEGORY_CHOICES, default=UNKNOWN
    )
    subcategory = models.SmallIntegerField(
        choices=ISSUE_SUBCATEGORY_CHOICES, default=UNKNOWN
    )
    category_raw = models.TextField(blank=True)
    detail = models.TextField(blank=True)

    class Meta:
        app_label = "search"
        ordering = ["category_raw"]
        verbose_name = "NYCoA Docket Issue"
        verbose_name_plural = "NYCoA Docket Issues"
        indexes = [
            # Serves the merger's lookup of the issues already stored for a
            # docket. Not unique: a case can carry two issues under one
            # category pair, so the merger picks create or update from
            # `detail`, which is too long to key on and gets reworded anyway.
            models.Index(
                fields=["metadata", "category", "subcategory"],
                name="nycoa_issue_category_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.pk}: {self.category_raw}"


@pghistory.track()
@document_model
class NYCoADocketEntry(AbstractDateTimeModel, CSVExportMixin):
    """
    Represents a docket entry in a New York Court of Appeals docket.

    An entry is either a row from the FILINGS table on the Court-PASS docket
    page or a filing the scraper reconstructed from a document the FILINGS
    table never listed, which is expected for motion papers, Appellate Division
    material, and the court's own decisions, transcripts, and oral argument
    webcasts. A reconstructed filing has no `filing_type_raw`, because no table
    row named it.

    :ivar docket: The Docket this entry is associated with.
    :ivar docket_entry_id: The identifier for this entry, unique within the
    docket and stable across scrapes. Composed from the filing type and party
    for a FILINGS table row, and from the role, party, and document type for
    an entry reconstructed from a document.
    :ivar entry_index: The position of this entry in the source listing.
    Reproduces the order Court-PASS displayed, but shifts between scrapes
    because new rows are inserted above existing ones, so it is not an
    identifier.
    :ivar filing_type: The type of filing the FILINGS table listed. Unknown on
    a reconstructed filing, whose role and document type are still recorded.
    :ivar filing_type_raw: The filing type exactly as the FILINGS table
    rendered it. Blank when no table row listed this filing.
    :ivar filing_role: The role of the party that made this filing.
    :ivar filing_doctype: The kind of document this filing consists of.
    :ivar filing_type_recognized: Whether the filing type resolved to a known
    role and document type. False on an entry taken from the FILINGS table
    means Court-PASS used a filing type we do not recognize yet.
    :ivar party: FK to the case party associated with this filing. May be null
    if the party cannot be found.
    :ivar party_name: The party as the FILINGS table named it. Court-PASS only
    identifies a party's attorneys elsewhere on the page, so `party` stays null
    for a party with no attorney of record; this preserves the name either way.
    :ivar date_filed: The date Court-PASS recorded this filing as received.
    Null on entries reconstructed from a document, which carry no date.
    :ivar date_due: The date Court-PASS recorded this filing as due.
    """

    docket = models.ForeignKey(
        "search.Docket",
        on_delete=models.CASCADE,
        related_name="nycoa_docket_entries",
    )
    docket_entry_id = models.TextField()
    entry_index = models.IntegerField(null=True, blank=True)
    filing_type = models.SmallIntegerField(
        choices=FilingType.choices, default=UNKNOWN
    )
    filing_type_raw = models.TextField(blank=True)
    filing_role = models.SmallIntegerField(
        choices=FilingRole.choices, default=UNKNOWN
    )
    filing_doctype = models.SmallIntegerField(
        choices=FilingDocType.choices, default=UNKNOWN
    )
    filing_type_recognized = models.BooleanField(default=False)
    party = models.ForeignKey(
        "people_db.Party",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nycoa_docket_entries",
    )
    party_name = models.TextField(blank=True)
    date_filed = models.DateField(null=True, blank=True)
    date_due = models.DateField(null=True, blank=True)

    class Meta:
        app_label = "search"
        ordering = ["date_filed", "entry_index"]
        verbose_name_plural = "NYCoA Docket Entries"
        indexes = [
            # Serves the docket page's `WHERE docket_id = ... ORDER BY
            # date_filed, entry_index`. The unique constraint below cannot do
            # this job: it is keyed on `docket_entry_id`, which shares no
            # prefix with the sort.
            models.Index(
                fields=["docket", "date_filed", "entry_index"],
                name="nycoa_entry_docket_order_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["docket", "docket_entry_id"],
                name="unique_nycoa_entry_id_per_docket",
            )
        ]


@pghistory.track()
@document_model
class NYCoADocument(AbstractDateTimeModel, AbstractStateDocument):
    """
    Represents a document attached to a New York Court of Appeals docket entry.

    :ivar docket_entry: The Docket entry this document is associated with.
    :ivar url: Not stored. Court-PASS serves every document by POST from one
    endpoint, the same for every download, so it identifies nothing.
    :ivar file_name: The name of the file as Court-PASS published it. Filers
    are expected to follow the Court's naming convention, which encodes the
    party role, party name, and document type.
    :ivar content_type: The MIME type of the file. Court-PASS publishes PDFs
    along with playlist files for oral argument recordings.
    :ivar available: Whether the file can be downloaded. False for sealed
    files and files the site lists but does not serve.
    :ivar doc_role: The party role encoded in the file name, e.g. "appellant".
    Blank when the file name does not follow the naming convention.
    :ivar doc_party: The party name encoded in the file name. Blank when the
    file name does not follow the naming convention.
    :ivar doc_type: The document type encoded in the file name, e.g. "brf".
    Values beginning with an underscore are the court's own output rather than
    a party filing. Blank when the file name does not follow the naming
    convention.
    :ivar volume: The volume number, for a record or appendix published in
    several volumes.
    :ivar part: The part number, for a volume that is itself split into parts.
    """

    docket_entry = models.ForeignKey(
        NYCoADocketEntry,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file_name = models.TextField()
    content_type = models.CharField(max_length=255, blank=True)
    available = models.BooleanField(default=True)
    doc_role = models.TextField(blank=True)
    doc_party = models.TextField(blank=True)
    doc_type = models.TextField(blank=True)
    volume = models.IntegerField(null=True, blank=True)
    part = models.IntegerField(null=True, blank=True)

    def make_filename(self) -> str:
        """Build the stored filename from the docket entry and file name.

        Overridden because the base implementation derives the name from
        `url`, which is one shared POST endpoint for all of Court-PASS and so
        would name every document identically. The entry plus file name is the
        document's natural key, so it is unique and stable across scrapes.
        """
        return f"{self.docket_entry_id}-{Path(self.file_name).stem}"

    @classmethod
    def tmp_prefix(cls) -> str:
        """Prefix for temporary download files."""
        return "nycoa_"

    @classmethod
    def download(
        cls, pk: int, extract: bool = True, queue: str = "celery"
    ) -> Self | None:
        """Always raises: Court-PASS documents cannot be fetched by URL.

        The inherited implementation GETs `url`, which for Court-PASS is one
        POST endpoint shared by every document; the document is identified by
        form data, and only within a session the site has handed a cookie.
        Fetching one takes the Court-PASS scraper, so this raises rather than
        silently GETting the endpoint and storing whatever comes back.

        Takes the base signature so a caller reaching it through
        `AbstractStateDocument` gets the error rather than a `TypeError`.

        :param pk: Unused; the primary key the base implementation would load.
        :param extract: Unused; see the base implementation.
        :param queue: Unused; see the base implementation.
        """
        raise NotImplementedError(
            "NYCoADocument cannot be downloaded by URL; Court-PASS serves "
            "documents by POST from a single session-scoped endpoint."
        )

    class Meta:
        app_label = "search"
        ordering = ["file_name"]
        indexes = [
            models.Index(fields=["filepath_local"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["docket_entry", "file_name"],
                name="unique_nycoa_file_name_per_docket_entry",
            )
        ]

    def get_pdf_path(self, filename: str, thumbs: bool = False) -> str:
        """Store Court-PASS documents under the shared state layout."""
        return self.state_pdf_path(
            "ny", self.docket_entry.docket.court_id, filename, thumbs
        )
