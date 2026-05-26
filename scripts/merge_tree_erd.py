#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pydantic>=2.0",
# ]
# ///
"""Generate a mermaid ER diagram from a merger Pydantic schema module.

Walks the Node tree rooted at the module's ``Aggregate`` subclass and
emits a mermaid ``erDiagram`` whose:

- Entities are the bound Django models. Each entity block lists the
  schema's *scalar* (non-edge) fields, their type, an NK marker (``PK``),
  and the resolved scalar strategy.
- Edges are labelled with the framework node kind that binds parent to
  child (``Internal`` / ``Owned`` / ``External`` / ``Bridge`` /
  ``Preresolved``) plus the resolved collection strategy and the
  Pydantic field name.
- A ``%%`` comment above each entity records class-level kwargs
  (``lock_for_update``, ``allow_duplicates``, ``path_scoped``,
  ``absence_policy``, schema defaults).

Usage (inside the django container)::

    podman exec cl-django python scripts/merge_tree_erd.py \\
        cl.scrapers.mergers.state.texas.tames

Or via ``uv`` from a checkout where ``cl.*`` is importable::

    uv run scripts/merge_tree_erd.py cl.scrapers.mergers.state.texas.tames
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import types
import typing
from pathlib import Path
from typing import Annotated, Any, get_args, get_origin


def _bootstrap_django() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cl.settings")
    import django

    django.setup()


# ---------------------------------------------------------------------------
# Annotation unwrapping
# ---------------------------------------------------------------------------


def _strip_annotated(ann: Any) -> Any:
    if get_origin(ann) is Annotated:
        return get_args(ann)[0]
    return ann


def _strip_optional(ann: Any) -> Any:
    origin = get_origin(ann)
    if origin is typing.Union or origin is types.UnionType:
        non_none = [a for a in get_args(ann) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return ann


# ---------------------------------------------------------------------------
# Strategy / type display helpers
# ---------------------------------------------------------------------------


def _strategy_name(strategy: Any) -> str:
    """Render a ScalarStrategy / CollectionStrategy instance as a string.

    Internal singletons (``_ScrapeWins``, ``_Union``, etc.) drop their
    leading underscore; ``Custom`` / ``CustomCollection`` instances
    include the wrapped function's ``__name__``.
    """
    if strategy is None:
        return "?"
    cls_name = type(strategy).__name__
    display = cls_name[1:] if cls_name.startswith("_") else cls_name
    fn = getattr(strategy, "fn", None)
    if fn is not None:
        fn_name = getattr(fn, "__name__", repr(fn))
        return f"{display}({fn_name})"
    return display


def _resolve_scalar_strategy(field_info: Any, node_cls: type) -> Any:
    """Return the effective ScalarStrategy for a field."""
    from cl.scrapers.mergers.strategies import ScalarStrategy

    for m in field_info.metadata or []:
        if isinstance(m, ScalarStrategy):
            return m
    return node_cls._mergers_default_field


def _resolve_collection_strategy(field_info: Any, node_cls: type) -> Any:
    """Return the effective CollectionStrategy for a field."""
    from cl.scrapers.mergers.strategies import CollectionStrategy

    for m in field_info.metadata or []:
        if isinstance(m, CollectionStrategy):
            return m
    return node_cls._mergers_default_collection


def _type_name(annotation: Any) -> str:
    """Render a Pydantic field annotation as a compact type label."""
    from cl.scrapers.mergers import PreResolvedRef

    a = _strip_optional(_strip_annotated(annotation))

    if get_origin(a) is PreResolvedRef:
        args = get_args(a)
        if args and isinstance(args[0], type):
            return args[0].__name__
        return "PreResolvedRef"

    if get_origin(a) is list:
        inner = get_args(a)
        return f"list_{_type_name(inner[0])}" if inner else "list"

    if isinstance(a, type):
        return a.__name__

    name = getattr(a, "__name__", None)
    return name if name else str(a).replace(" ", "")


# ---------------------------------------------------------------------------
# Node kind classification
# ---------------------------------------------------------------------------


_KIND_LABELS: tuple[tuple[str, str], ...] = (
    ("BridgeNode", "Bridge"),
    ("ExternalNodeRef", "External"),
    ("OwnedChild", "Owned"),
    ("InternalNode", "Internal"),
)


def _kind_label(cls: type) -> str | None:
    from cl.scrapers.mergers import (
        BridgeNode,
        ExternalNodeRef,
        InternalNode,
        OwnedChild,
    )

    kind_to_class: dict[str, type] = {
        "BridgeNode": BridgeNode,
        "ExternalNodeRef": ExternalNodeRef,
        "OwnedChild": OwnedChild,
        "InternalNode": InternalNode,
    }
    for kind_name, label in _KIND_LABELS:
        if issubclass(cls, kind_to_class[kind_name]):
            return label
    return None


def _classify_field(
    annotation: Any,
) -> tuple[str | None, type | None, bool, type | None]:
    """Returns ``(label, child_node_cls, is_collection, preresolved_model)``."""
    from cl.scrapers.mergers import PreResolvedRef

    a = _strip_optional(_strip_annotated(annotation))

    is_collection = False
    if get_origin(a) is list:
        is_collection = True
        a = _strip_optional(_strip_annotated(get_args(a)[0]))

    if get_origin(a) is PreResolvedRef:
        args = get_args(a)
        model = args[0] if args and isinstance(args[0], type) else None
        return ("Preresolved", None, is_collection, model)

    if isinstance(a, type):
        label = _kind_label(a)
        if label is not None:
            return (label, a, is_collection, None)

    return (None, None, is_collection, None)


# ---------------------------------------------------------------------------
# Class-level kwargs
# ---------------------------------------------------------------------------


def _class_kwargs(node_cls: type) -> dict[str, str]:
    """Return the merger framework kwargs set on this Node subclass."""
    from cl.scrapers.mergers import (
        Aggregate,
        BridgeNode,
        ExternalNodeRef,
        InternalNode,
    )

    out: dict[str, str] = {
        "default_field": _strategy_name(node_cls._mergers_default_field),
        "default_collection": _strategy_name(
            node_cls._mergers_default_collection
        ),
    }
    if issubclass(node_cls, Aggregate):
        out["lock_for_update"] = str(node_cls._mergers_lock_for_update)
    if issubclass(node_cls, (InternalNode, ExternalNodeRef, BridgeNode)):
        out["allow_duplicates"] = str(node_cls._mergers_allow_duplicates)
    if issubclass(node_cls, (ExternalNodeRef, BridgeNode)):
        out["absence_policy"] = node_cls._mergers_absence_policy.name
    if issubclass(node_cls, ExternalNodeRef):
        out["path_scoped"] = str(node_cls._mergers_path_scoped)
    return out


def _nk_field_names(node_cls: type) -> set[str]:
    """Field-name strings in ``node_cls.natural_key``.

    Excludes ``PathRef`` entries (those reference parent fields, which
    don't appear in this entity's attribute list).
    """
    nk = getattr(node_cls, "natural_key", None) or ()
    return {x for x in nk if isinstance(x, str)}


# ---------------------------------------------------------------------------
# Discovery + walk
# ---------------------------------------------------------------------------


def _find_aggregate(module: types.ModuleType, root_name: str | None) -> type:
    from cl.scrapers.mergers import Aggregate

    if root_name:
        cls = getattr(module, root_name, None)
        if cls is None or not (
            isinstance(cls, type) and issubclass(cls, Aggregate)
        ):
            raise SystemExit(
                f"{root_name!r} is not an Aggregate subclass in {module.__name__}"
            )
        return cls

    candidates = [
        obj
        for _, obj in vars(module).items()
        if (
            isinstance(obj, type)
            and obj is not Aggregate
            and issubclass(obj, Aggregate)
            and obj.__module__ == module.__name__
        )
    ]
    if not candidates:
        raise SystemExit(f"No Aggregate subclass found in {module.__name__}")
    if len(candidates) > 1:
        names = ", ".join(c.__name__ for c in candidates)
        raise SystemExit(
            f"Multiple Aggregates in {module.__name__}: {names}. "
            "Pick one with --root."
        )
    return candidates[0]


# parent_entity, target_entity, kind_label, strategy_name, is_collection, field_name
# strategy_name is the *scalar* strategy for Preresolved edges and the
# *collection* strategy for Internal/Owned/External/Bridge edges.
Edge = tuple[str, str, str, str, bool, str]


def _walk(
    root: type,
) -> tuple[list[str], dict[str, type], list[Edge]]:
    """BFS over Node classes reachable from ``root``.

    Returns ``(entity_order, entity_to_node, edges)`` where
    ``entity_to_node`` maps each entity name to the *first* Node subclass
    we saw binding it. Two Node subclasses bound to the same Django model
    (e.g. Texas's two BridgeNodes on ``CaseTransfer``) collapse to one
    entity with the first-visited class as its attribute source.
    Preresolved-only targets (``Court``, ``Person``) have no Node class
    and don't appear in the dict.
    """
    from cl.scrapers.mergers import bound_django_model

    def _entity(cls: type) -> str:
        model = bound_django_model(cls)
        return model.__name__ if model is not None else cls.__name__

    entity_order: list[str] = []
    seen_entities: set[str] = set()
    entity_to_node: dict[str, type] = {}

    def _add_entity(name: str, node_cls: type | None) -> None:
        if name not in seen_entities:
            seen_entities.add(name)
            entity_order.append(name)
        if node_cls is not None and name not in entity_to_node:
            entity_to_node[name] = node_cls

    edges: list[Edge] = []
    seen_edges: set[Edge] = set()

    def _add_edge(edge: Edge) -> None:
        if edge not in seen_edges:
            seen_edges.add(edge)
            edges.append(edge)

    queue: list[type] = [root]
    visited: set[type] = {root}
    _add_entity(_entity(root), root)

    while queue:
        parent_cls = queue.pop(0)
        parent_entity = _entity(parent_cls)
        for field_name, field_info in parent_cls.model_fields.items():
            label, child_cls, is_coll, pre_model = _classify_field(
                field_info.annotation
            )
            if label is None:
                continue
            # Strategy resolution mirrors cl.scrapers.mergers.fields.
            # extract_fields: PreResolvedRef → scalar strategy; single
            # child Node and list[Node] → collection strategy.
            if label == "Preresolved":
                strat = _strategy_name(
                    _resolve_scalar_strategy(field_info, parent_cls)
                )
                target = (
                    pre_model.__name__ if pre_model is not None else "Model"
                )
                _add_entity(target, None)
                _add_edge(
                    (
                        parent_entity,
                        target,
                        label,
                        strat,
                        is_coll,
                        field_name,
                    )
                )
                continue
            strat = _strategy_name(
                _resolve_collection_strategy(field_info, parent_cls)
            )
            assert child_cls is not None
            child_entity = _entity(child_cls)
            _add_entity(child_entity, child_cls)
            _add_edge(
                (
                    parent_entity,
                    child_entity,
                    label,
                    strat,
                    is_coll,
                    field_name,
                )
            )
            if child_cls not in visited:
                visited.add(child_cls)
                queue.append(child_cls)

    return entity_order, entity_to_node, edges


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


# Mermaid ER cardinality strings. Owned/Internal children are
# parent-owned (parent has zero-or-one or zero-or-many children);
# External/Bridge/Preresolved are references-to (many parents may
# point at one row, or at many rows for collection fields).
_CARDINALITY: dict[tuple[str, bool], str] = {
    ("Internal", False): "||--o|",
    ("Internal", True): "||--o{",
    ("Owned", False): "||--o|",
    ("Owned", True): "||--o{",
    ("External", False): "}o--||",
    ("External", True): "}o--o{",
    ("Bridge", False): "}o--||",
    ("Bridge", True): "}o--o{",
    ("Preresolved", False): "}o--||",
    ("Preresolved", True): "}o--o{",
}


def _entity_attributes(node_cls: type) -> list[str]:
    """Scalar (non-edge) fields rendered as mermaid ER attributes."""
    nk_names = _nk_field_names(node_cls)
    lines: list[str] = []
    for field_name, field_info in node_cls.model_fields.items():
        label, _, _, _ = _classify_field(field_info.annotation)
        if label is not None:
            # Edge field — rendered as an edge, not an attribute.
            continue
        type_name = _type_name(field_info.annotation)
        strategy = _strategy_name(
            _resolve_scalar_strategy(field_info, node_cls)
        )
        marker = " PK" if field_name in nk_names else ""
        lines.append(f'        {type_name} {field_name}{marker} "{strategy}"')
    return lines


def render_erd(root: type) -> str:
    entity_order, entity_to_node, edges = _walk(root)
    lines: list[str] = ["erDiagram"]

    for entity in entity_order:
        node_cls = entity_to_node.get(entity)
        if node_cls is not None:
            kwargs = _class_kwargs(node_cls)
            kw_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            lines.append(
                f"    %% {entity} ({node_cls.__name__}): {kw_str}"
            )
        lines.append(f"    {entity} {{")
        if node_cls is not None:
            lines.extend(_entity_attributes(node_cls))
        lines.append("    }")

    for parent, target, label, strat, is_coll, field_name in edges:
        cardinality = _CARDINALITY[(label, is_coll)]
        edge_label = f"{label}/{strat}: {field_name}"
        lines.append(
            f'    {parent} {cardinality} {target} : "{edge_label}"'
        )

    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Render a merger schema tree as a mermaid ER diagram.",
    )
    p.add_argument(
        "module",
        help="dotted path to a merger schema module "
        "(e.g. cl.scrapers.mergers.state.texas.tames)",
    )
    p.add_argument(
        "--root",
        help="Aggregate class name (if module declares more than one).",
    )
    args = p.parse_args()

    _bootstrap_django()
    module = importlib.import_module(args.module)
    root = _find_aggregate(module, args.root)
    print(render_erd(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
