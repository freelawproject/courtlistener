"""Pydantic schema for merging TAMES-scraped Texas dockets.

This is the first migration target for the merger framework. The Pydantic
classes here mirror the shape of the existing
``cl.corpus_importer.tasks.merge_texas_docket()`` flow but expressed
declaratively against the framework's Aggregate / InternalNode primitives.

Current scope:

- ``TexasDocket`` (Aggregate) — root Docket row with scalar fields and
  the ``source`` SCRAPER-bit OR via Custom strategy.
- ``TexasDocketEntrySchema`` (InternalNode) — entries; ``allow_duplicates``
  handles the (date, type, appellate_brief) collision case by
  pair-by-min-edit-cost (sequence_number contributes to the cost
  function).
- ``TexasDocumentSchema`` (InternalNode) — documents under entries.
  ``custom_class_update`` clears ``filepath_local`` / ``ocr_status`` /
  ``processing_error`` when ``media_version_id`` changes. ``on_update``
  emits the existing ``download_texas_document`` →
  ``extract_formatted_text_document`` Celery chain as a follow-up.

Deferred to subsequent iterations (each documented inline at the
relevant spot):

- ``OriginatingCourtInformation`` 1:1 child
- ``TrialCourtData`` (Supreme Court only)
- Parties / attorneys subtree
- ``CaseTransfer`` (cross-aggregate; needs ``OriginatingTransfer`` and
  ``DestinationTransfer`` subclasses)
- Appellate-docket disaggregation (handled caller-side per the theory
  doc; not a framework concern)

Callers (scraper code) are responsible for:

- Resolving ``court`` and ``appeal_from`` to ``Court`` instances via
  ``cl.corpus_importer.utils.texas_js_court_id_to_court_id``,
  ``texas_originating_court_to_court_id``, and
  ``cl.lib.courts.find_court_object_by_name`` before constructing the
  schema.
- Computing ``docket_number_core`` via
  ``cl.lib.model_helpers.make_texas_docket_number_core``.
- Computing per-entry ``sequence_number`` via
  ``cl.corpus_importer.utils.create_docket_entry_sequence_numbers``.
- Pairing scraped ``case_events`` with ``appellate_briefs`` (the existing
  zip-iter pattern) before constructing entry schemas.
- For appellate Texas dockets: doing the texapp-disaggregation lookup
  before invoking ``merge_one`` (in the same transaction).
"""

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from cl.people_db.models import (
    Attorney,
    AttorneyOrganization,
    AttorneyOrganizationAssociation,
    Party,
    PartyType,
    Person,
    Role,
)
from cl.scrapers.mergers import (
    Aggregate,
    BridgeNode,
    CreateIfMissing,
    Custom,
    FollowUp,
    InternalNode,
    ExternalNodeRef,
    OwnedChild,
    PreResolvedRef,
    ScrapeClobbers,
    ScrapeWins,
    ScrapeWinsIfPresent,
    Union,
    parent,
)
from cl.search.models import (
    CaseTransfer,
    Court,
    Docket,
    OriginatingCourtInformation,
    TrialCourtData,
)
from cl.search.state.texas.models import TexasDocketEntry, TexasDocument


# ---------------------------------------------------------------------------
# Custom strategies
# ---------------------------------------------------------------------------


def _or_scraper_bit(scrape: int, db: int | None) -> int:
    """Bitwise-OR the SCRAPER bit into Docket.source on update.

    For the create path, the scraper provides ``source=Docket.SCRAPER``
    directly and this strategy isn't consulted (CreateOp uses scrape
    values verbatim).
    """
    return (db or 0) | Docket.SCRAPER


# ---------------------------------------------------------------------------
# Document follow-up
# ---------------------------------------------------------------------------


