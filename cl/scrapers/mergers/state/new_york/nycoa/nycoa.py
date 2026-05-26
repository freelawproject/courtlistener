"""Pydantic schemas for merging NYCoA Court-PASS scrapes.

Mirrors the SCOTUS / Texas pattern, adapted for the Court-PASS data
shape:

- ``NYCoADocket`` (Aggregate) — root ``Docket`` row keyed by
  ``(court, docket_number)``. ``ScrapeWinsIfPresent`` on all optional
  scalar fields so re-scrapes that drop a value don't clobber DB state.
- ``NYCoADocketEntrySchema`` (InternalNode) — entries from both the
  FILINGS table and the synthesized one-per-file pass. ``sequence_number``
  is the disambiguator; ``allow_duplicates=False`` because the driver
  pre-disambiguates collisions by prefixing the sequence number with
  ``f"file."`` for file-only entries.
- ``NYCoADocumentSchema`` (InternalNode) — one-to-one with the file
  DocketEntry. ``on_create`` / ``on_update`` emit an ``IngestFile``
  follow-up so the post-merge pipeline pulls the file from S3,
  consults doctor for the suffix, and extracts plain text.
- Party / Attorney / Org subtree — uses the SCOTUS-style global
  ExternalNodeRef pattern (matched by name, no docket-path scoping). New
  rows get created via ``CreateIfMissing``.

Issues / issue_details / opinion_by / official_citation / oral
arguments are intentionally out of scope for the first cut — see the
``NYCoADocket`` docstring for the rationale.
"""

from datetime import date
from typing import Annotated, Any

from cl.people_db.models import (
    Attorney,
    AttorneyOrganization,
    AttorneyOrganizationAssociation,
    Party,
    PartyType,
    Role,
)
from cl.scrapers.mergers import (
    Aggregate,
    CreateIfMissing,
    Custom,
    IngestFile,
    InternalNode,
    ExternalNodeRef,
    PreResolvedRef,
    ScrapeWins,
    ScrapeWinsIfPresent,
    Union,
    parent,
)
from cl.search.models import Court, Docket
from cl.search.state.new_york.models import NYCoADocketEntry, NYCoADocument

# S3 bucket the kent runs land in. Same bucket as Texas/SCOTUS — the
# storage backend handles auth + region. The driver concatenates this
# with each file's local_path to form an ``s3://...`` URL in IngestFile.
_NYCOA_S3_BUCKET = "com-courtlistener-storage"


# ---------------------------------------------------------------------------
# Custom strategy: SCRAPER source-bit OR (same pattern as SCOTUS/Texas)
# ---------------------------------------------------------------------------


def _or_scraper_bit(scrape: int, db: int | None) -> int:
    """OR the SCRAPER bit into ``Docket.source`` on update so re-scraping
    a docket originally sourced from RECAP / Harvard compounds the bits
    rather than clobbering them. Create-path uses scrape value directly.
    """
    return (db or 0) | Docket.SCRAPER


# ---------------------------------------------------------------------------
# NYCoADocument (leaf with IngestFile follow-up)
# ---------------------------------------------------------------------------


