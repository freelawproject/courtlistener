from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import (
    ClassVar,
    Literal,
    TypeIs,
    cast,
)

from django.db.models import Model, QuerySet

from cl.corpus_importer.state.utils import MergeResult


class State[Enter: State | None, Exit: State]:
    def failed[Scrape, Params, M: Model](
        self, reason: str, result: MergeResult
    ) -> Failed[Scrape, Params, M]:
        """Shorthand to transition to a failure state"""
        return Failed(cast(NonTerminal, self), reason, result)

    def complete[Scrape, Params, M: Model](
        self, output: M, result: MergeResult
    ) -> Complete[Scrape, Params, M]:
        """Shorthand to transition to a success state"""
        return Complete(cast(NonTerminal, self), output, result)


@dataclass(slots=True, frozen=True)
class DerivedData[Scrape, Params]:
    scrape: Scrape
    """Scraped input"""
    params: Params
    """User-supplied parameters for this merge"""
    relation_params: Mapping[str, Model]
    """Extra model parameters for foreign object relationships"""

    def create[M: Model](
        self,
    ) -> Create[Scrape, Params, M]:
        """Shorthand to transition to a create state"""
        return Create(self.scrape, self.params, self.relation_params)

    def update[M: Model](
        self,
        instance: M,
    ) -> Update[Scrape, Params, M]:
        """Shorthand to transition to a update state"""
        return Update(
            self.scrape,
            self.params,
            self.relation_params,
            instance,
        )

    def resolve[M: Model](
        self, candidates: QuerySet[M] | Sequence[M]
    ) -> Resolve[Scrape, Params, M]:
        """Shorthand to transition to a resolve state"""
        return Resolve(
            self.scrape,
            self.params,
            self.relation_params,
            candidates,
        )

    def children[M: Model](
        self, parent: M, result: MergeResult
    ) -> Children[Scrape, Params, M]:
        """Shorthand to transition to a child state"""
        return Children(
            self.scrape,
            self.params,
            self.relation_params,
            parent,
            result,
        )


type LookupInput[Scrape, Params, M: Model] = None
type LookupOutput[Scrape, Params, M: Model] = (
    "Resolve[Scrape, Params, M] | Create[Scrape, Params, M] | Update[Scrape, Params, M] | Failed[Scrape, Params, M]"
)


@dataclass(slots=True, frozen=True)
class Lookup[Scrape, Params, M: Model](
    State[
        LookupInput[Scrape, Params, M],
        LookupOutput[Scrape, Params, M],
    ],
    DerivedData[Scrape, Params],
): ...


type ResolveInput[Scrape, Params, M: Model] = Lookup[Scrape, Params, M]
type ResolveOutput[Scrape, Params, M: Model] = (
    "Create[Scrape, Params, M] | Update[Scrape, Params, M] | Failed[Scrape, Params, M]"
)


@dataclass(slots=True, frozen=True)
class Resolve[Scrape, Params, M: Model](
    State[
        ResolveInput[Scrape, Params, M],
        ResolveOutput[Scrape, Params, M],
    ],
    DerivedData[Scrape, Params],
):
    candidates: QuerySet[M] | Sequence[M]
    """Objects to choose between"""


type CreateInput[Scrape, Params, M: Model] = (
    Resolve[Scrape, Params, M] | Lookup[Scrape, Params, M]
)
type CreateOutput[Scrape, Params, M: Model] = (
    "Children[Scrape, Params, M] | Complete[Scrape, Params, M] | Failed[Scrape, Params, M]"
)


@dataclass(slots=True, frozen=True)
class Create[Scrape, Params, M: Model](
    State[
        CreateInput[Scrape, Params, M],
        CreateOutput[Scrape, Params, M],
    ],
    DerivedData[Scrape, Params],
): ...


type UpdateInput[Scrape, Params, M: Model] = (
    Resolve[Scrape, Params, M] | Lookup[Scrape, Params, M]
)
type UpdateOutput[Scrape, Params, M: Model] = (
    "Children[Scrape, Params, M] | Complete[Scrape, Params, M] | Failed[Scrape, Params, M]"
)


@dataclass(slots=True, frozen=True)
class Update[Scrape, Params, M: Model](
    State[
        UpdateInput[Scrape, Params, M],
        UpdateOutput[Scrape, Params, M],
    ],
    DerivedData[Scrape, Params],
):
    instance: M
    """The object to update"""


type ChildrenInput[Scrape, Params, M: Model] = (
    Create[Scrape, Params, M] | Update[Scrape, Params, M]
)
type ChildrenOutput[Scrape, Params, M: Model] = (
    "Complete[Scrape, Params, M] | Failed[Scrape, Params, M]"
)


@dataclass(slots=True, frozen=True)
class Children[Scrape, Params, M: Model](
    State[
        ChildrenInput[Scrape, Params, M],
        ChildrenOutput[Scrape, Params, M],
    ],
    DerivedData[Scrape, Params],
):
    parent: M
    """The object to attach child objects to"""
    result: MergeResult
    """The result of the entire merge operation to this point"""


