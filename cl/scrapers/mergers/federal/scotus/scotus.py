"""Pydantic schemas for merging SCOTUS-scraped dockets.

Second migration target for the merger framework, after Texas. The
classes here mirror the legacy ``merge_scotus_docket`` flow expressed
declaratively against the framework's primitives.

Scope:

- ``ScotusDocket`` (Aggregate) — root ``Docket`` row with SCOTUS-shaped
  scalar fields, ``source`` SCRAPER-bit OR via ``Custom`` strategy, and
  most optional fields as ``ScrapeWinsIfPresent`` so missing scraper
  values never clobber DB state.
- ``ScotusOCISchema`` (OwnedChild) — ``OriginatingCourtInformation``
  row tied to the docket via the forward FK on ``Docket``. ``Union``
  collection strategy so a re-scrape with no lower-court info doesn't
  delete an existing row.
- ``ScotusDocketMetadataSchema`` (InternalNode) — always-present
  per-docket ``ScotusDocketMetadata`` row. ``on_create`` /
  ``on_update`` hooks queue the QP PDF download follow-up when the
  scrape provides a URL and the DB row doesn't yet have a stored file.
- ``ScotusDocketEntrySchema`` (InternalNode, ``allow_duplicates=True``)
  — numbered + unnumbered entries. The framework's bipartite
  minimum-edit-cost pairing handles unnumbered minute entries
  (``entry_number=None``) that share an NK.
- ``ScotusDocumentSchema`` (InternalNode) — per-entry attachments.
  ``on_create`` / ``on_update`` queue the existing
  ``download_scotus_document_pdf`` → ``extract_pdf_document`` chain on
  insert *or* when the URL-derived filename changes.
- Party / attorney / role / org subtree — parallel to Texas. Same
  Django models, same matching rules; declared as SCOTUS-prefixed
  subclasses so each merger's resolution cache stays scoped to itself.

Caller responsibilities (driver-side):

- Resolve ``court`` to the pre-existing ``Court(pk="scotus")``
  instance and pass it as ``PreResolvedRef[Court]``.
- Resolve ``appeal_from`` by name via
  ``cl.lib.courts.find_court_object_by_name`` (or pass ``None``).
- Convert "missing" scraper values to ``None`` (not ``""``) so
  ``ScrapeWinsIfPresent`` correctly preserves DB state.
- For each scraped party, normalize attorney contact via
  ``cl.lib.pacer.normalize_attorney_contact`` to compute the
  ``lookup_key`` (only attached if non-empty) and the parsed
  email/phone/fax.
- Compute ``sequence_number`` for each entry via
  ``cl.corpus_importer.utils.create_docket_entry_sequence_numbers``
  (keyed on ``date_filed``).
- Number per-entry attachments sequentially (1-indexed) before
  constructing ``ScotusDocumentSchema`` instances.

See cl/scrapers/MERGERS_SCOTUS_SANITY.md for the design walkthrough.
"""

from datetime import date
from typing import Annotated, Any
from urllib.parse import urljoin

from cl.corpus_importer.utils import extract_file_name_from_url
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
    FollowUp,
    InternalNode,
    ExternalNodeRef,
    OwnedChild,
    PreResolvedRef,
    ScrapeWins,
    ScrapeWinsIfPresent,
    Union,
    parent,
)
from cl.search.models import (
    Court,
    Docket,
    OriginatingCourtInformation,
    SCOTUSDocketEntry,
    SCOTUSDocument,
    ScotusDocketMetadata,
)


# ---------------------------------------------------------------------------
# Custom strategy: SCRAPER source-bit OR
# ---------------------------------------------------------------------------


def _or_scraper_bit(scrape: int, db: int | None) -> int:
    """Bitwise-OR the SCRAPER bit into ``Docket.source`` on update.

    On create the scraper passes ``source=Docket.SCRAPER`` directly
    and this strategy isn't consulted (``CreateOp`` uses scrape values
    verbatim); on update we OR in the bit so re-scraping a docket
    originally sourced from RECAP / Harvard compounds the bits rather
    than clobbering them.
    """
    return (db or 0) | Docket.SCRAPER


# ---------------------------------------------------------------------------
# Follow-up: QP PDF download
# ---------------------------------------------------------------------------