class NYCoADocumentSchema(InternalNode[NYCoADocument]):
    """A scraped file attached to a synthesized DocketEntry.

    Matched by parent docket_entry alone (the parent entry is 1:1 with
    this row by construction — the driver creates exactly one file-only
    DocketEntry per NYCourtPassFile).

    On create or on path change, emits an :class:`IngestFile`
    follow-up so the post-merge pipeline fetches the file from S3,
    asks doctor for the canonical suffix, and (for extractable types)
    extracts plain text into the row's ``plain_text`` column.
    """

    natural_key = (parent.docket_entry,)

    file_name: str = ""
    file_index: int | None = None
    # ``filepath_local`` mirrors AbstractPDF's column. Kent already
    # gives us the S3 key; we store it directly on create so doctor's
    # ``microservice(item=instance)`` helper can open the file.
    filepath_local: str = ""

    def _ingest_for(self, new_db: NYCoADocument) -> list[IngestFile]:
        """Build the IngestFile follow-up for ``new_db``. Skipped when
        the row has no S3 path — there's nothing to ingest.
        """
        key = new_db.filepath_local.name if new_db.filepath_local else ""
        if not key:
            return []
        return [
            IngestFile(
                storage_url=f"s3://{_NYCOA_S3_BUCKET}/{key}",
                model_label="search.NYCoADocument",
                pk=new_db.pk,
            )
        ]

    def on_create(self, new_db: NYCoADocument) -> Any:
        return self._ingest_for(new_db)

    def on_update(
        self,
        old_db: NYCoADocument | None,
        new_db: NYCoADocument | None,
    ) -> Any:
        # Framework dispatches all row mutations through ``on_update``
        # (with ``old_db=None`` on create, ``new_db=None`` on delete).
        # Route create / delete explicitly since we override the
        # default Node dispatch.
        if old_db is None:
            return self.on_create(new_db) if new_db is not None else None
        if new_db is None:
            return self.on_delete(old_db)
        # On update, only re-ingest when the stored path changed —
        # otherwise the existing plain_text/sha1/etc. are still correct.
        old_key = old_db.filepath_local.name if old_db.filepath_local else ""
        new_key = new_db.filepath_local.name if new_db.filepath_local else ""
        if old_key != new_key:
            return self._ingest_for(new_db)
        return None


# ---------------------------------------------------------------------------
# NYCoADocketEntry
# ---------------------------------------------------------------------------


class NYCoADocketEntrySchema(InternalNode[NYCoADocketEntry]):
    """A docket entry on an NYCoA docket.

    NK is ``(parent.docket, sequence_number)``. The driver synthesizes
    ``sequence_number`` with two disjoint prefixes so FILINGS-derived
    rows and file-only rows never collide:

    - FILINGS-derived: ``f"{date_received_iso}.{idx:03d}"`` (or
      ``"0000-00-00.{idx:03d}"`` if the FILINGS row has no date).
    - File-only: ``f"file.{file_index:03d}"``.

    File-only entries carry a 1:1 ``NYCoADocumentSchema`` child; FILINGS
    entries do not (Court-PASS doesn't deterministically link FILINGS
    rows to downloadable files).
    """

    natural_key = (parent.docket, "sequence_number")

    sequence_number: str
    date_filed: Annotated[date | None, ScrapeWinsIfPresent] = None
    description: Annotated[str | None, ScrapeWinsIfPresent] = ""
    filing_type: Annotated[str | None, ScrapeWinsIfPresent] = ""
    party_side: Annotated[str | None, ScrapeWinsIfPresent] = ""

    # Reverse-accessor name for the OneToOneField on NYCoADocument.
    # The default Django reverse accessor on a OneToOneField is the
    # lowercased model name.
    nycoadocument: NYCoADocumentSchema | None = None


# ---------------------------------------------------------------------------
# Parties + party-types
# ---------------------------------------------------------------------------


class NYCoAPartyRef(
    ExternalNodeRef[Party],
    absence_policy=CreateIfMissing,
    path_scoped=False,
):
    """Global ``Party`` lookup by name. ``path_scoped=False`` so the
    resolver hits the Party table globally — Court-PASS party names
    like "People of the State of New York" or "Acme Corp" recur across
    thousands of dockets, and we want a single Party row per name
    rather than per docket."""

    natural_key = ("name",)

    name: str


class NYCoAPartyTypeSchema(InternalNode[PartyType]):
    """A PartyType row joining this docket to a party with a role-name
    string (Appellant / Respondent / Amicus Curiae)."""

    natural_key = (parent.docket, "party", "name")

    party: NYCoAPartyRef
    name: str
    date_terminated: date | None = None
    extra_info: str = ""


# ---------------------------------------------------------------------------
# Attorneys + roles
# ---------------------------------------------------------------------------


class NYCoAAttorneyRef(
    ExternalNodeRef[Attorney],
    absence_policy=CreateIfMissing,
    path_scoped=False,
):
    """Global ``Attorney`` lookup by name. ``path_scoped=False`` so the
    table is searched globally rather than via the path through this
    docket. Contact fields populate on create only — matched-row
    updates are not refreshed."""

    natural_key = ("name",)

    name: str
    contact_raw: str = ""
    phone: str = ""


