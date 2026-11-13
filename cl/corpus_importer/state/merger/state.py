"""The states a merge moves through and the machine that drives it."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import (
    Any,
    ClassVar,
    LiteralString,
    TypeIs,
    cast,
)

from django.db.models import Model, QuerySet

from cl.corpus_importer.state.utils import MergeResult


@dataclass(slots=True, frozen=True)
class ModelUpdate[M: Model]:
    """Represents a pending update to a row."""

    instance: M
    """The model instance to save. Changes should already have been made and be awaiting save."""
    fields: Sequence[str]
    """The changed fields to save. Nothing outside of this set will be updated."""
    force: bool
    """Whether to force recording this update even if no fields are changed. A forced updated will not be saved to the DB, it will only be recorded."""


@dataclass(slots=True, frozen=True)
class ModelCreate[M: Model]:
    """Represents pending creation of a new row."""

    fields: Mapping[str, Any]
    """Mapping of names to values for fields in the new model."""


type ModelOperation[M: Model] = ModelCreate[M] | ModelUpdate[M]


@dataclass(slots=True, frozen=True)
class State:
    """A stage of a merge."""

    name: ClassVar[LiteralString]

    def failed[Scrape, Params, M: Model](
        self, reason: str, result: MergeResult
    ) -> Failed[Scrape, Params, M]:
        """Shorthand to transition to a failure state."""
        return Failed(cast(NonTerminal, self), reason, result)


@dataclass(slots=True, frozen=True)
class DerivedData[Scrape, Params]:
    """The merge's inputs, carried by every state that has yet to finish."""

    scrape: Scrape
    """Scraped input"""
    params: Params
    """User-supplied parameters for this merge"""
    relation_params: Mapping[str, Model]
    """Extra model parameters for foreign object relationships"""


@dataclass(slots=True, frozen=True)
class _QueryState[Scrape, Params, M: Model](
    State, DerivedData[Scrape, Params]
):
    def create(
        self,
    ) -> Create[Scrape, Params, M]:
        """Shorthand to transition to a create state."""
        return Create(self.scrape, self.params, self.relation_params)

    def update(
        self,
        instance: M,
    ) -> Update[Scrape, Params, M]:
        """Shorthand to transition to an update state."""
        return Update(
            self.scrape,
            self.params,
            self.relation_params,
            instance,
        )


@dataclass(slots=True, frozen=True)
class _Penultimate[Scrape, Params, M: Model](
    State, DerivedData[Scrape, Params]
):
    def complete(
        self, output: M, result: MergeResult
    ) -> Complete[Scrape, Params, M]:
        """Shorthand to transition to a success state."""
        return Complete(cast(NonTerminal, self), output, result)


type LookupOutput[Scrape, Params, M: Model] = (
    "Resolve[Scrape, Params, M] | Create[Scrape, Params, M] | Update[Scrape, Params, M] | Failed[Scrape, Params, M]"
)


@dataclass(slots=True, frozen=True)
class Lookup[Scrape, Params, M: Model](_QueryState[Scrape, Params, M]):
    """Looking for an existing object to merge into."""

    name = "lookup"

    def resolve(
        self, candidates: QuerySet[M] | Sequence[M]
    ) -> Resolve[Scrape, Params, M]:
        """Shorthand to transition to a resolve state."""
        return Resolve(
            self.scrape,
            self.params,
            self.relation_params,
            candidates,
        )


type ResolveOutput[Scrape, Params, M: Model] = (
    "Create[Scrape, Params, M] | Update[Scrape, Params, M] | Failed[Scrape, Params, M]"
)


@dataclass(slots=True, frozen=True)
class Resolve[Scrape, Params, M: Model](_QueryState[Scrape, Params, M]):
    """Choosing which of the lookup's candidates to merge into."""

    name = "resolve"

    candidates: QuerySet[M] | Sequence[M]
    """Objects to choose between"""


type CreateOutput[Scrape, Params, M: Model] = (
    "Save[Scrape, Params, M, ModelCreate[M]] | Failed[Scrape, Params, M]"
)


@dataclass(slots=True, frozen=True)
class Create[Scrape, Params, M: Model](_Penultimate[Scrape, Params, M]):
    """Creating a new object, since none exists to merge into."""

    name = "create"

    def save(
        self, fields: Mapping[str, Any], result: MergeResult
    ) -> Save[Scrape, Params, M, ModelCreate[M]]:
        """Shorthand to transition to a save state."""
        return Save(
            self.scrape,
            self.params,
            self.relation_params,
            ModelCreate(fields),
            result,
        )


type UpdateOutput[Scrape, Params, M: Model] = (
    "Save[Scrape, Params, M, ModelUpdate[M]] | Failed[Scrape, Params, M]"
)


@dataclass(slots=True, frozen=True)
class Update[Scrape, Params, M: Model](_Penultimate[Scrape, Params, M]):
    """Merging into an existing object."""

    name = "update"

    instance: M
    """The object to update"""

    def save(
        self,
        instance: M,
        fields: Sequence[str],
        result: MergeResult,
        force: bool = False,
    ) -> Save[Scrape, Params, M, ModelUpdate[M]]:
        """Shorthand to transition to a save state."""
        return Save(
            self.scrape,
            self.params,
            self.relation_params,
            ModelUpdate(instance, fields, force),
            result,
        )


