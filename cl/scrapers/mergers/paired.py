"""Paired-tree data structures and builder.

The paired tree mirrors the scrape tree's shape but each node carries both
the scrape Node and the matched DB instance (either may be ``None``):

- ``scrape`` non-None, ``db`` non-None — matched pair.
- ``scrape`` non-None, ``db`` None — scrape-only (Create candidate).
- ``scrape`` None, ``db`` non-None — DB-only (Delete candidate under
  ``ScrapeClobbers``, kept under ``Union`` / ``DBClobbers``).

Phase 3 reads this tree and produces a diff; phase 4 executes the diff.

This module covers L4c (root + InternalNode children) and L4d (ExternalNodeRef
pairing + ``SiblingRef`` in NKs). ExternalNodeRefs are resolved in a single
pre-pass walked over the scrape tree, producing a dict keyed by
``id(scrape_ref)`` that the builder threads into NK key construction.

The ``parent.X`` convention: the last element of a ``ParentPath`` names
the FK column on the child model. So ``parent.docket`` in
``TDocketEntry.natural_key`` means "filter the DB query by
``docket=<parent_db>``".

See cl/scrapers/MERGERS_IN_THEORY.md (4-phase model section).
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ObjectDoesNotExist

from cl.scrapers.mergers.dedup import (
    collapse_duplicate_scrape_nks,
    fold_lookup_refs_in_tree,
)
from cl.scrapers.mergers.fields import (
    ChildField,
    ChildListField,
    ScalarField,
    extract_fields,
)
from cl.scrapers.mergers.nk import (
    NKElement,
    OwnScalar,
    ParentPath,
    SiblingRef,
    classify_nk,
)
from cl.scrapers.mergers.nodes import (
    Aggregate,
    BridgeNode,
    ExternalNodeRef,
    Node,
    bound_django_model,
)
from cl.scrapers.mergers.ops import NoChange, Pairing
from cl.scrapers.mergers.prefetch import prefetch_root
from cl.scrapers.mergers.reconcile import (
    apply_scalar_strategy,
    pair_by_nk,
    pair_by_nk_allowing_duplicates,
)
from cl.scrapers.mergers.strategies import (
    CollectionStrategy,
    _DBClobbers,
    _ScrapeClobbers,
    _Union,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PairedNode:
    """One node in the paired tree.

    ``scrape`` and ``db`` are independently optional:
    - both set -> matched pair
    - only ``scrape`` set -> scrape-only (Create candidate)
    - only ``db`` set -> DB-only (Delete / Keep candidate)
    """

    scrape: Node | None
    db: Any | None
    children: list["ChildNodes"] = field(default_factory=list)


@dataclass
class ChildNodes:
    """A child collection on a parent: field name + the paired children.

    The collection covers all three buckets (matched / scrape-only /
    DB-only); each ``PairedNode`` says which bucket it's in via its
    ``scrape`` / ``db`` Optionals.
    """

    name: str
    paired: list[PairedNode] = field(default_factory=list)


# Type alias for the lookup-ref resolution dict, keyed by id(scrape_ref).
type ResolvedRefs = dict[int, Any]


# ---------------------------------------------------------------------------
# Tree builder (entry point)
# ---------------------------------------------------------------------------


def build_paired_tree[ModelT](
    scrape_root: Aggregate[ModelT],
) -> PairedNode:
    """Pair a scrape tree against the DB.

    Algorithm:
    1. Statically walk the *schema* to compute forward Django paths from
       the root model to each ExternalNodeRef class (e.g.,
       ``"party_types__party"``).
    2. Fetch the root with ``prefetch_related`` over those paths — one
       extra query per relation hop, but properly scoped.
    3. Walk the prefetched data to collect candidate DB rows for each
       ExternalNodeRef class and pair scrape refs against them by NK.
    4. Build the paired tree.

    ExternalNodeRef resolution is **path-scoped via the root** — a Party that
    exists in the DB but is only related to a different docket is
    *not* matched. This mirrors CL's existing ``add_parties_and_attorneys``
    semantic.
    """
    root_cls = type(scrape_root)
    all_paths, lookup_paths = _compute_schema_paths(root_cls)

    db_root = prefetch_root(scrape_root, prefetch_paths=all_paths or None)

    # Collapse duplicate-NK ExternalNodeRefs in the tree first — without
    # this, distinct Python instances with the same NK but different
    # scalar fields would each materialize their own DB row. The fold
    # uses each ref class's declared scalar strategies to resolve
    # conflicts (see :mod:`cl.scrapers.mergers.dedup`).
    fold_lookup_refs_in_tree(scrape_root)

    refs_by_class = _collect_lookup_refs(scrape_root)
    resolved = _resolve_via_prefetched(db_root, refs_by_class, lookup_paths)

    return _build_paired_node(scrape_root, db_root, resolved)


# ---------------------------------------------------------------------------
# Schema-static analysis: forward paths from root to each ExternalNodeRef class
# ---------------------------------------------------------------------------


def _compute_schema_paths(
    cls: type[Node],
) -> tuple[list[str], list[tuple[type[ExternalNodeRef], str]]]:
    """Walk the schema (just classes, no instances) and produce:

    1. ``all_paths``: every ChildField / ChildListField path under
       ``cls`` that contributes to phase-2 prefetching, expressed as
       Django-ORM ``__``-joined strings. ``InternalNode`` /
       ``OwnedChild`` paths and path-scoped ``ExternalNodeRef`` leaf paths
       are emitted; a path that *terminates* at a non-path-scoped
       ``ExternalNodeRef`` (``path_scoped=False``) is dropped because the
       resolver issues a global query for that class and would
       discard the prefetched cache.
    2. ``lookup_paths``: the subset that terminates at a path-scoped
       ``ExternalNodeRef``, paired with the ExternalNodeRef class so phase-2
       resolution knows which paths to traverse. Non-path-scoped
       classes never appear here — the resolver branches on
       ``_mergers_path_scoped`` and goes through ``_global_lookup_rows``.

    Convention: Pydantic field names match Django field / related-names.
    """
    all_paths: list[str] = []
    lookup_paths: list[tuple[type[ExternalNodeRef], str]] = []

    def _walk(c: type[Node], current_path: list[str]) -> None:
        for fd in extract_fields(c):
            if not isinstance(fd, (ChildField, ChildListField)):
                continue
            next_path = [*current_path, fd.name]
            joined = "__".join(next_path)
            child_cls = fd.child_class
            if issubclass(child_cls, BridgeNode):
                # BridgeNode is always globally resolved; the leaf
                # prefetch would be discarded.
                continue
            if issubclass(child_cls, ExternalNodeRef):
                if child_cls._mergers_path_scoped:
                    all_paths.append(joined)
                    lookup_paths.append((child_cls, joined))
                # Non-path-scoped: skip — leaf prefetch would be unused.
            else:
                all_paths.append(joined)
                _walk(child_cls, next_path)

    _walk(cls, [])
    return all_paths, lookup_paths


# ---------------------------------------------------------------------------
# ExternalNodeRef collection + path-scoped resolution
# ---------------------------------------------------------------------------


def _collect_lookup_refs(
    scrape: Node | None,
) -> dict[type[Node], list[Node]]:
    """Walk the scrape tree and collect ``ExternalNodeRef`` and ``BridgeNode``
    instances grouped by their class.

    Both kinds resolve against the DB via NK (path-scoped query for
    ``ExternalNodeRef``, batched global query for ``ExternalNodeRef`` with
    ``path_scoped=False`` and for all ``BridgeNode`` classes), so they
    share a single collection pass and a single resolution dict keyed
    by ``id(scrape_node)``.
    """
    result: dict[type[Node], list[Node]] = defaultdict(list)
    _visit_for_lookup_refs(scrape, result)
    # De-dupe by id within each class so we don't resolve the same
    # instance twice (e.g., a shared PartyRef referenced by multiple
    # PartyTypes).
    deduped: dict[type[Node], list[Node]] = {}
    for cls, items in result.items():
        seen: set[int] = set()
        unique: list[Node] = []
        for r in items:
            if id(r) not in seen:
                seen.add(id(r))
                unique.append(r)
        deduped[cls] = unique
    return deduped


def _visit_for_lookup_refs(
    node: Node | None,
    out: dict[type[Node], list[Node]],
) -> None:
    if node is None:
        return
    cls = type(node)
    if isinstance(node, (ExternalNodeRef, BridgeNode)):
        out[cls].append(node)
    for fd in extract_fields(cls):
        if isinstance(fd, ChildField):
            child = getattr(node, fd.name)
            if child is not None:
                _visit_for_lookup_refs(child, out)
        elif isinstance(fd, ChildListField):
            for child in getattr(node, fd.name) or []:
                _visit_for_lookup_refs(child, out)


def _resolve_via_prefetched(
    db_root: Any | None,
    refs_by_class: dict[type[Node], list[Node]],
    lookup_paths: list[tuple[type[ExternalNodeRef], str]],
) -> ResolvedRefs:
    """Resolve scrape ``ExternalNodeRef`` / ``BridgeNode`` refs against the DB.

    Three resolution modes:

    - **Path-scoped ExternalNodeRef** (default): traverse *every* declared
      forward path from the root, union the candidate DB rows
      (de-duped by PK), and pair scrape refs against the merged set
      by NK. Hits Django's prefetch cache so no extra queries fire.
    - **Global ExternalNodeRef** (``path_scoped=False``): batched
      ``Model.objects.filter(...)`` keyed by the union of NK tuples.
      For rows with a globally-unique NK (e.g.,
      ``AttorneyOrganization.lookup_key``).
    - **BridgeNode**: same batched global query as global ExternalNodeRef;
      the row's identity is global by definition (cross-aggregate).

    When ``db_root is None`` (the docket itself is new) path-scoped
    resolution can't see anything, so refs end up unresolved (phase 4
    will create them under ``CreateIfMissing``). Global resolution is
    independent of ``db_root`` and still runs.
    """
    resolved: ResolvedRefs = {}
    paths_by_class: dict[type[ExternalNodeRef], list[str]] = defaultdict(list)
    for cls, p in lookup_paths:
        paths_by_class[cls].append(p)

    for cls, refs in refs_by_class.items():
        if not refs:
            continue

        is_global = issubclass(cls, BridgeNode) or (
            issubclass(cls, ExternalNodeRef) and not cls._mergers_path_scoped
        )

        if is_global:
            db_rows = _global_lookup_rows(cls, refs)
        elif db_root is None:
            for r in refs:
                resolved[id(r)] = None
            continue
        else:
            paths = paths_by_class.get(cls)
            if not paths:
                for r in refs:
                    resolved[id(r)] = None
                continue
            db_rows = []
            seen_pks: set[Any] = set()
            for path in paths:
                for row in _traverse_prefetched(db_root, path):
                    if row.pk in seen_pks:
                        continue
                    seen_pks.add(row.pk)
                    db_rows.append(row)

        nk_to_row = _index_db_rows_by_nk(db_rows, cls)
        for r in refs:
            key = _lookup_ref_nk_tuple(r, cls)
            resolved[id(r)] = nk_to_row.get(key)
    return resolved


def _global_lookup_rows(
    cls: type[Node], refs: list[Node]
) -> list[Any]:
    """Batched global query for a non-path-scoped ``ExternalNodeRef`` or any
    ``BridgeNode`` class.

    Builds a single ``Model.objects.filter(...)`` keyed by the union
    of NK tuples across all scrape refs of this class, then returns
    the matched rows. Falls back to an empty list if the class has no
    bound Django model (shouldn't happen for a validated schema).
    """
    model = bound_django_model(cls)
    if model is None:
        return []
    elements = _nk_elements_for_lookup(cls)
    if not elements:
        # No queryable identity — global lookup can't disambiguate.
        return []
    nk_tuples = {
        tuple(_scrape_nk_value(r, e) for e in elements) for r in refs
    }
    if not nk_tuples:
        return []
    if len(elements) == 1:
        # Single-field NK → use a single ``__in`` clause for efficiency.
        (element,) = elements
        values = [t[0] for t in nk_tuples]
        return list(
            model._default_manager.filter(
                **{f"{_orm_field_key(element)}__in": values}
            )
        )
    # Multi-field NK → OR together one Q-tuple per scrape ref.
    from django.db.models import Q

    q = Q()
    for t in nk_tuples:
        q |= Q(
            **{_orm_field_key(e): v for e, v in zip(elements, t)}
        )
    return list(model._default_manager.filter(q))


def _orm_field_key(element: NKElement) -> str:
    """Return the Django ORM lookup key for an NK element.

    ``OwnScalar`` → the field name; ``SiblingRef`` (preresolved-FK
    variant only) → ``<field>_id`` so the lookup accepts raw PKs and
    avoids a related fetch on the scrape side.
    """
    if isinstance(element, OwnScalar):
        return element.field_name
    return f"{element.field_name}_id"


def _traverse_prefetched(root: Any, path: str) -> list[Any]:
    """Walk forward through Django relations from ``root``, returning
    the leaf rows.

    Each path segment may be a forward FK (yields a single instance),
    a reverse-FK manager (yields many), or a forward o2o (single). The
    function flattens at each level.
    """
    segments = path.split("__")
    current: list[Any] = [root]
    for seg in segments:
        next_level: list[Any] = []
        for item in current:
            attr = getattr(item, seg, None)
            if attr is None:
                continue
            if hasattr(attr, "all"):
                # Related manager (reverse FK / M2M).
                next_level.extend(attr.all())
            else:
                next_level.append(attr)
        current = next_level
    return current


def _index_db_rows_by_nk(
    db_rows: list[Any], cls: type[Node]
) -> dict[tuple, Any]:
    """Build ``{nk_tuple -> db_row}`` for a ``ExternalNodeRef`` or
    ``BridgeNode`` class.

    NK tuples on the DB side mirror the scrape side: ``OwnScalar``
    yields ``getattr(row, name)``; ``SiblingRef``-preresolved yields
    the FK PK via ``getattr(row, f"{name}_id")`` so the comparison
    against scrape-side PKs lines up.
    """
    elements = _nk_elements_for_lookup(cls)
    return {
        tuple(_db_nk_value(row, e) for e in elements): row for row in db_rows
    }


def _lookup_ref_nk_tuple(ref: Node, cls: type[Node]) -> tuple:
    """Compute the NK tuple for a scrape ``ExternalNodeRef`` / ``BridgeNode``
    in the same order as ``_index_db_rows_by_nk`` so the dict lookup
    works."""
    elements = _nk_elements_for_lookup(cls)
    return tuple(_scrape_nk_value(ref, e) for e in elements)


def _nk_elements_for_lookup(cls: type[Node]) -> list[NKElement]:
    """NK elements usable by ``ExternalNodeRef`` / ``BridgeNode`` global +
    path-scoped pairing.

    Accepts ``OwnScalar`` (a primitive column on the bound Django
    model) and ``SiblingRef`` with a pre-resolved Django model (i.e.,
    a ``PreResolvedRef`` field whose value is a Django instance the
    caller has already resolved). Rejects ``ParentPath`` (path-scoping
    is handled separately) and ``SiblingRef`` with a ``child_class``
    (a ``ExternalNodeRef`` sibling in the NK isn't supported on this code
    path yet — that would require a second resolution round).
    """
    out: list[NKElement] = []
    for element in classify_nk(cls):
        if isinstance(element, OwnScalar):
            out.append(element)
        elif (
            isinstance(element, SiblingRef)
            and element.preresolved_model is not None
        ):
            out.append(element)
        else:
            raise NotImplementedError(
                f"NK on {cls.__name__} has element {element!r} that's not "
                f"supported in this lookup code path; only OwnScalar and "
                f"SiblingRef-preresolved are supported."
            )
    return out


def _scrape_nk_value(ref: Node, element: NKElement) -> Any:
    """Extract the NK value for ``element`` from a scrape node.

    ``OwnScalar`` returns the field value directly. ``SiblingRef``
    (preresolved-FK only) returns the resolved Django instance's PK so
    it lines up with the DB side's ``<field>_id`` reading.
    """
    value = getattr(ref, element.field_name)
    if isinstance(element, OwnScalar):
        return value
    return value.pk if value is not None else None


def _db_nk_value(row: Any, element: NKElement) -> Any:
    """Extract the NK value for ``element`` from a Django row.

    ``OwnScalar`` reads the column directly; ``SiblingRef``
    (preresolved-FK only) reads ``<field>_id`` to avoid a related fetch.
    """
    if isinstance(element, OwnScalar):
        return getattr(row, element.field_name)
    return getattr(row, f"{element.field_name}_id")


# ---------------------------------------------------------------------------
# Tree-building recursion
# ---------------------------------------------------------------------------


def _build_paired_node(
    scrape: Node | None,
    db: Any | None,
    resolved: ResolvedRefs,
) -> PairedNode:
    """Build a ``PairedNode`` for ``(scrape, db)``, recursing into child
    fields of ``scrape``'s class (if any)."""
    cls: type[Node] | None = type(scrape) if scrape is not None else None

    children_collected: list[ChildNodes] = []
    if cls is not None:
        for fd in extract_fields(cls):
            if isinstance(fd, (ChildField, ChildListField)):
                paired = _pair_child_field(
                    scrape, db, fd, resolved
                )
                children_collected.append(
                    ChildNodes(name=fd.name, paired=paired)
                )

    return PairedNode(scrape=scrape, db=db, children=children_collected)


def _pair_child_field(
    scrape_parent: Node,
    db_parent: Any | None,
    fd: ChildField | ChildListField,
    resolved: ResolvedRefs,
) -> list[PairedNode]:
    """Pair scrape's value(s) for one child field against DB rows.

    Dispatches on the child class:

    - ``ExternalNodeRef`` or ``BridgeNode``: paired by globally-resolved NK
      (resolution happened in a single pre-pass over the scrape tree).
      No DB-only enumeration — both kinds have additive (``Union``)
      collection semantics by default.
    - ``InternalNode`` / ``OwnedChild``: paired by parent FK + NK
      fields including resolved ``SiblingRef`` values.
    """
    if isinstance(fd, ChildField):
        scrape_value = getattr(scrape_parent, fd.name)
        scrape_items: list[Node] = (
            [scrape_value] if scrape_value is not None else []
        )
    else:  # ChildListField
        raw = getattr(scrape_parent, fd.name)
        scrape_items = list(raw) if raw is not None else []

    child_cls = fd.child_class

    if issubclass(child_cls, (ExternalNodeRef, BridgeNode)):
        return _pair_lookup_ref_field(scrape_items, resolved)
    return _pair_internal_node_field(scrape_items, db_parent, fd, resolved)


def _pair_lookup_ref_field(
    scrape_items: list[Node],
    resolved: ResolvedRefs,
) -> list[PairedNode]:
    """Build PairedNodes for a ExternalNodeRef child field.

    The resolution was done in the pre-pass; we just read it back.
    DB rows that aren't referenced by any scrape ref are *not*
    represented here — ExternalNodeRefs have an independent lifecycle and the
    framework never deletes them as part of an aggregate merge.
    """
    out: list[PairedNode] = []
    for ref in scrape_items:
        db_row = resolved.get(id(ref))
        out.append(_build_paired_node(ref, db_row, resolved))
    return out


def _pair_internal_node_field(
    scrape_items: list[Node],
    db_parent: Any | None,
    fd: ChildField | ChildListField,
    resolved: ResolvedRefs,
) -> list[PairedNode]:
    """Pair an InternalNode child field, honoring SiblingRefs in NK and
    ``allow_duplicates`` on the child class.

    For nodes without ``allow_duplicates``, duplicate-NK scrape rows
    are folded into a single representative via the schema's existing
    per-field strategies (see :mod:`cl.scrapers.mergers.dedup`). The
    DB-side duplicate check in :func:`pair_by_nk` still raises — DB
    duplicates indicate a real invariant violation, not redundant
    emission.
    """
    child_cls = fd.child_class
    db_items: list[Any] = []
    if db_parent is not None:
        db_items = _fetch_db_children(fd, db_parent)

    key_fn = _build_nk_key_fn(child_cls, resolved)

    if child_cls._mergers_allow_duplicates:
        cost_fn = _build_edit_cost_fn(child_cls)
        pairing = pair_by_nk_allowing_duplicates(
            scrape_items, db_items, key_fn, cost_fn
        )
    else:
        # Collapse duplicate-NK scrape rows before hash-join pairing.
        # Bipartite-matched nodes (``allow_duplicates=True``) skip this
        # — the matcher there relies on raw multiplicities.
        scrape_items = collapse_duplicate_scrape_nks(
            scrape_items,
            child_cls,
            key_fn,
            build_key_fn=lambda c: _build_nk_key_fn(c, resolved),
        )
        pairing = pair_by_nk(scrape_items, db_items, key_fn)

    return _pairing_to_paired_nodes(pairing, resolved, fd.strategy)


def _pairing_to_paired_nodes(
    pairing: Pairing[Node, Any],
    resolved: ResolvedRefs,
    strategy: CollectionStrategy,
) -> list[PairedNode]:
    """Flatten a ``Pairing`` into ``PairedNode`` instances, recursing
    into each.

    The field's ``CollectionStrategy`` filters which unmatched buckets
    cross into the paired tree:

    - ``ScrapeClobbers`` (default): db-only nodes are included so they
      become ``DeleteOp``\\ s; scrape-only nodes become ``CreateOp``\\ s.
    - ``Union``: db-only nodes are dropped (kept in DB, never deleted
      by an aggregate merge); scrape-only nodes still become creates.
    - ``DBClobbers``: both unmatched buckets are dropped — only paired
      rows are touched.

    Custom strategies fall back to ``ScrapeClobbers`` semantics here;
    fully wiring ``CustomCollection.fn`` through the paired-tree
    builder is a separate piece of work.
    """
    include_scrape_only = not isinstance(strategy, _DBClobbers)
    include_db_only = isinstance(strategy, _ScrapeClobbers) or not isinstance(
        strategy, (_Union, _DBClobbers)
    )
    out: list[PairedNode] = []
    for s, d in pairing.pairs:
        out.append(_build_paired_node(s, d, resolved))
    if include_scrape_only:
        for s in pairing.scrape_only:
            out.append(_build_paired_node(s, None, resolved))
    if include_db_only:
        for d in pairing.db_only:
            out.append(_build_paired_node(None, d, resolved))
    return out


# ---------------------------------------------------------------------------
# DB fetch + NK key construction
# ---------------------------------------------------------------------------


def _fetch_db_children(
    fd: ChildField | ChildListField, db_parent: Any
) -> list[Any]:
    """Fetch DB rows for this child field via the parent's related
    accessor.

    Convention: the Pydantic field name on the parent schema matches the
    Django ``related_name`` (for reverse FK) or the field name (for a
    forward 1:1). This means ``getattr(db_parent, fd.name)`` always
    yields the right cache — when ``build_paired_tree`` has called
    ``prefetch_related`` for the corresponding path, no extra DB query
    is issued; without prefetch, Django does the lazy SELECT now.

    Sidesteps the question of multi-level ``ParentPath`` in the child's
    NK entirely: NK ParentPath elements are informational at the schema
    level (and skipped in the pairing key) — the actual scoping comes
    from walking the parent's related manager.
    """
    try:
        related = getattr(db_parent, fd.name)
    except ObjectDoesNotExist:
        return []
    if related is None:
        return []
    if isinstance(fd, ChildListField):
        return list(related.all())
    # ChildField (single, 1:1-ish on the DB side).
    if hasattr(related, "all"):
        return list(related.all())
    return [related]


def _build_edit_cost_fn(
    cls: type[Node],
) -> Callable[[Node, Any], int]:
    """Cost function for ``pair_by_nk_allowing_duplicates``: how many
    non-NK scalar fields would the per-field strategies actually write?

    Counts every ``ScalarField`` whose field name isn't an
    ``OwnScalar`` NK element, applies the field's strategy with the
    scrape vs DB values, and adds 1 to the cost whenever the strategy
    returns a ``Write`` rather than ``NoChange``.

    SiblingRef fields aren't iterated in cost (they're scalars wrapping
    a ExternalNodeRef instance; their "edit" is the ExternalNodeRef pairing, which
    happens separately).
    """
    nk_field_names = {
        e.field_name for e in classify_nk(cls) if isinstance(e, OwnScalar)
    }
    scalar_fields = [
        f
        for f in extract_fields(cls)
        if isinstance(f, ScalarField) and f.name not in nk_field_names
    ]

    def cost_fn(scrape: Node, db: Any) -> int:
        c = 0
        for f in scalar_fields:
            scrape_val = getattr(scrape, f.name)
            db_val = getattr(db, f.name)
            decision = apply_scalar_strategy(f.strategy, scrape_val, db_val)
            if decision is not NoChange:
                c += 1
        return c

    return cost_fn


def _build_nk_key_fn(
    cls: type[Node],
    resolved: ResolvedRefs,
) -> Callable[[Any], tuple[Any, ...]]:
    """Build a key function for ``pair_by_nk`` that extracts the
    pairable portion of the NK.

    Handles both scrape Node instances and DB Django model instances:
    - ``OwnScalar``: ``getattr(item, field_name)`` works on both.
    - ``SiblingRef``: on scrape side, look up the resolved DB PK via
      ``resolved`` (or fall back to a sentinel NK tuple for
      yet-to-be-created refs); on DB side, read ``<field>_id`` directly.
    - ``ParentPath``: skipped — already filtered out by the parent-FK
      query.
    """
    elements = classify_nk(cls)

    def key_fn(item: Any) -> tuple[Any, ...]:
        parts: list[Any] = []
        for e in elements:
            if isinstance(e, ParentPath):
                continue
            if isinstance(e, OwnScalar):
                parts.append(getattr(item, e.field_name))
            elif isinstance(e, SiblingRef):
                parts.append(_sibling_identity(item, e.field_name, resolved))
        return tuple(parts)

    return key_fn


def _sibling_identity(
    item: Any, field_name: str, resolved: ResolvedRefs
) -> Any:
    """Extract a hashable identity for a SiblingRef value.

    Works on both scrape (ExternalNodeRef instance) and DB (Django Model
    instance with FK).

    - DB row: read the ``<field>_id`` FK directly.
    - Scrape ref, resolved to a DB row: use that DB row's PK.
    - Scrape ref, unresolved (CreateIfMissing pending): use a sentinel
      tuple of its own NK values so it won't accidentally collide with
      a DB PK (which is typically an int / UUID).
    """
    if isinstance(item, Node):
        ref = getattr(item, field_name)
        if ref is None:
            return None
        resolved_db = resolved.get(id(ref))
        if resolved_db is not None:
            return resolved_db.pk
        # Unresolved: use NK tuple as identity (won't collide with PKs).
        return _scrape_ref_identity(ref)
    # DB row: get FK PK via ``<field>_id`` (avoids a relation fetch).
    return getattr(item, f"{field_name}_id")


def _scrape_ref_identity(ref: Node) -> tuple:
    """Compute a hashable identity for an unresolved scrape ExternalNodeRef
    from its own NK values."""
    parts: list[Any] = []
    for e in classify_nk(type(ref)):
        if isinstance(e, OwnScalar):
            parts.append(getattr(ref, e.field_name))
        elif isinstance(e, SiblingRef):
            parts.append(_sibling_identity(ref, e.field_name, {}))
    return ("__unresolved__", *parts)
