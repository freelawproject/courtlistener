"""Phase 4 — Apply.

Walks a diffed tree (from L5) and executes the diff against the DB:
creates, updates, and deletes rows in topologically-correct order,
fires lifecycle hooks on ascent, and accumulates follow-up callables.

L6a covers basic Create/Update/Delete/NoOp execution + parent-FK
injection on creates. Lifecycle hooks (L6b) and ExternalNodeRef
materialization (L6c) come in subsequent sub-cycles.

See cl/scrapers/MERGERS_IN_THEORY.md (4-phase model section).
"""

import copy
from collections.abc import Callable
from typing import Any

from cl.scrapers.mergers.diff import (
    CreateOp,
    DeleteOp,
    DiffedNode,
    NoOp,
    UpdateOp,
)
from cl.scrapers.mergers.fields import ChildField, extract_fields
from cl.scrapers.mergers.nk import ParentPath, classify_nk
from cl.scrapers.mergers.nodes import (
    BridgeNode,
    CreateIfMissing,
    ErrorIfMissing,
    ExternalNodeRef,
    Node,
    NoopIfMissing,
    OwnedChild,
    bound_django_model,
)
from cl.scrapers.mergers.outcome import MergeOutcome
from cl.scrapers.mergers.refs import path_parts


def apply(diffed_root: DiffedNode) -> MergeOutcome:
    """Execute a diffed tree against the DB and return the outcome.

    The caller is responsible for transaction management — wrap the
    call in ``transaction.atomic()`` (or use the convenience entry
    point ``merge_one`` in L7) to get atomicity.
    """
    creates: dict[Any, set[Any]] = {}
    updates: dict[Any, set[Any]] = {}
    deletes: dict[Any, set[Any]] = {}
    follow_ups: list[Callable[..., Any]] = []
    # Cache of materialized ExternalNodeRef rows keyed by id(scrape_ref) so a
    # shared scrape ref doesn't get inserted multiple times.
    lookup_cache: dict[int, Any] = {}
    new_root = _apply_node(
        diffed_root,
        parent_db=None,
        parent_fk_field=None,
        creates=creates,
        updates=updates,
        deletes=deletes,
        follow_ups=follow_ups,
        lookup_cache=lookup_cache,
        schema_class=None,  # root reads class from type(scrape)
    )
    return MergeOutcome(
        root=new_root,
        creates=creates,
        updates=updates,
        deletes=deletes,
        follow_ups=follow_ups,
    )


# ---------------------------------------------------------------------------
# Per-node dispatch
# ---------------------------------------------------------------------------