def _download_qp_pdf_chain(pk: int) -> None:
    """Run after-commit by the caller: kick off the QP PDF download
    for the given ``ScotusDocketMetadata.pk``.

    Lazy-imports the Celery task so schema import doesn't pull Celery
    transitively into contexts that don't need it.
    """
    from cl.corpus_importer.tasks import download_qp_scotus_pdf

    # The legacy task takes a Docket pk, not a metadata pk; the caller
    # bridges by reading metadata.docket_id off the row.
    metadata = ScotusDocketMetadata.objects.only("docket_id").get(pk=pk)
    download_qp_scotus_pdf.delay(metadata.docket_id)


# ---------------------------------------------------------------------------
# Follow-up: SCOTUS document download + extract
# ---------------------------------------------------------------------------


def _scotus_document_download_and_extract_chain(pk: int) -> None:
    """Run after-commit by the caller: kick off the SCOTUS document
    download + plain-text extraction chain.

    Same pattern as the Texas document follow-up — lazy-imports
    Celery to keep schema imports cheap.
    """
    from celery import chain

    from cl.corpus_importer.tasks import download_scotus_document_pdf
    from cl.scrapers.tasks import extract_pdf_document

    chain(
        download_scotus_document_pdf.si(pk),
        extract_pdf_document.s(
            check_if_needed=False, model_name="search.SCOTUSDocument"
        ),
    ).apply_async()


# ---------------------------------------------------------------------------
# ScotusDocument (leaf)
# ---------------------------------------------------------------------------


class ScotusDocumentSchema(InternalNode[SCOTUSDocument]):
    """A per-entry SCOTUS document attachment.

    Matched by ``(docket_entry, document_number, attachment_number)``
    — the same Django ``unique_together``. ``on_create`` queues the
    download/extract chain; ``on_update`` only re-fires it when the
    URL-derived filename actually changes (this mirrors the legacy
    "did the file source change?" check via
    ``extract_file_name_from_url``).
    """

    natural_key = (
        parent.docket_entry,
        "document_number",
        "attachment_number",
    )

    document_number: int | None = None
    attachment_number: int | None = None
    description: str = ""
    url: str

    def on_create(self, new_db: SCOTUSDocument) -> Any:
        return [
            FollowUp(
                name="scotus-document-download-and-extract",
                fn=_scotus_document_download_and_extract_chain,
                args=(new_db.pk,),
            )
        ]

    def on_update(
        self,
        old_db: SCOTUSDocument | None,
        new_db: SCOTUSDocument | None,
    ) -> Any:
        # Same dispatch rationale as ``ScotusDocketMetadataSchema``:
        # framework hands us ``old_db=None`` for create, so route to
        # ``on_create`` explicitly since we've overridden default
        # dispatch.
        if old_db is None:
            return self.on_create(new_db) if new_db is not None else None
        if new_db is None:
            return self.on_delete(old_db)
        if extract_file_name_from_url(
            old_db.url or ""
        ) != extract_file_name_from_url(new_db.url or ""):
            return [
                FollowUp(
                    name="scotus-document-download-and-extract",
                    fn=_scotus_document_download_and_extract_chain,
                    args=(new_db.pk,),
                )
            ]
        return None


# ---------------------------------------------------------------------------
# ScotusDocketEntry
# ---------------------------------------------------------------------------


class ScotusDocketEntrySchema(
    InternalNode[SCOTUSDocketEntry],
    allow_duplicates=True,
):
    """A SCOTUS docket entry — numbered or unnumbered.

    NK is ``(parent.docket, "entry_number")``. ``entry_number`` is
    ``None`` for minute entries; multiple such entries on the same
    docket collide on the NK, so ``allow_duplicates=True`` engages
    the framework's bipartite minimum-edit-cost pairing. Non-NK
    scalars (``description``, ``date_filed``, ``sequence_number``)
    contribute to the cost function so the right scraped row pairs
    with the right DB row even within the ``None`` bucket.
    """

    natural_key = (parent.docket, "entry_number")

    entry_number: int | None = None
    description: str = ""
    date_filed: date | None = None
    sequence_number: str

    # Django's default reverse-accessor name on SCOTUSDocketEntry for
    # SCOTUSDocument.docket_entry (no related_name set on the FK).
    # ``Union`` mirrors legacy ``merge_scotus_document``, which is
    # ``get_or_create``-based and never deletes DB-only documents on
    # re-scrape.
    scotusdocument_set: Annotated[
        list[ScotusDocumentSchema], Union
    ] = []


