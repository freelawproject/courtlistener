"""Field descriptor extraction for Node subclasses.

Given a ``Node`` subclass, ``extract_fields(cls)`` walks the Pydantic
fields and produces a typed descriptor per field describing what kind
it is and which strategy applies.

Variants:
- ``ScalarField`` — primitives and PreResolvedRefs (uniform: a single
  value written to one column on the bound Django model).
- ``ChildField`` — a single child ``Node`` instance, possibly optional.
- ``ChildListField`` — ``list[ChildNode]``.

Strategy resolution priority:
1. ``Annotated[..., Strategy]`` metadata on the field.
2. The class's ``_mergers_default_field`` (scalars) or
   ``_mergers_default_collection`` (collections).

See cl/scrapers/MERGERS_IN_THEORY.md.
"""

import types
from dataclasses import dataclass
from typing import Any, Union, get_args, get_origin

from cl.scrapers.mergers.nodes import Node, PreResolvedRef, _PreResolvedMarker
from cl.scrapers.mergers.strategies import (
    CollectionStrategy,
    ScalarStrategy,
)

# ---------------------------------------------------------------------------
# Field descriptors
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScalarField:
    """A scalar field — primitive type or PreResolvedRef.

    If ``preresolved_model`` is set, this field was declared as
    ``PreResolvedRef[Model]`` and the caller will supply a Django
    instance directly.
    """

    name: str
    annotation: type
    strategy: ScalarStrategy
    is_optional: bool
    preresolved_model: type | None = None


@dataclass(frozen=True)
class ChildField:
    """A single child ``Node`` instance (possibly optional).

    Optional children are treated as 0-or-1 collections under the
    collection strategy (see MERGERS_IN_THEORY.md, Tree-shape
    conventions).
    """

    name: str
    child_class: type[Node]
    strategy: CollectionStrategy
    is_optional: bool


@dataclass(frozen=True)
class ChildListField:
    """``list[ChildNode]``."""

    name: str
    child_class: type[Node]
    strategy: CollectionStrategy


type FieldDescriptor = ScalarField | ChildField | ChildListField


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_fields(cls: type[Node]) -> list[FieldDescriptor]:
    """Inspect ``cls.model_fields`` and produce a descriptor per field.

    :raises TypeError: if a strategy of the wrong kind is applied (scalar
        on a list, collection on a scalar), or if multiple strategies
        appear in the same ``Annotated`` metadata.
    """
    fields: list[FieldDescriptor] = []
    for name, fi in cls.model_fields.items():
        ann = fi.annotation
        metadata = list(fi.metadata)

        is_optional, ann = _strip_optional(ann)

        # PreResolvedRef has highest precedence: it might be wrapped
        # around any inner type.
        pr_model = _preresolved_inner(ann)
        if pr_model is not None:
            strategy = _resolve_scalar_strategy(metadata, cls)
            fields.append(
                ScalarField(
                    name=name,
                    annotation=pr_model,
                    strategy=strategy,
                    is_optional=is_optional,
                    preresolved_model=pr_model,
                )
            )
            continue

        # list[T]?
        if get_origin(ann) is list:
            (inner,) = get_args(ann)
            if isinstance(inner, type) and issubclass(inner, Node):
                strategy = _resolve_collection_strategy(metadata, cls)
                fields.append(
                    ChildListField(
                        name=name,
                        child_class=inner,
                        strategy=strategy,
                    )
                )
            else:
                # list of primitives; treat as scalar.
                strategy = _resolve_scalar_strategy(metadata, cls)
                fields.append(
                    ScalarField(
                        name=name,
                        annotation=ann,
                        strategy=strategy,
                        is_optional=is_optional,
                    )
                )
            continue

        # Single child node?
        if isinstance(ann, type) and issubclass(ann, Node):
            strategy = _resolve_collection_strategy(metadata, cls)
            fields.append(
                ChildField(
                    name=name,
                    child_class=ann,
                    strategy=strategy,
                    is_optional=is_optional,
                )
            )
            continue

        # Plain scalar.
        strategy = _resolve_scalar_strategy(metadata, cls)
        fields.append(
            ScalarField(
                name=name,
                annotation=ann,
                strategy=strategy,
                is_optional=is_optional,
            )
        )
    return fields


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_optional(ann: Any) -> tuple[bool, Any]:
    """If ``ann`` is ``T | None`` (any form), return ``(True, T)``. Else
    ``(False, ann)``. Multi-arm unions other than ``T | None`` are
    returned unchanged."""
    origin = get_origin(ann)
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(ann) if a is not type(None)]
        none_present = type(None) in get_args(ann)
        if none_present and len(args) == 1:
            return True, args[0]
    return False, ann


def _preresolved_inner(ann: Any) -> type | None:
    """If ``ann`` is ``PreResolvedRef[X]``, return ``X``. Otherwise
    ``None``.

    PEP 695 type aliases preserve the alias as ``get_origin``. We also
    accept the resolved form (a raw ``Annotated[X, _PreResolvedMarker]``)
    in case someone constructs it directly.
    """
    origin = get_origin(ann)
    if origin is PreResolvedRef:
        args = get_args(ann)
        return args[0] if args else None

    # Resolved Annotated form: Annotated[X, _PreResolvedMarker]
    # In Pydantic these are unwrapped to metadata, but if someone
    # bypasses that we handle it for robustness.
    metadata = getattr(ann, "__metadata__", None)
    if metadata and any(
        m is _PreResolvedMarker or isinstance(m, _PreResolvedMarker)
        for m in metadata
    ):
        return get_args(ann)[0]
    return None


def _strategies_in_metadata(
    metadata: list[Any],
) -> tuple[list[ScalarStrategy], list[CollectionStrategy]]:
    scalars = [m for m in metadata if isinstance(m, ScalarStrategy)]
    collections = [m for m in metadata if isinstance(m, CollectionStrategy)]
    return scalars, collections


def _resolve_scalar_strategy(
    metadata: list[Any], cls: type[Node]
) -> ScalarStrategy:
    scalars, collections = _strategies_in_metadata(metadata)
    if collections:
        raise TypeError(
            f"Collection strategy applied to scalar field on {cls.__name__}: "
            f"{collections!r}"
        )
    if len(scalars) > 1:
        raise TypeError(
            f"Multiple scalar strategies on field of {cls.__name__}: {scalars!r}"
        )
    if scalars:
        return scalars[0]
    return cls._mergers_default_field


def _resolve_collection_strategy(
    metadata: list[Any], cls: type[Node]
) -> CollectionStrategy:
    scalars, collections = _strategies_in_metadata(metadata)
    if scalars:
        raise TypeError(
            f"Scalar strategy applied to collection field on {cls.__name__}: "
            f"{scalars!r}"
        )
    if len(collections) > 1:
        raise TypeError(
            f"Multiple collection strategies on field of {cls.__name__}: "
            f"{collections!r}"
        )
    if collections:
        return collections[0]
    return cls._mergers_default_collection
