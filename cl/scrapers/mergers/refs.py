"""PathRef and the ``parent`` sentinel.

A ``PathRef`` records an attribute path symbolically so that natural keys
can reference parent/ancestor fields at class-definition time, before any
tree instance exists. The framework resolves the path against concrete
instances in phase 2.

Example::

    class TexasDocketEntry(InternalNode[DocketEntry]):
        natural_key = (parent.docket, "date_filed", "entry_type")

Here ``parent.docket`` evaluates to ``PathRef("parent", "docket")``. At
phase 2 the framework calls ``resolve_path(self, parent.docket)`` which
returns ``self.parent.docket`` on a concrete instance.

Chained access stacks: ``parent.parent.field`` ->
``PathRef("parent", "parent", "field")``.

To avoid name conflicts between PathRef's chaining behavior and any of its
own attribute names, internal storage lives in ``__dict__`` directly and
introspection is exposed via the module-level ``path_parts(p)`` and
``resolve_path(obj, p)`` functions.
"""

from typing import Any


class PathRef:
    """An attribute path the framework will resolve at runtime.

    Attribute access on a PathRef returns a new PathRef with the accessed
    name appended. Underscore-prefixed names raise ``AttributeError`` so
    internal/dunder names don't silently become path parts.
    """

    def __init__(self, *parts: str) -> None:
        # Store in __dict__ directly to avoid going through __setattr__/etc
        # which might interact with __getattr__ in surprising ways.
        self.__dict__["_parts"] = parts

    def __getattr__(self, name: str) -> "PathRef":
        # __getattr__ is only called when normal attribute lookup fails,
        # so ``_parts`` (stored in __dict__) is reached without entering
        # this method.
        if name.startswith("_"):
            raise AttributeError(name)
        return PathRef(*self.__dict__["_parts"], name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PathRef):
            return NotImplemented
        return self.__dict__["_parts"] == other.__dict__["_parts"]

    def __hash__(self) -> int:
        return hash(self.__dict__["_parts"])

    def __repr__(self) -> str:
        return ".".join(self.__dict__["_parts"])


def path_parts(p: PathRef) -> tuple[str, ...]:
    """Return the tuple of attribute names that make up ``p``'s path."""
    return p.__dict__["_parts"]


def resolve_path(obj: Any, p: PathRef) -> Any:
    """Walk ``getattr(obj, name)`` for each name in ``path_parts(p)``."""
    for part in path_parts(p):
        obj = getattr(obj, part)
    return obj


# The public sentinel. Natural-key declarations chain off this.
parent: PathRef = PathRef("parent")
