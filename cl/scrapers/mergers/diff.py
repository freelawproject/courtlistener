"""Phase 3 — Reconcile.

Walks a paired tree (from L4) and produces a *diffed tree* by applying
each ``ScalarField``'s strategy and, if the node class defines one, its
``custom_class_update`` hook.

The diff is *logical*: it captures what would change at the per-field
strategy level. FK fields whose values come from ExternalNodeRef resolution
(e.g., a ``PartyType.party_id`` that depends on a not-yet-created
``Party``) are intentionally left out — those get filled in during
phase 4 when PKs are known.

See cl/scrapers/MERGERS_IN_THEORY.md (4-phase model + custom_class_update).
"""

from dataclasses import dataclass, field
from typing import Any

from cl.scrapers.mergers.fields import ScalarField, extract_fields
from cl.scrapers.mergers.nodes import Node, bound_django_model
from cl.scrapers.mergers.ops import Write
from cl.scrapers.mergers.paired import PairedNode
from cl.scrapers.mergers.reconcile import apply_scalar_strategy

# ---------------------------------------------------------------------------
# Change variants
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreateOp:
    """A new row to insert. ``values`` carries the scalar fields to
    set."""

    values: dict[str, Any]


@dataclass(frozen=True)
class UpdateOp:
    """An existing row to update. ``field_changes`` is exactly the
    fields the per-field strategies (or ``custom_class_update``) decided
    to write — empty dict means NoOp would be used instead."""

    field_changes: dict[str, Any]


@dataclass(frozen=True)
class DeleteOp:
    """An existing row to remove."""


@dataclass(frozen=True)
class NoOp:
    """No write for this row (matched, all fields already in agreement)."""


type NodeChange = CreateOp | UpdateOp | DeleteOp | NoOp


# ---------------------------------------------------------------------------
# Diffed tree types
# ---------------------------------------------------------------------------


@dataclass
class DiffedNode:
    """One node in the diffed tree.

    Carries the original scrape / db references plus the computed
    ``change`` and the recursively-diffed children.
    """

    scrape: Node | None
    db: Any | None
    change: NodeChange
    children: list["DiffedChildren"] = field(default_factory=list)


@dataclass
class DiffedChildren:
    """A child collection: field name on parent + paired children."""

    name: str
    paired: list[DiffedNode] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def reconcile(paired_root: PairedNode) -> DiffedNode:
    """Walk the paired tree and produce the diffed tree.

    Pure (no DB access).
    """
    return _reconcile_node(paired_root)


# ---------------------------------------------------------------------------
# Recursion
# ---------------------------------------------------------------------------


def _reconcile_node(paired: PairedNode) -> DiffedNode:
    scrape = paired.scrape
    db = paired.db

    diffed_children = [
        DiffedChildren(
            name=cn.name,
            paired=[_reconcile_node(p) for p in cn.paired],
        )
        for cn in paired.children
    ]

    if scrape is None and db is None:
        # Defensive: shouldn't be reachable via build_paired_tree.
        return DiffedNode(
            scrape=None, db=None, change=NoOp(), children=diffed_children
        )

    if scrape is None:
        return DiffedNode(
            scrape=None, db=db, change=DeleteOp(), children=diffed_children
        )

    if db is None:
        values = _values_for_create(scrape)
        return DiffedNode(
            scrape=scrape,
            db=None,
            change=CreateOp(values=values),
            children=diffed_children,
        )

    field_changes = _compute_field_changes(scrape, db)
    change: NodeChange = (
        UpdateOp(field_changes=field_changes) if field_changes else NoOp()
    )
    return DiffedNode(
        scrape=scrape, db=db, change=change, children=diffed_children
    )


# ---------------------------------------------------------------------------
# Create-side: extract values from a scrape Node
# ---------------------------------------------------------------------------