# ---------------------------------------------------------------------------
# ScotusOCISchema (OwnedChild, ``Union`` so partial fills never delete)
# ---------------------------------------------------------------------------


class ScotusOCISchema(OwnedChild[OriginatingCourtInformation]):
    """Originating-court information for a SCOTUS docket.

    SCOTUS dockets reference a lower court (the appellate court below
    SCOTUS); the legacy merger only populated OCI when at least one of
    ``lower_court_case_numbers`` / ``lower_court_decision_date`` /
    ``lower_court_rehearing_denied_date`` was present, and never
    deleted an existing OCI on a re-scrape that lacked lower-court
    info. The driver expresses that contract by passing ``None`` for
    the OCI field when none of those source fields are populated;
    fields here use ``ScrapeWinsIfPresent`` so partial fills compose
    cleanly with prior values.

    Only the four SCOTUS-relevant OCI columns are declared — fields
    used by other mergers (``assigned_to``, ``court_reporter``, etc.)
    aren't touched by the SCOTUS pipeline.
    """

    # Defaults are "" (not None) for the text columns so the
    # framework's CREATE-path None→default coercion produces an
    # empty string instead of NULL — ``OriginatingCourtInformation``
    # has ``TextField(blank=True)`` on both columns (NOT NULL with
    # implicit empty default). On UPDATE, ``ScrapeWinsIfPresent``
    # still preserves DB values when the scrape passes ``None``.
    docket_number: Annotated[str | None, ScrapeWinsIfPresent] = ""
    docket_number_raw: Annotated[str | None, ScrapeWinsIfPresent] = ""
    date_judgment: Annotated[date | None, ScrapeWinsIfPresent] = None
    date_rehearing_denied: Annotated[
        date | None, ScrapeWinsIfPresent
    ] = None


# ---------------------------------------------------------------------------
# ScotusDocketMetadata (always-present singleton child)
# ---------------------------------------------------------------------------


def _resolve_qp_url(url: str | None) -> str | None:
    """Resolve a SCOTUS QP URL: relative ``../qp/14-00556qp.pdf``
    paths get joined against the SCOTUS base URL. ``None`` and empty
    pass through untouched.
    """
    if not url:
        return None
    if url.startswith("http"):
        return url
    return urljoin("https://www.supremecourt.gov/", url)


class ScotusDocketMetadataSchema(InternalNode[ScotusDocketMetadata]):
    """Per-docket SCOTUS metadata row.

    NK is the parent docket; one row per docket (a 0-or-1 collection
    on ``Docket.scotus_metadata``). ``capital_case`` uses ``ScrapeWins``
    (the scrape's boolean is authoritative since it's always
    deterministic from the source); other fields use
    ``ScrapeWinsIfPresent`` so absent values don't clobber.

    The ``questions_presented_url`` field carries a normalized
    absolute URL — the driver (which has the Juriscraper dict) calls
    ``_resolve_qp_url`` before constructing the schema instance.

    Lifecycle hook ``on_update`` queues the QP-PDF download follow-up
    when the new row has a URL and the prior row had no stored file.
    ``on_create`` does the same for new rows (treating the prior file
    as empty).
    """

    natural_key = (parent.docket,)

    capital_case: bool = False
    date_discretionary_court_decision: date | None = None
    # Text fields default to "" so the create-path coercion handles
    # ``None`` cleanly (``ScotusDocketMetadata`` has these as
    # ``CharField(blank=True)`` / ``CharField(blank=True, default="")``
    # — both NOT NULL).
    linked_with: Annotated[str | None, ScrapeWinsIfPresent] = ""
    questions_presented_url: Annotated[
        str | None, ScrapeWinsIfPresent
    ] = ""

    def on_create(self, new_db: ScotusDocketMetadata) -> Any:
        return self._maybe_download_qp(new_db, prev_file="")

    def on_update(
        self,
        old_db: ScotusDocketMetadata | None,
        new_db: ScotusDocketMetadata | None,
    ) -> Any:
        # Framework calls ``on_update`` for every row mutation,
        # passing ``old_db=None`` on CreateOp and ``new_db=None`` on
        # DeleteOp. Dispatch to ``on_create`` / ``on_delete``
        # explicitly since we've overridden the default Node dispatch.
        if old_db is None:
            return self.on_create(new_db) if new_db is not None else None
        if new_db is None:
            return self.on_delete(old_db)
        return self._maybe_download_qp(
            new_db, prev_file=old_db.questions_presented_file
        )

    def _maybe_download_qp(
        self, new_db: ScotusDocketMetadata, prev_file: Any
    ) -> Any:
        if new_db.questions_presented_url and not prev_file:
            return [
                FollowUp(
                    name="scotus-qp-download",
                    fn=_download_qp_pdf_chain,
                    args=(new_db.pk,),
                )
            ]
        return None