def _apply_node(
    diffed: DiffedNode,
    parent_db: Any | None,
    parent_fk_field: str | None,
    creates: dict[Any, set[Any]],
    updates: dict[Any, set[Any]],
    deletes: dict[Any, set[Any]],
    follow_ups: list[Callable[..., Any]],
    lookup_cache: dict[int, Any],
    schema_class: type[Node] | None,
) -> Any | None:
    """Process one node, recursing into its children.

    Ordering:
    - Create / Update / NoOp: materialize ExternalNodeRef ``ChildField``
      siblings first (their PKs feed into this node's FK columns),
      mutate self next (children can then use ``self.pk`` for their
      parent FK), recurse into the remaining (InternalNode) children,
      and finally fire ``on_update`` on ascent.
    - Delete: recurse into children first (post-order delete), then
      delete self.

    Returns the new (or matched) DB instance, or ``None`` for deletes.
    """
    change = diffed.change

    # The schema class for *this* node: prefer the live scrape Node's
    # type, but for db-only branches (no scrape) the parent threads it
    # down so we can still synthesize a Node for ``on_delete``.
    cls: type[Node] | None = (
        type(diffed.scrape) if diffed.scrape is not None else schema_class
    )

    if isinstance(change, DeleteOp):
        return _apply_delete(
            diffed,
            creates,
            updates,
            deletes,
            follow_ups,
            lookup_cache,
            cls,
        )

    # 1. Pre-process child siblings that must materialize *before*
    #    self (so their PKs can be injected as FK columns on this row):
    #    - ``ExternalNodeRef`` ChildFields: shared external refs; resolve or
    #      create-if-missing.
    #    - ``OwnedChild`` ChildFields: parent-owned 1:1; full recursive
    #      apply (the owned row gets its own scalar updates, children,
    #      and hooks).
    #    Returns the FK kwargs plus the set of collection names already
    #    handled (skipped in the InternalNode recursion below).
    lookup_fk_kwargs, lookup_handled = _materialize_pre_children(
        diffed, creates, updates, deletes, follow_ups, lookup_cache
    )

    # 2. Snapshot old DB state *before* mutation so hooks can compare
    #    against the pre-mutation values.
    old_db: Any | None = None
    if isinstance(change, UpdateOp) and diffed.db is not None:
        old_db = copy.copy(diffed.db)

    # 3. Mutate self.
    if isinstance(change, CreateOp):
        new_db = _apply_create(
            diffed,
            parent_db,
            parent_fk_field,
            lookup_fk_kwargs,
            creates,
        )
    elif isinstance(change, UpdateOp):
        new_db = _apply_update(
            diffed,
            lookup_fk_kwargs,
            updates,
            parent_db=parent_db,
            parent_fk_field=parent_fk_field,
        )
    elif isinstance(change, NoOp):
        # If pre-materialization produced FK changes (e.g., an
        # ``OwnedChild`` got created or deleted under an existing
        # parent), or a ``BridgeNode`` child needs its parent-FK
        # NULL-side filled in, we still need to write the FK column.
        # Route through the update path; it'll be a no-op write if no
        # FK actually changed.
        synthetic_fk_kwargs = dict(lookup_fk_kwargs)
        if (
            parent_fk_field is not None
            and parent_db is not None
            and diffed.scrape is not None
            and isinstance(diffed.scrape, BridgeNode)
        ):
            synthetic_fk_kwargs[parent_fk_field] = parent_db
        if synthetic_fk_kwargs and _fk_kwargs_imply_change(
            diffed.db, synthetic_fk_kwargs
        ):
            new_db = _apply_update(
                diffed,
                synthetic_fk_kwargs,
                updates,
                parent_db=parent_db,
                parent_fk_field=parent_fk_field,
            )
        else:
            new_db = diffed.db
    else:  # pragma: no cover — exhaustive
        raise TypeError(f"Unknown change type: {change!r}")

    # 4. Recurse into remaining (InternalNode / BridgeNode) children
    #    top-down, threading down each child's schema class (looked up
    #    from this node's field descriptors) so db-only delete branches
    #    retain it. For ``BridgeNode`` children the parent-FK field
    #    name is derived from this node's Django model via the parent
    #    field's reverse-relation descriptor (the bridge has no
    #    ``parent.<fk>`` element in its NK).
    fields_by_name = (
        {f.name: f for f in extract_fields(cls)} if cls is not None else {}
    )
    for cn in diffed.children:
        if cn.name in lookup_handled:
            continue
        fd = fields_by_name.get(cn.name)
        child_cls = fd.child_class if fd is not None else None
        if child_cls is not None and issubclass(child_cls, BridgeNode):
            child_fk = _bridge_parent_fk_field(cls, cn.name)
        else:
            child_fk = None
        for child in cn.paired:
            if child_fk is None:
                child_fk_for_this = _parent_fk_field_for(child, child_cls)
            else:
                child_fk_for_this = child_fk
            _apply_node(
                child,
                new_db,
                child_fk_for_this,
                creates,
                updates,
                deletes,
                follow_ups,
                lookup_cache,
                schema_class=child_cls,
            )

    # 5. Post-order: fire on_update hook on ascent.
    if diffed.scrape is not None:
        if isinstance(change, CreateOp):
            hook_old, hook_new = None, new_db
        elif isinstance(change, NoOp):
            hook_old, hook_new = diffed.db, diffed.db
        else:  # UpdateOp
            hook_old, hook_new = old_db, new_db
        result = diffed.scrape.on_update(hook_old, hook_new)
        if result:
            follow_ups.extend(result)

    return new_db