def _texas_document_download_and_extract_chain(pk: int) -> None:
    """Run after-commit by the caller: kick off the Celery chain that
    downloads the document PDF and extracts its text.

    Lazy-imports Celery + the task modules to avoid pulling them in at
    schema-import time (helps when the framework is used from contexts
    that don't have Celery configured).
    """
    from celery import chain

    from cl.corpus_importer.tasks import download_texas_document
    from cl.scrapers.tasks import extract_formatted_text_document

    chain(
        download_texas_document.si(pk),
        extract_formatted_text_document.s(
            check_if_needed=False,
            model_name="search.TexasDocument",
            strip_html_tags=True,
        ),
    ).apply_async()


# ---------------------------------------------------------------------------
# TexasDocument (leaf)
# ---------------------------------------------------------------------------


class TexasDocumentSchema(InternalNode[TexasDocument]):
    """A document attachment under a Texas docket entry.

    Matching uses ``(docket_entry, media_id)`` — the (UUID) media_id is
    the stable identifier provided by TAMES.

    Cross-field invariant: when ``media_version_id`` changes, the
    stored file becomes stale, so ``filepath_local``, ``ocr_status``,
    and ``processing_error`` must be cleared. Expressed via
    ``custom_class_update``.

    On insert or version change, queues the existing
    ``download_texas_document`` → ``extract_formatted_text_document``
    chain as a follow-up.
    """

    natural_key = (parent.docket_entry, "media_id")

    media_id: UUID
    media_version_id: UUID
    description: str = ""
    url: str

    def custom_class_update(
        self,
        scraped: "TexasDocumentSchema",
        db: TexasDocument | None,
    ) -> TexasDocument:
        """Build the desired DB state. On version change clear the
        local-file / OCR / processing fields so the row is treated as
        "needs re-download" downstream."""
        new_db = db if db is not None else TexasDocument()
        new_db.media_id = scraped.media_id
        new_db.media_version_id = scraped.media_version_id
        new_db.description = scraped.description
        new_db.url = scraped.url
        version_changed = (
            db is None or db.media_version_id != scraped.media_version_id
        )
        if version_changed:
            new_db.filepath_local = ""
            new_db.ocr_status = None
            new_db.processing_error = None
        return new_db

    def on_update(
        self,
        old_db: TexasDocument | None,
        new_db: TexasDocument | None,
    ) -> Any:
        """Queue download + extract when the document is new or its
        ``media_version_id`` changed.

        Handles the delete boundary explicitly (``new_db=None``);
        the create boundary (``old_db=None``) falls through to the
        version-change branch which fires for any new row.
        """
        if new_db is None:
            return self.on_delete(old_db)
        if old_db is None or (
            old_db.media_version_id != new_db.media_version_id
        ):
            return [
                FollowUp(
                    name="texas-document-download-and-extract",
                    fn=_texas_document_download_and_extract_chain,
                    args=(new_db.pk,),
                )
            ]
        return None


# ---------------------------------------------------------------------------
# TexasDocketEntry
# ---------------------------------------------------------------------------


class TexasDocketEntrySchema(
    InternalNode[TexasDocketEntry],
    allow_duplicates=True,
):
    """A Texas docket entry.

    NK is ``(parent.docket, date_filed, entry_type, appellate_brief)``;
    the existing merger had to fall back to ``sequence_number`` when
    those four fields collided. With ``allow_duplicates=True``, the
    framework's bipartite minimum-edit-cost pairing handles the same
    case: ``sequence_number`` is a non-NK field, so identical
    sequence_numbers contribute 0 to the cost and same-sequence rows
    pair preferentially.
    """

    natural_key = (
        parent.docket,
        "date_filed",
        "entry_type",
        "appellate_brief",
    )

    date_filed: date | None = None
    entry_type: str
    appellate_brief: bool = False
    sequence_number: str
    description: str = ""
    disposition: str = ""
    remarks: str = ""

    # Django's default reverse-accessor name on ``TexasDocketEntry``
    # for ``TexasDocument.docket_entry`` (no ``related_name`` set on
    # the FK). ``Union`` mirrors legacy ``merge_texas_document``,
    # which only creates / updates per scraped attachment and never
    # deletes DB-only documents on a re-scrape.
    texasdocument_set: Annotated[
        list[TexasDocumentSchema], Union
    ] = []