class NYCoARoleSchema(InternalNode[Role]):
    """A ``Role`` row linking party + attorney + docket. Court-PASS only
    gives us the party_role string (Appellant / Respondent / Amicus
    Curiae); ``role`` (the int) stays at its default since Court-PASS
    has no PACER-style role taxonomy."""

    natural_key = (parent.docket, "party", "attorney", "role_raw")

    party: NYCoAPartyRef
    attorney: NYCoAAttorneyRef
    role: int = 0
    role_raw: str = ""
    date_action: date | None = None


# ---------------------------------------------------------------------------
# Attorney organizations + per-docket associations
# ---------------------------------------------------------------------------


class NYCoAAttorneyOrgRef(
    ExternalNodeRef[AttorneyOrganization],
    absence_policy=CreateIfMissing,
    path_scoped=False,
):
    """``AttorneyOrganization`` lookup keyed by globally-unique
    ``lookup_key`` (firm-name + address). ``path_scoped=False`` so the
    resolver hits the table globally."""

    natural_key = ("lookup_key",)

    lookup_key: str
    name: str = ""
    address1: str = ""
    address2: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""


class NYCoAAttorneyOrgAssociationSchema(
    InternalNode[AttorneyOrganizationAssociation],
):
    """Docket-scoped attorney ↔ org link."""

    natural_key = (parent.docket, "attorney", "attorney_organization")

    attorney: NYCoAAttorneyRef
    attorney_organization: NYCoAAttorneyOrgRef


# ---------------------------------------------------------------------------
# NYCoADocket (root)
# ---------------------------------------------------------------------------


class NYCoADocket(
    Aggregate[Docket],
    default_field=ScrapeWins,
    lock_for_update=True,
):
    """Root schema for an NYCoA Court-PASS scrape.

    Natural key: ``("court", "docket_number")``. Court-PASS docket
    numbers like ``APL-2024-00177`` round-trip cleanly, so no
    ``_core`` normalization variant is needed (unlike Texas).

    Intentional omissions for the first iteration:

    - ``issues`` / ``issue_details`` arrays carried inline on
      NYCourtPassDocket are dropped — CL has no native field for
      free-text issue categorization on Docket.
    - ``opinion_by`` and ``official_citation`` scalars from the docket
      are dropped — they belong on OpinionCluster, not Docket; the
      Opinion-side merge is a separate concern.
    - Oral-argument recordings are skipped — the .wmv files live on a
      Court-PASS HTTP host, not in our S3.
    """

    natural_key = ("court", "docket_number")

    court: PreResolvedRef[Court]
    docket_number: str
    docket_number_raw: str

    case_name: Annotated[str | None, ScrapeWinsIfPresent] = ""
    case_name_short: Annotated[str | None, ScrapeWinsIfPresent] = ""
    case_name_full: Annotated[str | None, ScrapeWinsIfPresent] = ""
    date_argued: Annotated[date | None, ScrapeWinsIfPresent] = None
    date_filed: Annotated[date | None, ScrapeWinsIfPresent] = None

    source: Annotated[int, Custom(_or_scraper_bit)] = 0

    # Entries: both FILINGS-derived and file-only synthesized rows
    # share this list. The driver assigns disjoint sequence_number
    # prefixes so the NK never collides. ``Union`` so DB-only rows
    # aren't deleted by a re-scrape that drops them.
    nycoadocketentry_set: Annotated[
        list[NYCoADocketEntrySchema], Union
    ] = []

    # Party / Attorney / Org subtree. ``Union`` so DB-only rows stay
    # put — Court-PASS docket re-scrapes can drop attorneys (e.g.
    # appearance withdrawn) without us deleting CL history.
    party_types: Annotated[list[NYCoAPartyTypeSchema], Union] = []
    role_set: Annotated[list[NYCoARoleSchema], Union] = []
    attorneyorganizationassociation_set: Annotated[
        list[NYCoAAttorneyOrgAssociationSchema], Union
    ] = []