type NonTerminal[Scrape, Params, M: Model] = (
    Lookup[Scrape, Params, M]
    | Resolve[Scrape, Params, M]
    | Create[Scrape, Params, M]
    | Update[Scrape, Params, M]
    | Children[Scrape, Params, M]
)


def is_non_terminal(v: object) -> TypeIs[NonTerminal]:
    return isinstance(v, Lookup | Resolve | Create | Update | Children)


type CompleteInput[Scrape, Params, M: Model] = NonTerminal[Scrape, Params, M]
type CompleteOutput[Scrape, Params, M: Model] = "Complete[Scrape, Params, M]"


@dataclass(slots=True, frozen=True)
class Complete[Scrape, Params, M: Model](
    State[
        CompleteInput[Scrape, Params, M],
        CompleteOutput[Scrape, Params, M],
    ]
):
    state: NonTerminal[Scrape, Params, M]
    """The state of the merge before failure"""
    output: M
    """The object created or updated during this merge"""
    result: MergeResult
    """The result of the entire merge operation"""


type FailedInput[Scrape, Params, M: Model] = "AnyState[Scrape, Params, M]"
type FailedOutput[Scrape, Params, M: Model] = "Failed[Scrape, Params, M]"


@dataclass(slots=True, frozen=True)
class Failed[Scrape, Params, M: Model](
    State[
        FailedInput[Scrape, Params, M],
        FailedOutput[Scrape, Params, M],
    ]
):
    state: NonTerminal[Scrape, Params, M] | None
    """The state of the merge before failure"""
    reason: str
    """Human-readable message providing the reason of failure"""
    result: MergeResult
    """The result of the entire merge operation"""


type Terminal[Scrape, Params, M: Model] = (
    Complete[Scrape, Params, M] | Failed[Scrape, Params, M]
)


def is_terminal(v: object) -> TypeIs[Terminal]:
    return isinstance(v, Complete | Failed)


type AnyState[Scrape, Params, M: Model] = (
    NonTerminal[Scrape, Params, M] | Terminal[Scrape, Params, M]
)

type StateName = Literal[
    "lookup", "resolve", "create", "update", "children", "failed", "complete"
]


@dataclass(slots=True)
class Machine[Scrape, Params, M: Model](ABC):
    """Base class for state-based merge operations. Methods can be overridden to customize
    handling of specific states."""

    runners: ClassVar[Mapping[type[AnyState], str]] = {
        Lookup: "lookup",
        Resolve: "resolve",
        Create: "create",
        Update: "update",
        Children: "children",
        Failed: "failed",
        Complete: "complete",
    }
    """Utility mapping from states to the name of their runner methods."""

    state: AnyState[Scrape, Params, M]
    """The current state of the merge operation"""

    def step(self) -> AnyState[Scrape, Params, M]:
        """Take one step in the merge if it's in a non-terminal state. Otherwise, do nothing.

        Returns:
            The next state"""
        if is_terminal(self.state):
            return self.state

        state = getattr(self, self.runners[self.state.__class__])(self.state)

        self.state = state
        return self.state

    @abstractmethod
    def lookup(
        self, state: Lookup[Scrape, Params, M]
    ) -> LookupOutput[Scrape, Params, M]:
        """Attempt to find existing objects for update."""
        raise NotImplementedError

    @abstractmethod
    def resolve(
        self, state: Resolve[Scrape, Params, M]
    ) -> ResolveOutput[Scrape, Params, M]:
        """Resolve the output of a lookup into a single object."""
        raise NotImplementedError

    @abstractmethod
    def create(
        self, state: Create[Scrape, Params, M]
    ) -> CreateOutput[Scrape, Params, M]:
        raise NotImplementedError

    @abstractmethod
    def update(
        self, state: Update[Scrape, Params, M]
    ) -> UpdateOutput[Scrape, Params, M]:
        """Merge attributes and 1-1 relations in-place."""
        raise NotImplementedError

    @abstractmethod
    def children(
        self, state: Children[Scrape, Params, M]
    ) -> ChildrenOutput[Scrape, Params, M]:
        """Merge child objects into a given parent."""
        raise NotImplementedError

    @abstractmethod
    def complete(
        self, state: Complete[Scrape, Params, M]
    ) -> CompleteOutput[Scrape, Params, M]:
        """Cleanup and logging after a successful merge."""
        raise NotImplementedError

    @abstractmethod
    def failed(
        self, state: Failed[Scrape, Params, M]
    ) -> FailedOutput[Scrape, Params, M]:
        """Cleanup and logging after a failed merge."""
        raise NotImplementedError

    def run(self) -> Complete[Scrape, Params, M] | Failed[Scrape, Params, M]:
        """Run this merge until it reaches a terminal state.

        Returns:
            The final state of this merge"""
        while not is_terminal(self.state):
            self.step()

        return self.state