def _materialize_pre_children(
    diffed: DiffedNode,
    creates: dict[Any, set[Any]],
    updates: dict[Any, set[Any]],
    deletes: dict[Any, set[Any]],
    follow_ups: list[Callable[..., Any]],
    lookup_cache: dict[int, Any],
) -> tuple[dict[str, Any], set[str]]:
    """Process child fields whose materialization has to happen *before*
    this node's own row mutates, so their PKs feed FK columns on the
    parent.

    Two such field kinds today:
    - ``ChildField`` to a ``ExternalNodeRef``: resolve or create-if-missing
      per the ExternalNodeRef's absence policy.
    - ``ChildField`` to an ``OwnedChild``: parent-owned 1:1 child whose
      FK is on the parent. Full recursive ``_apply_node`` so the owned
      row gets scalar updates, children, and lifecycle hooks; the
      returned DB instance (or ``None`` if deleted) is injected as the
      parent's FK kwarg.

    Returns the FK kwargs plus the set of collection names already
    handled (skipped in the InternalNode recursion below).

    Multi-element ``list[ExternalNodeRef]`` (M2M-style) isn't handled here;
    that would need ``.set([refs])`` after the parent is inserted.
    """
    cls = _schema_class(diffed)
    if cls is None:
        return {}, set()

    fk_kwargs: dict[str, Any] = {}
    handled: set[str] = set()

    for fd in extract_fields(cls):
        if not isinstance(fd, ChildField):
            continue

        is_lookup = issubclass(fd.child_class, ExternalNodeRef)
        is_owned = issubclass(fd.child_class, OwnedChild)
        if not (is_lookup or is_owned):
            continue

        cn = next((c for c in diffed.children if c.name == fd.name), None)
        if cn is None or not cn.paired:
            continue
        # ChildField -> at most one PairedNode.
        ref_diffed = cn.paired[0]

        if is_lookup:
            materialized = _materialize_one_lookup_ref(
                ref_diffed, creates, updates, follow_ups, lookup_cache
            )
        else:
            # OwnedChild: recurse fully so the owned row's own diff
            # (scalar updates, children, hooks) is applied. The
            # ``_apply_node`` recursion handles Create / Update / NoOp
            # / Delete uniformly and returns the resulting DB instance
            # (or ``None`` for deletes).
            materialized = _apply_node(
                ref_diffed,
                parent_db=None,
                parent_fk_field=None,
                creates=creates,
                updates=updates,
                deletes=deletes,
                follow_ups=follow_ups,
                lookup_cache=lookup_cache,
                schema_class=fd.child_class,
            )

        # For OwnedChild we include the kwarg even when ``None`` (so a
        # delete clears the parent's FK). For ExternalNodeRef we omit
        # ``None`` so the parent's FK gets whatever the model default
        # is (typically ``NULL`` for nullable FKs).
        if is_owned or materialized is not None:
            fk_kwargs[fd.name] = materialized
        handled.add(fd.name)

    return fk_kwargs, handled


def _materialize_one_lookup_ref(
    diffed_ref: DiffedNode,
    creates: dict[Any, set[Any]],
    updates: dict[Any, set[Any]],
    follow_ups: list[Callable[..., Any]],
    lookup_cache: dict[int, Any],
) -> Any | None:
    """Resolve / create / update / skip a single ExternalNodeRef PairedNode.

    Returns the DB instance (or ``None`` for ``NoopIfMissing`` with no
    match). Cached by ``id(scrape_ref)`` so shared scrape refs only
    produce a single DB row.

    Matched ExternalNodeRefs (``diffed_ref.db is not None``): if the diff
    produced an ``UpdateOp`` with field changes (typically from an
    explicit ``ScrapeWins`` override on a non-NK field, since the
    ExternalNodeRef class default is ``DBWins``), the field changes are
    applied to the row and ``on_update`` fires with ``(old_db,
    new_db)``. A ``NoOp`` matched row returns unchanged without
    firing any hook.
    """
    if diffed_ref.scrape is None:
        # db-only ExternalNodeRef branches don't currently exist (ExternalNodeRefs
        # have their own lifecycle and aren't deleted as part of an
        # aggregate merge), but guard for safety.
        return diffed_ref.db

    scrape_id = id(diffed_ref.scrape)
    if scrape_id in lookup_cache:
        return lookup_cache[scrape_id]

    # Matched ExternalNodeRef: apply any ``UpdateOp`` field changes from the
    # diff. ``NoOp`` short-circuits unchanged.
    if diffed_ref.db is not None:
        if isinstance(diffed_ref.change, UpdateOp) and (
            diffed_ref.change.field_changes
        ):
            old_db = copy.copy(diffed_ref.db)
            new_db = diffed_ref.db
            for field_name, value in diffed_ref.change.field_changes.items():
                setattr(new_db, field_name, value)
            new_db.save(
                update_fields=list(diffed_ref.change.field_changes.keys())
            )
            updates.setdefault(type(new_db), set()).add(new_db.pk)
            result = diffed_ref.scrape.on_update(old_db, new_db)
            if result:
                follow_ups.extend(result)
        lookup_cache[scrape_id] = diffed_ref.db
        return diffed_ref.db

    cls = type(diffed_ref.scrape)
    policy = cls._mergers_absence_policy

    if policy is ErrorIfMissing:
        raise ValueError(
            f"{cls.__name__}: required ExternalNodeRef not found in DB "
            f"({diffed_ref.scrape!r})"
        )
    if policy is NoopIfMissing:
        lookup_cache[scrape_id] = None
        return None
    assert policy is CreateIfMissing

    # CreateIfMissing: insert a new row using the scrape's values.
    if not isinstance(diffed_ref.change, CreateOp):
        # Unexpected — the unresolved-and-scrape-present case should
        # have produced a CreateOp in L5.
        return None

    model = bound_django_model(cls)
    if model is None:
        raise ValueError(f"{cls.__name__} has no bound Django model.")
    new_db = model._default_manager.create(**diffed_ref.change.values)
    creates.setdefault(model, set()).add(new_db.pk)
    lookup_cache[scrape_id] = new_db

    # Fire on_create / on_update hook for the ExternalNodeRef.
    result = diffed_ref.scrape.on_update(None, new_db)
    if result:
        follow_ups.extend(result)

    return new_db