# ---------------------------------------------------------------------------
# OriginatingCourtInformation (parent-owned 1:1)
# ---------------------------------------------------------------------------


class TexasOCISchema(OwnedChild[OriginatingCourtInformation]):
    """Originating-court information for a Texas docket.

    OCI is the appellate-side recording of the lower court that
    produced the case — distinct from ``TrialCourtData`` (which lives
    on the trial court side for some SC cases).

    The Django relationship is ``Docket.originating_court_information``,
    a forward OneToOneField — so the FK column lives on ``Docket`` and
    we use ``OwnedChild`` to express that the framework should
    pre-materialize this row and inject its PK as the parent's FK.

    Judge: the caller pre-resolves via
    ``lookup_judge_by_full_name_and_set_attr`` and passes a ``Person``
    instance (or ``None``). ``ScrapeWinsIfPresent`` keeps any existing
    DB value when the caller's lookup fails.
    """

    docket_number: str = ""
    docket_number_raw: str = ""
    court_reporter: str = ""
    assigned_to_str: str = ""
    assigned_to: Annotated[
        PreResolvedRef[Person] | None, ScrapeWinsIfPresent
    ] = None


# ---------------------------------------------------------------------------
# TrialCourtData (Supreme Court only — child→parent FK)
# ---------------------------------------------------------------------------


class TexasTrialCourtDataSchema(InternalNode[TrialCourtData]):
    """Trial-court metadata attached to a Texas SC docket.

    ``TrialCourtData.docket`` is a ``OneToOneField`` to ``Docket``
    *without* an explicit ``related_name``, so Django's reverse
    accessor is the lowercase model name ``trialcourtdata``. The
    Pydantic field on ``TexasDocket`` is named ``trialcourtdata`` to
    match — slightly awkward but avoids a model migration. Adding
    ``related_name="trial_court_data"`` to the Django field would
    let us rename the Pydantic field.

    Judge and court are pre-resolved by the caller (same pattern as
    OCI's ``assigned_to``); ``ScrapeWinsIfPresent`` preserves DB
    values when the caller's lookup fails.

    Set ``trialcourtdata=None`` (or omit) on non-Supreme-Court
    Texas dockets; the framework treats ``T | None`` as a 0-or-1
    collection and leaves the row alone (under default
    ``ScrapeClobbers``, a ``None`` scrape with an existing DB row
    would delete it — non-issue on the typical Texas data shape but
    note it for safety).
    """

    natural_key = (parent.docket,)

    docket_number_trial: str = ""
    docket_number_raw_trial: str = ""
    judge_str: str = ""
    judge: Annotated[
        PreResolvedRef[Person] | None, ScrapeWinsIfPresent
    ] = None
    reporter: str = ""
    court_name: str = ""
    court: Annotated[
        PreResolvedRef[Court] | None, ScrapeWinsIfPresent
    ] = None
    punishment: str = ""
    county: str = ""
    date_filed: date | None = None


# ---------------------------------------------------------------------------
# Parties + party-types
# ---------------------------------------------------------------------------


class TexasPartyRef(
    ExternalNodeRef[Party],
    absence_policy=CreateIfMissing,
):
    """A reference to a ``cl.people_db.Party`` row.

    Parties are *docket-scoped*: the framework's path-scoped ExternalNodeRef
    resolution walks ``party_types__party`` from the matched root
    docket, so a Party named "John Smith" attached to a *different*
    docket won't accidentally be reused for this one. If no match,
    ``CreateIfMissing`` inserts a new ``Party`` row before the
    referencing ``PartyType`` is created.

    Note: the legacy ``add_parties_and_attorneys`` does a name match
    here without any normalization beyond what
    ``normalize_texas_parties`` provides at parse time. The caller is
    expected to keep that pre-merge normalization in place when
    constructing scrape instances.
    """

    natural_key = ("name",)

    name: str


