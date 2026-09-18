from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, cast


@dataclass(frozen=True, slots=True)
class FileTally:
    """What a merge did with the files a scrape had waiting for it.

    Instances are immutable and combine with `|`, which is what lets one sit on
    every `MergeResult` without any of them owning mutable state. `NO_FILES` is
    the shared empty one, so a merge that touched no file allocates nothing.

    :ivar moved: Files now in the public bucket because this merge put them
        there.
    :ivar missing: Files that were not there to move -- a path in neither
        bucket's layout, or a key the private bucket does not hold. Re-running
        the load will not conjure these; the scrape has to be run again.
    :ivar failed: Files the storage backend refused to copy for some other
        reason. These are worth re-running the load over.
    """

    moved: int = 0
    missing: int = 0
    failed: int = 0

    def __bool__(self) -> bool:
        """Whether this counted anything at all."""
        return bool(self.moved or self.missing or self.failed)

    def __or__(self, other: FileTally) -> FileTally:
        """Add two tallies together.

        An empty tally is returned as the other side rather than summed, since
        almost every merge in a tree touches no file and there is no reason for
        each of them to allocate.
        """
        if not other:
            return self
        if not self:
            return other
        return FileTally(
            moved=self.moved + other.moved,
            missing=self.missing + other.missing,
            failed=self.failed + other.failed,
        )

    @property
    def unpublished(self) -> int:
        """Files that had a move to make and did not make it."""
        return self.missing + self.failed

    def __str__(self) -> str:
        return (
            f"{self.moved} moved, {self.missing} not found, "
            f"{self.failed} could not be moved"
        )


NO_FILES: Final = FileTally()


@dataclass
class MergeResult[T = int]:
    """Stores data about the result of an attempted merge operation.

    :ivar creates: Objects which needed to be created. Key is object name and
        value is a list of PKs to created objects.
    :ivar updates: Objects which needed to be updated.
    :ivar failures: Objects for which the merge operation failed. Items will be
        None if an object needed to be created but that operation failed.
    :ivar files: What became of the files this merge had to publish. See
        `FileTally`."""

    creates: dict[str, set[T]] = field(default_factory=dict)
    updates: dict[str, set[T]] = field(default_factory=dict)
    failures: dict[str, list[T | None]] = field(default_factory=dict)
    files: FileTally = NO_FILES

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
            files=a.files | b.files,
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