def _values_for_create(scrape: Node) -> dict[str, Any]:
    """Produce the dict of scalar values to insert for a new row.

    If the class defines ``custom_class_update``, the framework calls it
    with ``db=None`` and reads scalar values off the returned Django
    instance — the user has full control over the new-row state.

    Otherwise: for each scalar field, ``None`` on the scrape side is
    coerced to the Pydantic field's declared default when that
    default is non-``None``. This bridges the common Django pattern
    of ``TextField(blank=True)`` (NOT NULL with implicit ``""``
    default) — the driver can pass ``None`` to express "no scrape
    data" without violating the NOT NULL constraint on insert. The
    per-field ``ScrapeWinsIfPresent`` strategy still preserves the
    DB value on subsequent updates because that path doesn't go
    through this coercion.
    """
    cls = type(scrape)
    if _has_custom_class_update(cls):
        desired = scrape.custom_class_update(scrape, None)
        return _extract_scalar_fields(desired, cls)
    values = _extract_scalar_fields(scrape, cls)
    return _coerce_none_to_defaults(values, cls)


def _coerce_none_to_defaults(
    values: dict[str, Any], cls: type[Node]
) -> dict[str, Any]:
    """Replace ``None`` values with the Pydantic field default when
    the default is itself non-``None`` (e.g., ``""`` for a string
    field). Fields without a non-``None`` default are left as-is so
    truly nullable columns receive ``NULL`` as expected.
    """
    from pydantic_core import PydanticUndefined

    coerced = dict(values)
    for name, value in values.items():
        if value is not None:
            continue
        field_info = cls.model_fields.get(name)
        if field_info is None:
            continue
        default = field_info.default
        if default is PydanticUndefined or default is None:
            continue
        coerced[name] = default
    return coerced


# ---------------------------------------------------------------------------
# Update-side: per-field strategies, with custom_class_update override
# ---------------------------------------------------------------------------


def _compute_field_changes(scrape: Node, db: Any) -> dict[str, Any]:
    """Return the dict of fields that would actually change on the
    existing row.

    If the class defines ``custom_class_update``, the framework
    snapshots the DB's scalar field values, calls the hook, and re-diffs
    the returned desired state against the snapshot. (Snapshotting first
    means the hook is free to mutate ``db`` in place and return it — a
    common pattern.) Otherwise the framework applies each
    ``ScalarField``'s strategy directly.
    """
    cls = type(scrape)
    if _has_custom_class_update(cls):
        original_values = _extract_scalar_fields(db, cls)
        desired = scrape.custom_class_update(scrape, db)
        return _diff_snapshot_to_desired(original_values, desired, cls)

    changes: dict[str, Any] = {}
    for fd in extract_fields(cls):
        if not isinstance(fd, ScalarField):
            continue
        scrape_val = getattr(scrape, fd.name)
        db_val = getattr(db, fd.name)
        decision = apply_scalar_strategy(fd.strategy, scrape_val, db_val)
        if isinstance(decision, Write):
            changes[fd.name] = decision.value
    return changes


def _diff_snapshot_to_desired(
    original: dict[str, Any], desired: Any, cls: type[Node]
) -> dict[str, Any]:
    """Compare ``desired`` (a Django instance returned by
    ``custom_class_update``) against a snapshot of the original DB
    values, returning the dict of differing scalar fields.

    Only fields declared on the schema are diffed; if the hook touches a
    Django-only field, those changes are *not* picked up here.
    """
    changes: dict[str, Any] = {}
    for fd in extract_fields(cls):
        if not isinstance(fd, ScalarField):
            continue
        old = original[fd.name]
        new = getattr(desired, fd.name)
        if old != new:
            changes[fd.name] = new
    return changes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_custom_class_update(cls: type[Node]) -> bool:
    """True iff ``cls`` itself defines ``custom_class_update``.

    Checks ``cls.__dict__`` directly (not the MRO) so the base classes
    can't accidentally provide one.
    """
    return "custom_class_update" in cls.__dict__


def _extract_scalar_fields(source: Any, cls: type[Node]) -> dict[str, Any]:
    """Read each schema-declared ``ScalarField`` off ``source`` (either
    a Pydantic Node or a Django model instance) and return a dict.

    For PreResolvedRef fields, ``source.field_name`` is a Django
    instance — Django's ORM accepts that directly as the FK value on
    ``Model(**values)``, so no special handling needed.
    """
    out: dict[str, Any] = {}
    for fd in extract_fields(cls):
        if isinstance(fd, ScalarField):
            out[fd.name] = getattr(source, fd.name)
    return out
