"""FollowUp — post-commit work returned from lifecycle hooks.

A lifecycle hook (`on_create` / `on_update` / `on_delete`) may return a
list of FollowUp instances. The framework collects them into the
``MergeOutcome.follow_ups`` field; the caller is responsible for
dispatching each one with ``transaction.on_commit`` (or however it sees
fit). All follow-ups are post-commit by design — anything that needs to
write inside the merge's transaction belongs in the tree as a node.

See cl/scrapers/MERGERS_IN_THEORY.md (Follow-ups section) for the design.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FollowUp:
    """A callable record of post-commit work.

    :ivar name: Short human-readable label for logging / tracing.
    :ivar fn: The callable to invoke after commit.
    :ivar args: Positional arguments to pass to ``fn``.
    :ivar kwargs: Keyword arguments to pass to ``fn``.
    :ivar tags: Optional labels callers can route on.
    """

    name: str
    fn: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    tags: frozenset[str] = field(default_factory=frozenset)

    def __call__(self) -> Any:
        return self.fn(*self.args, **self.kwargs)
