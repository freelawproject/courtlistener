from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast


@dataclass
class MergeResult[T = int]:
    """Stores data about the result of an attempted merge operation.

    :ivar creates: Objects which needed to be created. Key is object name and
        value is a list of PKs to created objects.
    :ivar updates: Objects which needed to be updated.
    :ivar failures: Objects for which the merge operation failed. Items will be
        None if an object needed to be created but that operation failed."""

    creates: dict[str, set[T]] = field(default_factory=dict)
    updates: dict[str, set[T]] = field(default_factory=dict)
    failures: dict[str, list[T | None]] = field(default_factory=dict)

    @staticmethod
    def union[S, U](
        a: MergeResult[S], b: MergeResult[U]
    ) -> MergeResult[S | U]:
        """
        Creates a new MergeResult object storing the combined results of two
        objects.
        """
        return MergeResult[S | U](
            creates={
                k: a.creates.get(k, set()) | b.creates.get(k, set())
                for k in a.creates.keys() | b.creates.keys()
            },
            updates={
                k: a.updates.get(k, set()) | b.updates.get(k, set())
                for k in a.updates.keys() | b.updates.keys()
            },
            failures={
                k: [*a.failures.get(k, []), *b.failures.get(k, [])]
                for k in a.failures.keys() | b.failures.keys()
            },
        )

    def __or__[U](self, other: MergeResult[U]) -> MergeResult[T | U]:
        return MergeResult.union(
            cast(MergeResult[T | U], self), cast(MergeResult[T | U], other)
        )

    @property
    def success(self) -> bool:
        return not self.failures

    @property
    def update(self) -> bool:
        return bool(self.updates)

    @property
    def create(self) -> bool:
        return bool(self.creates)

    @staticmethod
    def created[S](model: str, pk: S) -> MergeResult[S]:
        """Shorthand for the result of a successful create operation.

        :param model: The model which was created.
        :param pk: The primary key of created object.
        :returns: The constructed MergeResult object."""
        return MergeResult(creates={model: {pk}})

    @staticmethod
    def updated[S](model: str, pk: S) -> MergeResult[S]:
        """Shorthand for the result of a successful update operation.

        :param model: The model which was updated.
        :param pk: The primary key of the updated object.
        :return: The constructed MergeResult object."""
        return MergeResult(updates={model: {pk}})

    @staticmethod
    def failed[S](model: str, pk: S | None = None) -> MergeResult[S]:
        """Shorthand for the result of a failed merge operation.

        :param model: The model which failed.
        :param pk: The (optional) primary key of the failed object.
        :return: The constructed MergeResult object."""
        return MergeResult(failures={model: [pk]})

    @staticmethod
    def unnecessary() -> MergeResult:
        """Shorthand for the result of an unnecessary merge operation.

        :return: The constructed MergeResult object."""
        return MergeResult()