# ---------------------------------------------------------------------------
# Parties + party-types
# ---------------------------------------------------------------------------


class ScotusPartyRef(
    ExternalNodeRef[Party],
    absence_policy=CreateIfMissing,
):
    """A reference to a ``Party`` row for a SCOTUS docket.

    Path-scoped via ``party_types__party`` and ``role_set__party``
    from the root docket. Matched by ``name`` only — the legacy
    SCOTUS code (via ``add_parties_and_attorneys``) does the same.
    """

    natural_key = ("name",)

    name: str


class ScotusPartyTypeSchema(InternalNode[PartyType]):
    """A SCOTUS-side ``PartyType`` row: the join between this docket
    and a party with a role string (``Petitioner``, ``Respondent``,
    ``Other`` from the SCOTUS dataset)."""

    natural_key = (parent.docket, "party", "name")

    party: ScotusPartyRef
    name: str
    date_terminated: date | None = None
    extra_info: str = ""


# ---------------------------------------------------------------------------
# Attorneys + roles
# ---------------------------------------------------------------------------


class ScotusAttorneyRef(
    ExternalNodeRef[Attorney],
    absence_policy=CreateIfMissing,
):
    """An ``Attorney`` reference for a SCOTUS docket.

    Matched by name with path-scoping via ``role_set__attorney`` and
    ``attorneyorganizationassociation_set__attorney``. Contact fields
    use ``ScrapeWinsIfPresent`` so a later appearance with no contact
    info (``None``) doesn't clobber an earlier appearance that had
    real data — matches legacy ``add_attorney`` which skips its
    ``a.save()`` when the source contact string is falsy.

    The driver MUST pass ``None`` (not ``""``) when a contact field
    is absent — empty strings would still ``ScrapeWinsIfPresent``-win
    because the strategy only treats ``None`` as missing (see the
    None-convention note in MERGERS_IN_THEORY.md).
    """

    natural_key = ("name",)

    name: str
    contact_raw: Annotated[str | None, ScrapeWinsIfPresent] = ""
    email: Annotated[str | None, ScrapeWinsIfPresent] = ""
    phone: Annotated[str | None, ScrapeWinsIfPresent] = ""
    fax: Annotated[str | None, ScrapeWinsIfPresent] = ""


class ScotusRoleSchema(InternalNode[Role]):
    """A SCOTUS ``Role`` row linking party + attorney + docket with a
    role int.

    Flat child of ``ScotusDocket`` (same as Texas — the legacy logic
    keys roles by ``(party, attorney, docket)`` directly, not through
    ``PartyType``)."""

    natural_key = (parent.docket, "party", "attorney", "role_raw")

    party: ScotusPartyRef
    attorney: ScotusAttorneyRef
    role: int = 0
    role_raw: str = ""
    date_action: date | None = None


# ---------------------------------------------------------------------------
# Attorney organizations + per-docket associations
# ---------------------------------------------------------------------------


class ScotusAttorneyOrgRef(
    ExternalNodeRef[AttorneyOrganization],
    absence_policy=CreateIfMissing,
    path_scoped=False,
):
    """``AttorneyOrganization`` lookup keyed by globally-unique
    ``lookup_key``. ``path_scoped=False`` so the resolver hits the
    table globally instead of pretending the row is reachable from
    this docket alone."""

    natural_key = ("lookup_key",)

    lookup_key: str
    name: str = ""
    address1: str = ""
    address2: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""