# ---------------------------------------------------------------------------
# Create / Update / Delete primitives
# ---------------------------------------------------------------------------


def _apply_create(
    diffed: DiffedNode,
    parent_db: Any | None,
    parent_fk_field: str | None,
    lookup_fk_kwargs: dict[str, Any],
    creates: dict[Any, set[Any]],
) -> Any:
    assert diffed.scrape is not None
    assert isinstance(diffed.change, CreateOp)
    cls = type(diffed.scrape)
    model = bound_django_model(cls)
    if model is None:
        raise ValueError(f"{cls.__name__} has no bound Django model.")

    kwargs = {**diffed.change.values, **lookup_fk_kwargs}
    if parent_fk_field is not None and parent_db is not None:
        kwargs[parent_fk_field] = parent_db

    new_db = model._default_manager.create(**kwargs)
    creates.setdefault(model, set()).add(new_db.pk)
    return new_db


def _apply_update(
    diffed: DiffedNode,
    fk_kwargs: dict[str, Any],
    updates: dict[Any, set[Any]],
    parent_db: Any | None = None,
    parent_fk_field: str | None = None,
) -> Any:
    """Apply scalar field changes plus any pre-materialized FK changes
    to an existing row.

    ``fk_kwargs`` is set by ``_materialize_pre_children`` and carries
    the resolved/created/deleted state of ``ExternalNodeRef`` and
    ``OwnedChild`` siblings. For matched FKs whose PKs match the
    row's existing FK value, the FK is *not* re-written (no-op
    optimization); for genuine FK changes (e.g., an ``OwnedChild``
    that appeared/disappeared, or a ``BridgeNode``'s previously-NULL
    parent FK getting filled in by the second merge), the new value
    is applied.

    For ``BridgeNode`` children, ``parent_db`` + ``parent_fk_field``
    inject the parent FK kwarg: a globally-matched bridge row whose
    parent-side FK is NULL gets written; one that already points at
    this parent is a no-op.
    """
    assert diffed.db is not None
    db_row = diffed.db
    field_changes = (
        diffed.change.field_changes
        if isinstance(diffed.change, UpdateOp)
        else {}
    )

    # Apply scalar field changes from the diff.
    for field_name, value in field_changes.items():
        setattr(db_row, field_name, value)

    # Build the effective FK kwargs: pre-materialized children plus,
    # for BridgeNode rows, the parent FK column the framework owns.
    effective_fk_kwargs = dict(fk_kwargs)
    if (
        parent_fk_field is not None
        and parent_db is not None
        and diffed.scrape is not None
        and isinstance(diffed.scrape, BridgeNode)
    ):
        effective_fk_kwargs.setdefault(parent_fk_field, parent_db)

    # Apply FK changes — only those whose value actually differs from
    # the row's current FK.
    fk_changed_names: list[str] = []
    for fk_name, fk_value in effective_fk_kwargs.items():
        current_pk = getattr(db_row, f"{fk_name}_id", None)
        new_pk = fk_value.pk if fk_value is not None else None
        if current_pk != new_pk:
            setattr(db_row, fk_name, fk_value)
            fk_changed_names.append(fk_name)

    update_field_names = list(field_changes.keys()) + fk_changed_names
    if update_field_names:
        db_row.save(update_fields=update_field_names)
        updates.setdefault(type(db_row), set()).add(db_row.pk)
    return db_row