class TexasPartyTypeSchema(InternalNode[PartyType]):
    """A ``PartyType`` row — the (docket, party, role) join with
    optional metadata.

    NK is ``(parent.docket, party, name)``. ``party`` is a
    ``SiblingRef`` so the framework needs the resolved Party PK (or
    the to-be-created identity) to compute the pairing key — the
    framework's bipartite-ish keying handles this via the
    ``_sibling_identity`` mechanism. ``name`` is the role string
    (``Defendant``, ``Plaintiff``, ...) that ``normalize_texas_parties``
    fills in at parse time.

    Non-NK scalars (``date_terminated``, ``extra_info``) update on
    matched rows under the default ``ScrapeWins``.

    Deferred: attorneys / roles / attorney organizations. The legacy
    ``add_parties_and_attorneys`` populates Attorney + Role +
    AttorneyOrganization + AttorneyOrganizationAssociation rows; until
    we model that subtree the caller should continue to invoke the
    legacy code for attorney handling after the new merger runs.
    """

    natural_key = (parent.docket, "party", "name")

    party: TexasPartyRef
    name: str  # role string — distinct from ``party.name`` (the person)
    date_terminated: date | None = None
    extra_info: str = ""


# ---------------------------------------------------------------------------
# Attorneys + roles
# ---------------------------------------------------------------------------


class TexasAttorneyRef(
    ExternalNodeRef[Attorney],
    absence_policy=CreateIfMissing,
):
    """A reference to a ``cl.people_db.Attorney`` row.

    Attorneys are matched by ``name`` (the legacy
    ``add_parties_and_attorneys`` does the same — no normalization
    beyond what the caller does at parse time).

    Path-scoped via ``role_set__attorney`` *and*
    ``attorneyorganizationassociation_set__attorney`` from the root
    docket. The framework unions candidate rows across every declared
    path to the ``ExternalNodeRef`` class (de-duped by PK), so an attorney
    reachable via either path resolves correctly.

    Contact fields (``contact_raw``, ``email``, ``phone``, ``fax``)
    are populated on the *create* path from the values the caller
    pre-computes via ``cl.lib.pacer.normalize_attorney_contact``.
    **They do not update existing matched rows** — that's the
    ExternalNodeRef-field-update framework gap. Until that lands, callers
    who need to refresh contact info on existing attorneys should
    keep invoking the legacy ``add_attorney`` path.
    """

    natural_key = ("name",)

    name: str
    contact_raw: str = ""
    email: str = ""
    phone: str = ""
    fax: str = ""


class TexasRoleSchema(InternalNode[Role]):
    """A ``Role`` row linking a Party + Attorney to a Docket with a
    specific role string.

    Modeled as a *flat* child of ``TexasDocket`` rather than nested
    under a PartyType, because ``Role`` FKs to ``party`` + ``attorney``
    + ``docket`` directly — there's no FK to ``PartyType``. The
    framework's SiblingRef machinery handles the (party, attorney)
    keying via resolved ExternalNodeRef PKs.

    Django's default reverse-accessor name on ``Docket`` is
    ``role_set`` (no explicit ``related_name`` on ``Role.docket``),
    so the Pydantic field on ``TexasDocket`` is named ``role_set``.
    Like ``trialcourtdata``, this is cosmetic and would clear up if
    the Django field grew an explicit ``related_name``.

    Attorney organizations (``AttorneyOrganization`` /
    ``AttorneyOrganizationAssociation``) are *not* yet modeled — the
    legacy ``add_parties_and_attorneys`` does address-parsing to
    populate them, and replacing that is out of scope for this
    iteration.
    """

    natural_key = (parent.docket, "party", "attorney", "role_raw")

    party: TexasPartyRef
    attorney: TexasAttorneyRef
    # ``Role.role`` is nullable in the DB; legacy stores ``None`` when
    # ``normalize_attorney_role`` doesn't recognize the role string
    # (e.g. ``"LEAD_ATTORNEY"`` with an underscore doesn't match
    # "lead attorney" with a space). Mirror that so parity tests pass.
    role: int | None = None
    role_raw: str = ""
    date_action: date | None = None


