"""Natural-key element classification.

``classify_nk(cls)`` walks ``cls.natural_key`` (a tuple of strings and
PathRefs) and produces a list of typed descriptors so phase 2 can
compute resolution order and build prefetch queries.

Variants:
- ``OwnScalar(field_name)`` — a primitive scalar field on the class.
- ``SiblingRef(field_name, child_class, preresolved_model)`` — a sibling
  ExternalNodeRef or PreResolvedRef field. Resolution depends on this sibling
  being resolved first.
- ``ParentPath(path)`` — a ``PathRef`` into the parent chain.

See cl/scrapers/MERGERS_IN_THEORY.md.
"""

from dataclasses import dataclass

from cl.scrapers.mergers.fields import (
    ChildField,
    ChildListField,
    ScalarField,
    extract_fields,
)
from cl.scrapers.mergers.nodes import (
    InternalNode,
    ExternalNodeRef,
    Node,
)
from cl.scrapers.mergers.refs import PathRef


# ---------------------------------------------------------------------------
# Element descriptors
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OwnScalar:
    """A primitive scalar field on this class."""

    field_name: str


@dataclass(frozen=True)
class SiblingRef:
    """A sibling ExternalNodeRef or PreResolvedRef field whose resolved PK
    contributes to this node's NK.

    Exactly one of ``child_class`` / ``preresolved_model`` is non-None.
    """

    field_name: str
    child_class: type[Node] | None
    preresolved_model: type | None


@dataclass(frozen=True)
class ParentPath:
    """A path into the parent chain (``parent.X.Y...``)."""

    path: PathRef


type NKElement = OwnScalar | SiblingRef | ParentPath


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_nk(cls: type[Node]) -> list[NKElement]:
    """Classify each element of ``cls.natural_key``.

    :raises ValueError: if ``natural_key`` is missing, references an
        unknown field, references a ChildListField, or references an
        InternalNode sibling that hasn't been matched yet.
    """
    nk = getattr(cls, "natural_key", None)
    if nk is None:
        raise ValueError(
            f"{cls.__name__} must declare a natural_key class attribute"
        )

    fields_by_name = {f.name: f for f in extract_fields(cls)}

    result: list[NKElement] = []
    for elem in nk:
        if isinstance(elem, PathRef):
            result.append(ParentPath(path=elem))
            continue

        if not isinstance(elem, str):
            raise ValueError(
                f"NK element on {cls.__name__} must be a str or PathRef, "
                f"got {elem!r}"
            )

        f = fields_by_name.get(elem)
        if f is None:
            raise ValueError(
                f"NK on {cls.__name__} references unknown field {elem!r}"
            )

        if isinstance(f, ScalarField):
            if f.preresolved_model is not None:
                result.append(
                    SiblingRef(
                        field_name=elem,
                        child_class=None,
                        preresolved_model=f.preresolved_model,
                    )
                )
            else:
                result.append(OwnScalar(field_name=elem))
            continue

        if isinstance(f, ChildField):
            if not issubclass(f.child_class, ExternalNodeRef):
                raise ValueError(
                    f"NK on {cls.__name__} references non-ExternalNodeRef "
                    f"InternalNode sibling {elem!r}: a node that's matched "
                    f"after this one can't appear in this NK"
                )
            result.append(
                SiblingRef(
                    field_name=elem,
                    child_class=f.child_class,
                    preresolved_model=None,
                )
            )
            continue

        if isinstance(f, ChildListField):
            raise ValueError(
                f"NK on {cls.__name__} can't reference collection field "
                f"{elem!r}"
            )

    return result
