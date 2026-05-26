"""Duplicate-NK scrape-row dedup via strategy-driven fold.

Two entry points:

- :func:`collapse_duplicate_scrape_nks` — folds duplicate-NK
  ``InternalNode`` children of one parent into a single representative
  before pairing.
- :func:`fold_lookup_refs_in_tree` — folds duplicate-NK
  ``ExternalNodeRef`` instances scattered anywhere in the scrape tree by
  mutating parent fields to point at a single canonical per NK group.

When a scrape Aggregate emits multiple instances sharing a natural
key, the framework collapses them into a single representative row
*before* pairing. The legacy SCOTUS merger does the same idempotently
via ``get_or_create`` on ``AttorneyOrganizationAssociation``; this
module is the general framework-level equivalent for both
``InternalNode`` and ``ExternalNodeRef`` shapes.

Approach: treat the first scrape row of an NK group as a synthetic
"db" and reduce subsequent rows into it using the schema's *existing*
per-field strategies — ``ScrapeWins`` / ``ScrapeWinsIfPresent`` /
``DBWins`` / ``Custom`` for scalars, ``ScrapeClobbers`` / ``Union`` /
``DBClobbers`` / ``CustomCollection`` for collections. The semantics
fall out for free:

- ``ScrapeWins`` scalar: last write wins.
- ``ScrapeWinsIfPresent`` scalar: last non-``None`` write wins.
- ``DBWins`` scalar: first write wins.
- ``Custom(fn)`` scalar: ``fn(scrape=row_i+1, db=accumulator)`` per step.
- ``ScrapeClobbers`` collection: later list replaces earlier.
- ``Union`` collection: pairwise NK-union, recursing into the merged
  set (so duplicate-NK rows nested inside ``Union``-strategy collections
  collapse the same way).
- ``DBClobbers`` collection: earlier list wins.
- ``CustomCollection``: ``ScrapeClobbers`` fallback (the custom fn's
  pair / scrape_only / db_only signature isn't a natural fit for the
  scrape-vs-scrape fold; drivers wanting more nuance there should
  emit deduped data themselves).

The fold operates on ``InternalNode`` subclasses only; aggregate
roots are paired one-to-one by the orchestrator (no dedup possible).
``allow_duplicates=True`` nodes are NOT deduped — the bipartite
matcher there relies on raw multiplicities to drive its edit-cost
assignment.

Public entry point: :func:`collapse_duplicate_scrape_nks`.
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from cl.scrapers.mergers.fields import (
    ChildField,
    ChildListField,
    FieldDescriptor,
    ScalarField,
    extract_fields,
)
from cl.scrapers.mergers.nodes import ExternalNodeRef, Node
from cl.scrapers.mergers.strategies import (
    CollectionStrategy,
    Custom,
    CustomCollection,
    ScalarStrategy,
    _DBClobbers,
    _DBWins,
    _ScrapeClobbers,
    _ScrapeWins,
    _ScrapeWinsIfPresent,
    _Union,
)

logger = logging.getLogger(__name__)


def collapse_duplicate_scrape_nks(
    scrape_items: list[Node],
    cls: type[Node],
    key_fn: Callable[[Any], Any],
    *,
    build_key_fn: Callable[[type[Node]], Callable[[Any], Any]] | None = None,
) -> list[Node]:
    """Fold duplicate-NK scrape rows into a single representative per NK.

    Order-preserving: each NK keeps the position of its first occurrence.
    Same-list pass-through when no duplicates are present (no allocation
    of new Node instances).

    :param scrape_items: the scrape children to fold.
    :param cls: the child Node class — used to look up per-field
        strategies via :func:`cl.scrapers.mergers.fields.extract_fields`.
    :param key_fn: callable returning the natural-key tuple for a
        Node. Typically built via
        ``cl.scrapers.mergers.paired._build_nk_key_fn``.
    :param build_key_fn: optional factory ``(child_cls) -> key_fn`` used
        to obtain key functions for *nested* child classes during a
        ``Union`` collection fold. Defaults to ``lambda c: key_fn`` —
        which works for the common shape where the same key function
        applies (only the top level dedups). Pass a real factory only
        if recursive Union folds need NK keys for differently-shaped
        children.

    :returns: deduped list. Items with no NK collisions are the
        original instances; folded rows are new
        ``model_construct``-built instances.
    """
    field_descriptors = extract_fields(cls)
    # Default: re-use the same key_fn for any recursive Union fold (the
    # nested child class may share NK shape with the outer; callers
    # who need per-class key functions pass ``build_key_fn``).
    if build_key_fn is None:
        build_key_fn = lambda _c: key_fn  # noqa: E731

    # Pass 1: detect collisions to know whether to fold at all.
    seen: set = set()
    has_collision = False
    for item in scrape_items:
        k = key_fn(item)
        if k in seen:
            has_collision = True
            break
        seen.add(k)
    if not has_collision:
        return scrape_items

    return _fold_run(
        scrape_items, cls, key_fn, field_descriptors, build_key_fn
    )


def _fold_run(
    items: list[Node],
    cls: type[Node],
    key_fn: Callable[[Any], Any],
    field_descriptors: list[FieldDescriptor],
    build_key_fn: Callable[[type[Node]], Callable[[Any], Any]],
) -> list[Node]:
    """Run the collapse — insertion order preserved via ``dict``."""
    accumulator: dict[Any, Node] = {}
    fold_count = 0
    for item in items:
        k = key_fn(item)
        existing = accumulator.get(k)
        if existing is None:
            accumulator[k] = item
        else:
            accumulator[k] = _fold_pair(
                existing, item, field_descriptors, build_key_fn
            )
            fold_count += 1
    if fold_count:
        logger.info(
            "collapse_duplicate_scrape_nks: folded %d duplicate-NK "
            "scrape rows under %s",
            fold_count,
            cls.__name__,
        )
    return list(accumulator.values())


def _fold_pair(
    acc: Node,
    nxt: Node,
    field_descriptors: list[FieldDescriptor],
    build_key_fn: Callable[[type[Node]], Callable[[Any], Any]],
) -> Node:
    """Merge ``nxt`` into ``acc``, treating ``acc`` as synthetic 'db'
    and ``nxt`` as 'scrape' across every field's strategy."""
    new_values: dict[str, Any] = {}
    for fd in field_descriptors:
        acc_val = getattr(acc, fd.name)
        nxt_val = getattr(nxt, fd.name)
        if isinstance(fd, ScalarField):
            new_values[fd.name] = _fold_scalar(
                acc_val, nxt_val, fd.strategy
            )
        elif isinstance(fd, ChildField):
            new_values[fd.name] = _fold_optional_child(
                acc_val,
                nxt_val,
                fd.strategy,
                fd.child_class,
                build_key_fn,
            )
        elif isinstance(fd, ChildListField):
            new_values[fd.name] = _fold_child_list(
                acc_val,
                nxt_val,
                fd.strategy,
                fd.child_class,
                build_key_fn,
            )
    # ``model_construct`` skips re-validation: every input value is
    # already a validated Node-side value (either an original
    # validated field or a previously-folded one). Re-running
    # validators here would force defaults to re-apply, which is wrong
    # for the fold (we want the folded value, not the default).
    return type(acc).model_construct(**new_values)