# ---------------------------------------------------------------------------
# Attorney organizations + per-docket associations
# ---------------------------------------------------------------------------


class TexasAttorneyOrgRef(
    ExternalNodeRef[AttorneyOrganization],
    absence_policy=CreateIfMissing,
    path_scoped=False,
):
    """Reference to an ``AttorneyOrganization`` matched by
    ``lookup_key``.

    ``AttorneyOrganization`` has a globally-unique ``lookup_key`` (a
    trimmed/normalized rendering of the org's address), so this
    ExternalNodeRef is declared ``path_scoped=False``. The resolver issues
    a single batched global query keyed by ``lookup_key``; misses
    fall through to ``CreateIfMissing`` (matching the legacy
    ``get_or_create``-with-race-recovery flow).

    Address fields are populated on the *create* path only — matched
    rows are left alone. That mirrors the legacy behavior (the
    legacy ``add_attorney`` only updates contact info on the
    ``Attorney`` row, never on the org itself).

    Caller responsibility: produce ``lookup_key`` and the address
    fields via ``cl.lib.pacer.normalize_attorney_contact``; only
    construct this ref when the returned ``atty_org_info`` dict is
    non-empty (the legacy code skips org/association creation when
    address parsing yielded nothing).
    """

    natural_key = ("lookup_key",)

    lookup_key: str
    name: str = ""
    address1: str = ""
    address2: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""


class TexasAttorneyOrgAssociationSchema(
    InternalNode[AttorneyOrganizationAssociation],
):
    """A docket-scoped link between an Attorney and an
    AttorneyOrganization.

    Modeled as a flat child of ``TexasDocket`` (parallel to
    ``TexasRoleSchema``) because the ``AttorneyOrganizationAssociation``
    row FKs to ``attorney``, ``attorney_organization``, and ``docket``
    directly — no FK to ``Role`` or ``PartyType``. The Django
    ``unique_together`` is exactly ``(attorney, attorney_organization,
    docket)``, so this NK matches the row identity.

    Django's default reverse-accessor name on ``Docket`` is
    ``attorneyorganizationassociation_set`` (no explicit
    ``related_name`` on ``AttorneyOrganizationAssociation.docket``),
    so the Pydantic field on ``TexasDocket`` follows that name.
    Cosmetic only — a small migration adding ``related_name`` would
    let us rename.

    No non-FK fields exist on this model; the row is essentially a
    presence flag. ``Union`` strategy on the parent's list field
    (additive — never delete DB-only rows) matches the legacy
    ``get_or_create`` behavior.
    """

    natural_key = (parent.docket, "attorney", "attorney_organization")

    attorney: TexasAttorneyRef
    attorney_organization: TexasAttorneyOrgRef


# ---------------------------------------------------------------------------
# CaseTransfer (cross-aggregate bridge)
# ---------------------------------------------------------------------------
#
# ``CaseTransfer`` straddles two ``Docket`` aggregates — its FK
# columns ``origin_docket`` and ``destination_docket`` point to two
# (typically different) ``Docket`` rows. This is the canonical
# ``BridgeNode`` shape:
#
# - Identity is global by NK (the 6-tuple of routing keys, sans
#   docket FKs). When two paired dockets are merged in sequence, the
#   second merge's NK lookup finds the half-filled row the first
#   merge inserted.
# - Lifecycle is parent-owned by *each* side (the FK column lives on
#   the bridge), but neither side deletes the bridge if scrape stops
#   mentioning it — default-collection is ``Union``.
# - Parent FK auto-injection: the framework derives the FK column
#   name on ``CaseTransfer`` from the parent Pydantic field name on
#   ``TexasDocket`` (``case_transfer_origin_docket`` →
#   ``origin_docket``, similarly for destination), so the schema body
#   doesn't carry the docket-FK fields.