def _fk_kwargs_imply_change(
    db_row: Any, fk_kwargs: dict[str, Any]
) -> bool:
    """Return True iff any ``fk_kwargs`` value differs from the row's
    current FK PK — used to detect when a ``NoOp`` parent needs an
    upgrade to ``UpdateOp`` because an ``OwnedChild`` appeared or
    disappeared.
    """
    for fk_name, fk_value in fk_kwargs.items():
        current_pk = getattr(db_row, f"{fk_name}_id", None)
        new_pk = fk_value.pk if fk_value is not None else None
        if current_pk != new_pk:
            return True
    return False


def _apply_delete(
    diffed: DiffedNode,
    creates: dict[Any, set[Any]],
    updates: dict[Any, set[Any]],
    deletes: dict[Any, set[Any]],
    follow_ups: list[Callable[..., Any]],
    lookup_cache: dict[int, Any],
    cls: type[Node] | None,
) -> None:
    # Post-order: delete children first (threading each child's schema
    # class so its on_delete can fire).
    fields_by_name = (
        {f.name: f for f in extract_fields(cls)} if cls is not None else {}
    )
    for cn in diffed.children:
        fd = fields_by_name.get(cn.name)
        child_cls = fd.child_class if fd is not None else None
        for child in cn.paired:
            _apply_node(
                child,
                parent_db=None,
                parent_fk_field=None,
                creates=creates,
                updates=updates,
                deletes=deletes,
                follow_ups=follow_ups,
                lookup_cache=lookup_cache,
                schema_class=child_cls,
            )
    assert diffed.db is not None
    # Snapshot before delete: Django clears ``pk`` on the instance when
    # ``.delete()`` runs, so we copy first to preserve the PK and other
    # field values for the on_delete hook.
    old_db_snapshot = copy.copy(diffed.db)
    pk = diffed.db.pk
    model = type(diffed.db)
    diffed.db.delete()
    deletes.setdefault(model, set()).add(pk)

    # Fire on_delete. If we have a live scrape Node, use it directly;
    # for db-only deletes (the common ``ScrapeClobbers`` case), the
    # framework synthesizes a Node via ``cls.model_construct()`` so the
    # hook can be invoked. ``self``'s field values on the synthetic
    # instance aren't populated — hooks should read from the ``old_db``
    # argument.
    scrape_for_hook: Node | None = diffed.scrape
    if scrape_for_hook is None and cls is not None:
        scrape_for_hook = cls.model_construct()
    if scrape_for_hook is not None:
        result = scrape_for_hook.on_update(old_db_snapshot, None)
        if result:
            follow_ups.extend(result)
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parent_fk_field_for(
    diffed: DiffedNode, schema_class: type[Node] | None = None
) -> str | None:
    """Return the FK field name on this child's model that points to
    its parent, derived from the child's NK ``ParentPath``.

    ``schema_class`` is the fallback when ``diffed.scrape is None``
    (db-only branches). When neither is available we return ``None``
    and the caller relies on Django ``CASCADE`` semantics.
    """
    cls = (
        type(diffed.scrape) if diffed.scrape is not None else schema_class
    )
    if cls is None:
        return None
    for element in classify_nk(cls):
        if isinstance(element, ParentPath):
            parts = path_parts(element.path)
            # Single-level parent reference (parent.<fk_name>) is what
            # we support for FK-injection. Multi-level (parent.parent.X)
            # is informational and skipped here.
            if len(parts) == 2 and parts[0] == "parent":
                return parts[1]
    return None


def _schema_class(diffed: DiffedNode) -> type[Node] | None:
    """The Pydantic schema class for this diffed node, if known."""
    if diffed.scrape is None:
        return None
    return type(diffed.scrape)


def _bridge_parent_fk_field(
    parent_cls: type[Node] | None, parent_field_name: str
) -> str | None:
    """Derive the FK field name on a ``BridgeNode``'s Django model
    that points back to ``parent_cls``, via the parent's reverse-
    relation descriptor for ``parent_field_name``.

    Convention: the Pydantic field name on the parent schema matches
    the Django ``related_name`` (or default reverse accessor) of the
    bridge model's FK. Looking the field up on the parent's Django
    model yields a reverse-relation object whose ``.field.name`` is
    the actual FK column on the bridge.
    """
    if parent_cls is None:
        return None
    parent_model = bound_django_model(parent_cls)
    if parent_model is None:
        return None
    try:
        rel = parent_model._meta.get_field(parent_field_name)
    except Exception:
        return None
    field = getattr(rel, "field", None)
    if field is None:
        return None
    return field.name