# ---------------------------------------------------------------------------
# Scalar fold
# ---------------------------------------------------------------------------


def _fold_scalar(
    acc_val: Any, nxt_val: Any, strategy: ScalarStrategy
) -> Any:
    """Reduce two values per the field's scalar strategy.

    Strategies were designed for "scrape vs DB"; here ``acc`` plays
    the DB role and ``nxt`` plays the scrape role. The semantics
    described in the module docstring fall out.
    """
    if isinstance(strategy, _DBWins):
        return acc_val
    if isinstance(strategy, _ScrapeWinsIfPresent):
        return nxt_val if nxt_val is not None else acc_val
    if isinstance(strategy, Custom):
        return strategy.fn(nxt_val, acc_val)
    # ``_ScrapeWins`` and any unrecognized scalar strategy: later wins.
    return nxt_val


# ---------------------------------------------------------------------------
# Child fold
# ---------------------------------------------------------------------------


def _fold_child_list(
    acc_val: list[Node],
    nxt_val: list[Node],
    strategy: CollectionStrategy,
    child_cls: type[Node],
    build_key_fn: Callable[[type[Node]], Callable[[Any], Any]],
) -> list[Node]:
    """Reduce two child-collection lists per the collection strategy."""
    if isinstance(strategy, _DBClobbers):
        return list(acc_val)
    if isinstance(strategy, _Union):
        merged = list(acc_val) + list(nxt_val)
        # Recursively dedupe the merged set — any duplicate NKs
        # introduced by the union collapse via the same fold.
        return collapse_duplicate_scrape_nks(
            merged,
            child_cls,
            build_key_fn(child_cls),
            build_key_fn=build_key_fn,
        )
    if isinstance(strategy, CustomCollection):
        # CustomCollection's signature (pairs, scrape_only, db_only)
        # is for the apply-phase reconciliation, not for fold; default
        # to ScrapeClobbers semantics. Drivers needing custom fold
        # behavior should emit deduped data upstream.
        return list(nxt_val)
    # ``_ScrapeClobbers`` and unrecognized fallback: later wins.
    return list(nxt_val)