_CASE_TRANSFER_NK = (
    "origin_court",
    "origin_docket_number",
    "destination_court",
    "destination_docket_number",
    "transfer_date",
    "transfer_type",
)


class TexasOriginatingTransfer(BridgeNode[CaseTransfer]):
    """``CaseTransfer`` viewed from the origin docket's side.

    Used as the child class of ``TexasDocket.case_transfer_origin_docket``;
    the framework auto-injects ``origin_docket`` from the parent on
    both ``CreateOp`` and ``UpdateOp``. The other side's FK
    (``destination_docket``) isn't a schema field — the second merge
    (the destination docket's merge) writes that side via its own
    ``TexasDestinationTransfer`` bridge.
    """

    natural_key = _CASE_TRANSFER_NK

    origin_court: PreResolvedRef[Court]
    origin_docket_number: str
    destination_court: PreResolvedRef[Court]
    destination_docket_number: str
    transfer_date: date
    transfer_type: int


class TexasDestinationTransfer(BridgeNode[CaseTransfer]):
    """Mirror of ``TexasOriginatingTransfer`` for the destination
    docket's side. ``destination_docket`` auto-injects; the other
    side is filled by the paired ``TexasOriginatingTransfer`` merge.
    """

    natural_key = _CASE_TRANSFER_NK

    origin_court: PreResolvedRef[Court]
    origin_docket_number: str
    destination_court: PreResolvedRef[Court]
    destination_docket_number: str
    transfer_date: date
    transfer_type: int


# ---------------------------------------------------------------------------
# TexasDocket (root)
# ---------------------------------------------------------------------------


