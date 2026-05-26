"""MergeOutcome - record of what a merge did.

Returned from phase 4 (Apply). Single-merge outcomes have ``root``
populated; batch accumulations via ``|`` keep the left operand's root.

The ``|`` operator lets a batch caller accumulate stats across many
merges:

- ``creates`` / ``updates`` / ``deletes`` are per-model set unions
  (commutative).
- ``follow_ups`` is list concatenation (order-preserving,
  non-commutative).
- ``root`` prefers the left operand; falls through to right if left is
  ``None``.

See cl/scrapers/MERGERS_IN_THEORY.md (MergeOutcome section).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MergeOutcome[ModelT]:
    """What a merge wrote (or would write) and what to do next.

    :ivar root: The resolved Django root instance for a single merge, or
        ``None`` after batch accumulation.
    :ivar creates: Per-model set of newly inserted PKs.
    :ivar updates: Per-model set of updated PKs.
    :ivar deletes: Per-model set of deleted PKs.
    :ivar follow_ups: Ordered list of post-commit callables to dispatch.
    """

    root: ModelT | None = None
    creates: dict[Any, set[Any]] = field(default_factory=dict)
    updates: dict[Any, set[Any]] = field(default_factory=dict)
    deletes: dict[Any, set[Any]] = field(default_factory=dict)
    follow_ups: list[Callable[..., Any]] = field(default_factory=list)

    def __or__(self, other: "MergeOutcome[ModelT]") -> "MergeOutcome[ModelT]":
        return MergeOutcome(
            root=self.root if self.root is not None else other.root,
            creates=_union_sets(self.creates, other.creates),
            updates=_union_sets(self.updates, other.updates),
            deletes=_union_sets(self.deletes, other.deletes),
            follow_ups=[*self.follow_ups, *other.follow_ups],
        )


def _union_sets(
    a: dict[Any, set[Any]], b: dict[Any, set[Any]]
) -> dict[Any, set[Any]]:
    return {k: a.get(k, set()) | b.get(k, set()) for k in a.keys() | b.keys()}