def _fold_optional_child(
    acc_val: Node | None,
    nxt_val: Node | None,
    strategy: CollectionStrategy,
    child_cls: type[Node],
    build_key_fn: Callable[[type[Node]], Callable[[Any], Any]],
) -> Node | None:
    """Reduce a 0-or-1 child slot per the collection strategy."""
    if isinstance(strategy, _DBClobbers):
        return acc_val
    if isinstance(strategy, _Union):
        if acc_val is None:
            return nxt_val
        if nxt_val is None:
            return acc_val
        # Both present: there's only one slot, so by Union semantics
        # the merged child is the fold of the two — same NK by
        # construction, so collapse-of-two yields a single element.
        merged = collapse_duplicate_scrape_nks(
            [acc_val, nxt_val],
            child_cls,
            build_key_fn(child_cls),
            build_key_fn=build_key_fn,
        )
        return merged[0] if merged else None
    if isinstance(strategy, CustomCollection):
        return nxt_val
    # ``_ScrapeClobbers`` and unrecognized fallback.
    return nxt_val


# ---------------------------------------------------------------------------
# ExternalNodeRef NK-fold (in-tree mutation)
# ---------------------------------------------------------------------------


def fold_lookup_refs_in_tree(scrape_root: Node | None) -> dict[int, Node]:
    """Fold duplicate-NK ``ExternalNodeRef`` instances by mutating the tree.

    The framework's ``_collect_lookup_refs`` dedupes by Python ``id``,
    so distinct ``ExternalNodeRef`` instances with the same NK but different
    scalar fields are treated as separate logical refs — each would
    independently materialize a DB row. This function collapses such
    groups into a single *canonical* instance per ``(class, NK)``
    group by:

    1. Walking the tree to collect every ``ExternalNodeRef`` grouped by
       ``(class, NK)``.
    2. For each group with more than one instance, folding the non-NK
       scalar fields into the first occurrence (the canonical), using
       each field's declared :class:`ScalarStrategy`.
    3. Walking the tree a second time and rewriting every parent
       field that previously held a non-canonical instance so it now
       holds the canonical.

    After mutation, the framework's existing id-keyed dedup +
    resolution flow naturally produces one DB row per canonical.

    Pydantic models are mutable by default (no ``frozen=True``), so
    in-place scalar mutation is safe. The scrape tree the caller
    passed in IS mutated — document this for callers if they expect
    immutability.

    :returns: ``id(original) -> canonical_node`` for every folded
        original. Empty when no folds were necessary.
    """
    if scrape_root is None:
        return {}

    # Deferred import to dodge the circular dep with paired.py (which
    # imports from dedup at module load time).
    from cl.scrapers.mergers.paired import (
        _lookup_ref_nk_tuple,
        _visit_for_lookup_refs,
    )

    raw: dict[type[Node], list[Node]] = defaultdict(list)
    _visit_for_lookup_refs(scrape_root, raw)

    # Per-class id-dedup so a single Python instance referenced from
    # multiple places only contributes once to NK grouping.
    refs_by_class: dict[type[Node], list[Node]] = {}
    for cls, items in raw.items():
        seen_ids: set[int] = set()
        unique: list[Node] = []
        for r in items:
            if id(r) not in seen_ids:
                seen_ids.add(id(r))
                unique.append(r)
        refs_by_class[cls] = unique

    id_remap: dict[int, Node] = {}
    folds_per_class: dict[str, int] = {}

    for cls, items in refs_by_class.items():
        if len(items) < 2:
            continue
        by_nk: dict[tuple, list[Node]] = defaultdict(list)
        for ref in items:
            nk = _lookup_ref_nk_tuple(ref, cls)
            by_nk[nk].append(ref)
        field_descriptors = extract_fields(cls)
        scalar_fds = [
            fd for fd in field_descriptors if isinstance(fd, ScalarField)
        ]
        for group in by_nk.values():
            if len(group) < 2:
                continue
            canonical = group[0]
            # Fold each subsequent instance's scalars into the canonical
            # using its field strategy. NK-typed scalars (in any sane
            # design) will always be equal across the group so the fold
            # is a no-op on those; non-NK scalars (email/phone/etc.) get
            # the strategy-driven merge.
            for other in group[1:]:
                for fd in scalar_fds:
                    acc = getattr(canonical, fd.name)
                    nxt = getattr(other, fd.name)
                    if acc != nxt:
                        new_val = _fold_scalar(acc, nxt, fd.strategy)
                        setattr(canonical, fd.name, new_val)
                id_remap[id(other)] = canonical
            folds_per_class[cls.__name__] = (
                folds_per_class.get(cls.__name__, 0) + len(group) - 1
            )

    if id_remap:
        _rewrite_lookup_ref_refs(scrape_root, id_remap)
        for cls_name, count in folds_per_class.items():
            logger.info(
                "fold_lookup_refs_in_tree: collapsed %d duplicate-NK "
                "%s instances",
                count,
                cls_name,
            )
    return id_remap


def _rewrite_lookup_ref_refs(
    node: Node | None, id_remap: dict[int, Node]
) -> None:
    """Walk the tree and replace every ``ExternalNodeRef`` field that holds a
    non-canonical instance with its canonical from ``id_remap``."""
    if node is None:
        return
    cls = type(node)
    for fd in extract_fields(cls):
        if isinstance(fd, ChildField):
            child = getattr(node, fd.name)
            if child is None:
                continue
            if isinstance(child, ExternalNodeRef):
                canonical = id_remap.get(id(child))
                if canonical is not None and canonical is not child:
                    setattr(node, fd.name, canonical)
            else:
                _rewrite_lookup_ref_refs(child, id_remap)
        elif isinstance(fd, ChildListField):
            children = getattr(node, fd.name) or []
            for i, child in enumerate(children):
                if child is None:
                    continue
                if isinstance(child, ExternalNodeRef):
                    canonical = id_remap.get(id(child))
                    if canonical is not None and canonical is not child:
                        children[i] = canonical
                else:
                    _rewrite_lookup_ref_refs(child, id_remap)