class TexasDocket(
    Aggregate[Docket],
    default_field=ScrapeWins,
    default_collection=ScrapeClobbers,
    lock_for_update=True,
):
    """Root schema for a TAMES-scraped Texas docket.

    Natural key: ``(court, docket_number_core)``. The caller resolves
    ``court`` (a ``Court`` instance) via the existing
    ``texas_js_court_id_to_court_id`` helper and computes
    ``docket_number_core`` via ``make_texas_docket_number_core``.

    ``lock_for_update=True`` so concurrent merges on the same docket
    serialize — matches the existing ``select_for_update`` pattern.

    Known limitations / deferred work:

    - **CaseTransfer**: ``TexasOriginatingTransfer`` and
      ``TexasDestinationTransfer`` are ``BridgeNode`` subclasses; the
      framework auto-injects whichever docket FK matches the parent
      field name on this class. Callers don't need to know about
      docket PKs at scrape-construction time — the bridge row's
      parent FK is filled in on insert (first merge) or on matched
      update (second merge filling in the previously-NULL side).
    - **Cosmetic field-name choices**: ``trialcourtdata``,
      ``role_set``, and ``attorneyorganizationassociation_set``
      follow Django's default reverse-accessor names (the underlying
      Django FKs lack explicit ``related_name`` values). Small
      migrations adding ``related_name`` would let us rename the
      Pydantic fields.
    - **Attorney contact-field updates on matched rows**:
      ``TexasAttorneyRef`` now carries ``contact_raw`` / ``email`` /
      ``phone`` / ``fax`` so the create path populates them, but
      ExternalNodeRef field-update on matched rows is the same framework
      gap that blocks CaseTransfer. Until it closes, existing
      attorney rows aren't refreshed by a re-merge.
    """

    natural_key = ("court", "docket_number_core")

    # Pre-resolved by caller before constructing the tree.
    court: PreResolvedRef[Court]

    # Identity fields.
    docket_number: str
    docket_number_core: str
    docket_number_raw: str

    # Scalar metadata.
    date_filed: date | None = None
    cause: str = ""
    case_name: str = ""
    case_name_full: str = ""

    # Appeal-from is an optional pre-resolved ref; if the caller's lower-
    # court lookup fails it passes ``None`` and ScrapeWinsIfPresent keeps
    # any existing DB value.
    appeal_from: Annotated[
        PreResolvedRef[Court] | None, ScrapeWinsIfPresent
    ] = None
    appeal_from_str: str = ""

    # Caller sets ``source=Docket.SCRAPER`` for create; the Custom
    # strategy OR-bits the SCRAPER bit into existing values on update.
    source: Annotated[int, Custom(_or_scraper_bit)] = 0

    # Owned 1:1 children (parent has the FK column). ``Union`` so a
    # later merge with no usable lower-court info doesn't delete an
    # OCI populated by an earlier merge — matches the legacy
    # ``merge_texas_docket_originating_court`` behavior of returning
    # ``failed`` (and leaving the existing OCI untouched) when the
    # originating court type is UNKNOWN.
    originating_court_information: Annotated[
        TexasOCISchema | None, Union
    ] = None

    # Reverse-FK 1:1 child (TCD has FK to Docket; reverse-accessor
    # ``trialcourtdata`` is Django's default lowercased model name —
    # ugly but functional). Only populated for SC dockets at the
    # scraper level. ``Union`` so an appellate-docket re-merge (which
    # supplies no TCD) doesn't delete a TCD that an earlier SC merge
    # set up — matches the legacy ``MergeResult.unnecessary()`` short-
    # circuit for non-SC dockets.
    trialcourtdata: Annotated[
        TexasTrialCourtDataSchema | None, Union
    ] = None

    # Children. ``texasdocketentry_set`` is Django's default reverse
    # accessor for ``TexasDocketEntry.docket`` (no ``related_name``
    # set). ``Union`` mirrors legacy ``merge_texas_docket_entries``,
    # which iterates over scrape only — DB-only entries are never
    # deleted by a re-merge.
    texasdocketentry_set: Annotated[
        list[TexasDocketEntrySchema], Union
    ] = []

    # ``party_types`` uses ``Union`` (additive) to match the legacy
    # ``add_parties_and_attorneys`` behavior: scraped parties are
    # inserted or matched, but DB-only ``PartyType`` rows are *not*
    # deleted. (The default ``ScrapeClobbers`` would delete them; we
    # explicitly opt out to keep the migration safe.)
    party_types: Annotated[
        list[TexasPartyTypeSchema], Union
    ] = []

    # ``Role`` rows: flat children with Django's default ``role_set``
    # reverse-accessor name. Also ``Union`` (additive) to match the
    # legacy behavior. Caller flattens scrape parties → roles at parse
    # time; the framework's SiblingRef machinery resolves party +
    # attorney ExternalNodeRefs for the NK pairing.
    role_set: Annotated[list[TexasRoleSchema], Union] = []

    # ``AttorneyOrganizationAssociation`` rows: per-docket attorney
    # ↔ org links. Default reverse-accessor name
    # ``attorneyorganizationassociation_set``. ``Union`` to mirror the
    # legacy ``get_or_create`` flow (additive — never delete a DB-only
    # association). Caller is responsible for invoking
    # ``normalize_attorney_contact`` and constructing org refs only
    # when address parsing yielded a usable lookup_key.
    attorneyorganizationassociation_set: Annotated[
        list[TexasAttorneyOrgAssociationSchema], Union
    ] = []

    # ``CaseTransfer`` rows: the docket appears as the origin or
    # destination of a transfer. Both lists use ``Union`` (additive —
    # never delete an existing transfer just because the current
    # scrape doesn't mention it). Field names follow the
    # ``related_name`` on ``CaseTransfer.origin_docket`` and
    # ``destination_docket``. The two ``ExternalNodeRef`` subclasses share
    # the same 6-tuple NK and both declare ``path_scoped=False`` so
    # the global lookup finds half-filled rows the *other* docket
    # inserted in a prior merge.
    case_transfer_origin_docket: Annotated[
        list[TexasOriginatingTransfer], Union
    ] = []
    case_transfer_destination_docket: Annotated[
        list[TexasDestinationTransfer], Union
    ] = []