class ScotusAttorneyOrgAssociationSchema(
    InternalNode[AttorneyOrganizationAssociation],
):
    """Docket-scoped attorney ↔ org link, mirroring the Django
    ``unique_together`` on ``AttorneyOrganizationAssociation``."""

    natural_key = (parent.docket, "attorney", "attorney_organization")

    attorney: ScotusAttorneyRef
    attorney_organization: ScotusAttorneyOrgRef


# ---------------------------------------------------------------------------
# ScotusDocket (root)
# ---------------------------------------------------------------------------


class ScotusDocket(
    Aggregate[Docket],
    default_field=ScrapeWins,
    lock_for_update=True,
):
    """Root schema for a SCOTUS-scraped docket.

    Natural key: ``("court", "docket_number")`` — *no* ``_core``
    variant (SCOTUS docket numbers like ``22-145`` round-trip
    cleanly without normalization, unlike Texas).

    Field strategies:

    - Required identity columns (``docket_number``, ``docket_number_raw``)
      use the class default ``ScrapeWins``.
    - Optional scalars (``case_name``, ``date_filed``,
      ``appeal_from``, ``appeal_from_str``) use ``ScrapeWinsIfPresent``
      so a re-scrape that drops a value won't clobber a real DB value.
    - ``source`` uses ``Custom(_or_scraper_bit)`` to OR the SCRAPER
      bit on update; create-path callers set ``source=Docket.SCRAPER``
      directly.

    1:1 children:

    - ``originating_court_information``: OwnedChild OCI; ``Union``
      strategy on the 0-or-1 collection so a partial scrape doesn't
      drop existing lower-court info.
    - ``scotus_metadata``: InternalNode that's *always* present per
      SCOTUS docket; the driver always supplies one (even with all
      fields ``None``).

    N children:

    - ``scotusdocketentry_set``: docket entries, allow_duplicates for
      the unnumbered-minute-entry case.
    - ``party_types``, ``role_set``, ``attorneyorganizationassociation_set``:
      ``Union`` (additive) — legacy ``add_parties_and_attorneys``
      never deletes DB-only rows.
    """

    natural_key = ("court", "docket_number")

    court: PreResolvedRef[Court]
    docket_number: str
    docket_number_raw: str

    # Text fields on Docket are ``TextField(blank=True)`` — defaults
    # to "" so the create-path coercion produces an empty string when
    # the driver signals "no scrape value" via ``None``.
    case_name: Annotated[str | None, ScrapeWinsIfPresent] = ""
    date_filed: Annotated[date | None, ScrapeWinsIfPresent] = None
    appeal_from: Annotated[
        PreResolvedRef[Court] | None, ScrapeWinsIfPresent
    ] = None
    appeal_from_str: Annotated[str | None, ScrapeWinsIfPresent] = ""

    source: Annotated[int, Custom(_or_scraper_bit)] = 0

    # 0-or-1 children. ``Union`` for OCI mirrors the legacy "only
    # touch if lower-court info present, never delete on absence."
    originating_court_information: Annotated[
        ScotusOCISchema | None, Union
    ] = None
    # ScotusDocketMetadata uses the explicit related_name on its FK,
    # so the field name here matches Django's reverse accessor.
    scotus_metadata: ScotusDocketMetadataSchema | None = None

    # Entries: see ScotusDocketEntrySchema for the allow_duplicates
    # rationale. ``Union`` mirrors legacy ``add_scotus_docket_entries``
    # which iterates over scrape only — DB-only entries are never
    # deleted by a re-merge. Field name follows Django's default
    # reverse-accessor convention.
    scotusdocketentry_set: Annotated[
        list[ScotusDocketEntrySchema], Union
    ] = []

    # Party / Attorney / Org subtree — ``Union`` so DB-only rows stay
    # put (matches legacy ``add_parties_and_attorneys`` behavior).
    party_types: Annotated[
        list[ScotusPartyTypeSchema], Union
    ] = []
    role_set: Annotated[list[ScotusRoleSchema], Union] = []
    attorneyorganizationassociation_set: Annotated[
        list[ScotusAttorneyOrgAssociationSchema], Union
    ] = []
