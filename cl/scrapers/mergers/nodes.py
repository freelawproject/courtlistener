"""Schema base classes for the merger framework.

Four kinds of tree nodes:

- ``Node`` — common base (Pydantic ``BaseModel`` subclass).
- ``Aggregate[ModelT]`` — the root of a merge; binds the root Django
  model and optionally declares ``lock_for_update``.
- ``InternalNode[ModelT]`` — lifecycle-owned child; deleted under
  ``ScrapeClobbers`` semantics.
- ``ExternalNodeRef[ModelT]`` — external row with independent lifecycle;
  declares an ``absence_policy``.

User schemas declare class-level configuration via class kwargs:

    class TexasDocket(
        Aggregate[Docket],
        default_field=ScrapeWins,
        default_collection=ScrapeClobbers,
        lock_for_update=True,
    ):
        ...

This module captures those kwargs as class attributes (prefixed
``_mergers_``) and resolves the bound Django model from the generic
parameter. Field annotation extraction, NK topological sort, and
schema validation come in later sub-cycles (L3b, L3c, L3d).

See cl/scrapers/MERGERS_IN_THEORY.md (Node kinds section).
"""

import enum
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict

from cl.scrapers.mergers.strategies import (
    CollectionStrategy,
    DBWins,
    ScalarStrategy,
    ScrapeClobbers,
    ScrapeWins,
    Union,
)

# ---------------------------------------------------------------------------
# Absence policy (for ExternalNodeRef)
# ---------------------------------------------------------------------------

class AbsencePolicy(enum.Enum):
    """What to do when a ExternalNodeRef's NK doesn't match anything in DB."""

    CREATE_IF_MISSING = "create_if_missing"
    ERROR_IF_MISSING = "error_if_missing"
    NOOP_IF_MISSING = "noop_if_missing"


# Public aliases used at the schema declaration site.
CreateIfMissing = AbsencePolicy.CREATE_IF_MISSING
ErrorIfMissing = AbsencePolicy.ERROR_IF_MISSING
NoopIfMissing = AbsencePolicy.NOOP_IF_MISSING


# ---------------------------------------------------------------------------
# PreResolvedRef marker
# ---------------------------------------------------------------------------

class _PreResolvedMarker:
    """Sentinel marker for PreResolvedRef annotations."""


# A type alias rather than a class: ``PreResolvedRef[Court]`` evaluates to
# ``Annotated[Court, _PreResolvedMarker]`` at static-type-checker level
# (and runtime introspection via ``__value__``). At the Pydantic field
# level the value type is just ``Court``, so callers pass the Django
# instance directly.
type PreResolvedRef[T] = Annotated[T, _PreResolvedMarker]


# ---------------------------------------------------------------------------
# Django model binding resolution + concrete-class validation hook
# ---------------------------------------------------------------------------

def bound_django_model(cls: type) -> type | None:
    """Resolve the Django model bound to ``cls`` via its generic parameter.

    Walks ``cls.__mro__`` looking for the first base whose
    ``__pydantic_generic_metadata__["args"]`` is populated. The first
    argument is the bound model. Returns ``None`` if no binding is
    found (which is unusual — typically a schema bug caught in L3d).
    """
    # ``Node`` is referenced here at call-time, not at definition-time, so
    # it's fine that this function appears before ``Node`` in the module.
    for base in cls.__mro__:
        md = getattr(base, "__pydantic_generic_metadata__", None)
        if md and md.get("args"):
            origin = md.get("origin")
            if origin is not None and issubclass(origin, Node):
                return md["args"][0]
    return None


def _validate_if_concrete(cls: type) -> None:
    """Run schema validation if ``cls`` is a concrete user subclass.

    Three kinds of class go through ``__pydantic_init_subclass__``:
    - Abstract framework bases (``Aggregate`` itself, etc.) — no bound
      Django model, skip.
    - Parameterized-generic *intermediates* (``ExternalNodeRef[Party]``)
      created automatically by Pydantic. These have an
      ``__pydantic_generic_metadata__["origin"]`` set to the parent
      generic; skip — not user schemas.
    - User concrete subclasses — origin is ``None`` in their own
      metadata, but a bound Django model is reachable via the MRO.

    Validate only the last kind.
    """
    own_md = getattr(cls, "__pydantic_generic_metadata__", None) or {}
    if own_md.get("origin") is not None:
        return
    if bound_django_model(cls) is None:
        return
    # Lazy import to break the validate.py <-> nodes.py cycle.
    from cl.scrapers.mergers.validate import validate_schema

    validate_schema(cls)


# ---------------------------------------------------------------------------
# Common base
# ---------------------------------------------------------------------------