type SaveOutput[Scrape, Params, M: Model] = (
    "Children[Scrape, Params, M] | Complete[Scrape, Params, M]"
)


@dataclass(slots=True, frozen=True)
class Save[Scrape, Params, M: Model, Operation = ModelOperation](
    _Penultimate[Scrape, Params, M]
):
    """Save the result of an operation to the database before continuing."""

    name = "save"

    operation: Operation
    """The operation to complete"""
    result: MergeResult

    def children(
        self, parent: M, result: MergeResult
    ) -> Children[Scrape, Params, M]:
        """Shorthand to transition to a child state."""
        return Children(
            self.scrape,
            self.params,
            self.relation_params,
            parent,
            result,
        )


type ChildrenOutput[Scrape, Params, M: Model] = (
    "Complete[Scrape, Params, M] | Failed[Scrape, Params, M]"
)


@dataclass(slots=True, frozen=True)
class Children[Scrape, Params, M: Model](_Penultimate[Scrape, Params, M]):
    """Merging the related objects of a created or updated object."""

    name = "children"

    parent: M
    """The object to attach child objects to"""
    result: MergeResult
    """The result of the entire merge operation to this point"""


type NonTerminal[Scrape, Params, M: Model] = (
    Lookup[Scrape, Params, M]
    | Resolve[Scrape, Params, M]
    | Create[Scrape, Params, M]
    | Save[Scrape, Params, M]
    | Update[Scrape, Params, M]
    | Children[Scrape, Params, M]
)


type CompleteOutput[Scrape, Params, M: Model] = "Complete[Scrape, Params, M]"


@dataclass(slots=True, frozen=True)
class Complete[Scrape, Params, M: Model](State):
    """The merge finished successfully."""

    name = "complete"

    state: NonTerminal[Scrape, Params, M]
    """The state of the merge before failure"""
    output: M
    """The object created or updated during this merge"""
    result: MergeResult
    """The result of the entire merge operation"""


type FailedOutput[Scrape, Params, M: Model] = "Failed[Scrape, Params, M]"


@dataclass(slots=True, frozen=True)
class Failed[Scrape, Params, M: Model](State):
    """The merge could not finish."""

    name = "failed"

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
    """Whether a value is a state the merge ends in."""
    return isinstance(v, Complete | Failed)


type AnyState[Scrape, Params, M: Model] = (
    NonTerminal[Scrape, Params, M] | Terminal[Scrape, Params, M]
)


@dataclass(slots=True)
class Machine[Scrape, Params, M: Model](ABC):
    """Base class for state-based merge operations.

    Methods can be overridden to customize handling of specific states.
    """

    state: AnyState[Scrape, Params, M]
    """The current state of the merge operation"""

    def step(self) -> AnyState[Scrape, Params, M]:
        """Run the current merge state and transition to the next.

        No guards are implemented to prevent repeatedly running terminal states.

        Returns:
            The next state
        """
        state = getattr(self, self.state.name)(self.state)

        self.state = state
        return self.state

    @abstractmethod
    def lookup(
        self, state: Lookup[Scrape, Params, M]
    ) -> LookupOutput[Scrape, Params, M]:
        """Attempt to find existing objects for update."""

    @abstractmethod
    def resolve(
        self, state: Resolve[Scrape, Params, M]
    ) -> ResolveOutput[Scrape, Params, M]:
        """Resolve the output of a lookup into a single object."""

    @abstractmethod
    def create(
        self, state: Create[Scrape, Params, M]
    ) -> CreateOutput[Scrape, Params, M]:
        """Create a new object with the merged attributes and 1-1 relations."""

    @abstractmethod
    def update(
        self, state: Update[Scrape, Params, M]
    ) -> UpdateOutput[Scrape, Params, M]:
        """Merge attributes and 1-1 relations in-place."""

    @abstractmethod
    def save(
        self, state: Save[Scrape, Params, M]
    ) -> SaveOutput[Scrape, Params, M]:
        """Save changes to self to the database."""

    @abstractmethod
    def children(
        self, state: Children[Scrape, Params, M]
    ) -> ChildrenOutput[Scrape, Params, M]:
        """Merge child objects into a given parent."""

    @abstractmethod
    def complete(
        self, state: Complete[Scrape, Params, M]
    ) -> CompleteOutput[Scrape, Params, M]:
        """Cleanup and logging after a successful merge."""

    @abstractmethod
    def failed(
        self, state: Failed[Scrape, Params, M]
    ) -> FailedOutput[Scrape, Params, M]:
        """Cleanup and logging after a failed merge."""

    def run(self) -> Complete[Scrape, Params, M] | Failed[Scrape, Params, M]:
        """Run this merge until it reaches a terminal state.

        Returns:
            The final state of this merge
        """
        while not is_terminal(self.state):
            self.step()

        self.step()

        return self.state