class Node(BaseModel):
    """Common base for all tree nodes.

    Subclasses (Aggregate / InternalNode / ExternalNodeRef) extend this with
    kind-specific defaults and kwargs.
    """

    # ``arbitrary_types_allowed`` lets fields hold Django model
    # instances (e.g. ``PreResolvedRef[Court]`` resolves to a ``Court``
    # row the caller pre-fetched). Pydantic v2 merges ``model_config``
    # across the MRO, so this propagates to every subclass — drivers
    # don't need to repeat it per schema class.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # ClassVar so subclasses can assign ``natural_key = (...)`` without
    # an explicit annotation. Pydantic respects the parent's ClassVar
    # annotation when the child reassigns without one.
    natural_key: ClassVar[tuple[Any, ...] | None] = None

    # These get set by __init_subclass__ on the relevant base. Kept here
    # as ClassVars so Pydantic doesn't treat them as fields.
    _mergers_default_field: ClassVar[ScalarStrategy]
    _mergers_default_collection: ClassVar[CollectionStrategy]

    def __init_subclass__(
        cls,
        *,
        default_field: ScalarStrategy | None = None,
        default_collection: CollectionStrategy | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if default_field is not None:
            cls._mergers_default_field = default_field
        if default_collection is not None:
            cls._mergers_default_collection = default_collection

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """Pydantic-specific hook that runs after model_fields are
        populated. Runs schema validation for concrete subclasses.

        Validation only fires for user-declared subclasses with a bound
        Django model; abstract bases and Pydantic's auto-created
        parameterized intermediates are skipped (see
        ``_validate_if_concrete`` for the rules).
        """
        super().__pydantic_init_subclass__(**kwargs)
        _validate_if_concrete(cls)

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    #
    # ``on_update`` is the single entry-point the framework calls after
    # every mutated row. By default it dispatches to ``on_create`` /
    # ``on_delete`` based on which side is ``None`` so subclasses can
    # override just the case they care about. Direct ``on_update``
    # override is also supported — call ``super().on_update(...)`` to
    # get the default dispatch.
    #
    # Returning ``None`` (or an empty list) means "no follow-ups."
    #
    # Note on ``on_delete`` and db-only deletes: for ``ScrapeClobbers``-
    # induced deletions there is no scrape Node, so the framework
    # synthesizes one via ``cls.model_construct()`` to invoke the hook.
    # The synthetic ``self`` has *no* field values populated — hooks for
    # db-only deletes should read from the ``old_db`` argument, not
    # ``self``.

    def on_create(self, new_db: Any) -> Any:
        """Called when this node's row is being created.

        :param new_db: the freshly inserted Django instance, with PK
            populated.
        :return: ``None`` or a list of follow-up callables.
        """
        return None

    def on_delete(self, old_db: Any) -> Any:
        """Called when this node's row is being deleted.

        :param old_db: a snapshot of the row taken *before* the
            ``DELETE`` ran, so ``old_db.pk`` and other field values are
            still readable.
        :return: ``None`` or a list of follow-up callables.
        """
        return None

    def on_update(self, old_db: Any, new_db: Any) -> Any:
        """Called after each row mutation. Default dispatches:
        - ``old_db is None`` → ``on_create(new_db)``
        - ``new_db is None`` → ``on_delete(old_db)``
        - both set → returns ``None`` (override for custom behavior).
        """
        if old_db is None:
            return self.on_create(new_db)
        if new_db is None:
            return self.on_delete(old_db)
        return None


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

class Aggregate[ModelT](Node):
    """The root of a merge tree.

    Class kwargs (in addition to those on ``Node``):
    - ``lock_for_update: bool = False`` — if True, phase 2 fetches the
      root row with ``select_for_update()``.
    """

    _mergers_default_field: ClassVar[ScalarStrategy] = ScrapeWins
    _mergers_default_collection: ClassVar[CollectionStrategy] = ScrapeClobbers
    _mergers_lock_for_update: ClassVar[bool] = False

    def __init_subclass__(
        cls,
        *,
        lock_for_update: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if lock_for_update is not None:
            cls._mergers_lock_for_update = lock_for_update


# ---------------------------------------------------------------------------
# InternalNode
# ---------------------------------------------------------------------------

class InternalNode[ModelT](Node):
    """A lifecycle-owned child node.

    Class kwargs (in addition to those on ``Node``):
    - ``allow_duplicates: bool = False`` — allow multiple items per NK,
      paired via minimum-edit-cost assignment.
    """

    _mergers_default_field: ClassVar[ScalarStrategy] = ScrapeWins
    _mergers_default_collection: ClassVar[CollectionStrategy] = ScrapeClobbers
    _mergers_allow_duplicates: ClassVar[bool] = False

    def __init_subclass__(
        cls,
        *,
        allow_duplicates: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if allow_duplicates is not None:
            cls._mergers_allow_duplicates = allow_duplicates


# ---------------------------------------------------------------------------
# ExternalNodeRef
# ---------------------------------------------------------------------------

class ExternalNodeRef[ModelT](Node):
    """An external-row reference looked up by NK.

    Class kwargs (in addition to those on ``Node``):
    - ``absence_policy: AbsencePolicy = CreateIfMissing`` — what to do
      when the lookup misses.
    - ``allow_duplicates: bool = False``.
    - ``path_scoped: bool = True`` — when ``True`` (the default), the
      framework restricts candidate rows to those reachable from the
      root aggregate via declared paths (``Docket.party_types.party``,
      etc.). When ``False`` the resolver issues a single batched
      global query against the bound Django model keyed by the NK
      fields; use this for rows whose NK is globally unique (e.g.,
      ``AttorneyOrganization.lookup_key``) or that cross aggregate
      boundaries (e.g., ``CaseTransfer`` which links two dockets).
    """

    _mergers_default_field: ClassVar[ScalarStrategy] = DBWins
    _mergers_default_collection: ClassVar[CollectionStrategy] = Union
    _mergers_absence_policy: ClassVar[AbsencePolicy] = CreateIfMissing
    _mergers_allow_duplicates: ClassVar[bool] = False
    _mergers_path_scoped: ClassVar[bool] = True

    def __init_subclass__(
        cls,
        *,
        absence_policy: AbsencePolicy | None = None,
        allow_duplicates: bool | None = None,
        path_scoped: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if absence_policy is not None:
            cls._mergers_absence_policy = absence_policy
        if allow_duplicates is not None:
            cls._mergers_allow_duplicates = allow_duplicates
        if path_scoped is not None:
            cls._mergers_path_scoped = path_scoped


# ---------------------------------------------------------------------------
# BridgeNode
# ---------------------------------------------------------------------------


class BridgeNode[ModelT](Node):
    """A row that straddles two aggregates.

    The bridge has FK columns to two parent rows in different
    aggregates. From either parent's perspective the bridge is a
    reverse-FK child (so its lifecycle is parent-owned by *each*
    side), but the row's *identity* is global by NK — both aggregates
    refer to the same row when their merges share the bridge's NK.

    Canonical example: ``CaseTransfer`` between two ``Docket`` rows.
    The first docket's merge inserts the bridge with its side's FK
    filled and the other side's FK NULL; the second docket's merge
    finds the same row by NK and fills in the previously-NULL side.

    Resolution: always global (NK-keyed ``Model.objects.filter`` query
    against the bound Django model). Path-scoping makes no sense for
    a row that's reachable from two different aggregates.

    Apply-time parent FK auto-injection: the framework derives the FK
    field name on the bridge model from the parent's Pydantic field
    name (which by convention matches the Django reverse-relation
    accessor / ``related_name``). On ``CreateOp`` the parent FK is
    injected into the insert kwargs; on ``UpdateOp`` it's written if
    the matched row had it NULL (the cross-merge fill-in path).

    Default strategies are ExternalNodeRef-like: ``DBWins`` for scalars and
    ``Union`` for collections so a bridge isn't accidentally deleted
    when one of its two parents stops referencing it from scrape.
    """

    _mergers_default_field: ClassVar[ScalarStrategy] = DBWins
    _mergers_default_collection: ClassVar[CollectionStrategy] = Union
    _mergers_absence_policy: ClassVar[AbsencePolicy] = CreateIfMissing
    _mergers_allow_duplicates: ClassVar[bool] = False

    def __init_subclass__(
        cls,
        *,
        absence_policy: AbsencePolicy | None = None,
        allow_duplicates: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if absence_policy is not None:
            cls._mergers_absence_policy = absence_policy
        if allow_duplicates is not None:
            cls._mergers_allow_duplicates = allow_duplicates


# ---------------------------------------------------------------------------
# OwnedChild
# ---------------------------------------------------------------------------

class OwnedChild[ModelT](Node):
    """A parent-owned 1:1 child whose FK lives on the *parent* row.

    Use for OneToOne relationships where the parent's Django model has
    the FK column (e.g., ``Docket.originating_court_information``
    pointing to ``OriginatingCourtInformation``).

    Lifecycle is owned: when scrape gains or loses this child, the
    framework creates or deletes accordingly (mirroring
    ``InternalNode`` defaults). Matching is trivial — there's at most
    one row reachable via the parent's forward FK — so the default
    ``natural_key`` is empty.

    During phase 4 the framework processes ``OwnedChild`` siblings
    *before* the parent (so the parent's FK is settable) and fully
    recurses via ``_apply_node`` so the owned row gets its own scalar
    updates, children, and lifecycle hooks. The resulting DB instance
    is injected as the parent's FK kwarg.
    """

    natural_key: ClassVar[tuple[Any, ...]] = ()

    _mergers_default_field: ClassVar[ScalarStrategy] = ScrapeWins
    _mergers_default_collection: ClassVar[CollectionStrategy] = ScrapeClobbers
    # Not meaningful for OwnedChild (singleton-via-path) but required by
    # the framework's pairing code path which also handles
    # ``InternalNode``/``OwnedChild`` uniformly.
    _mergers_allow_duplicates: ClassVar[bool] = False


