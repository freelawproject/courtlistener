from __future__ import annotations

import operator
import typing
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import reduce
from typing import Any, override

from django.db.models import Model, Q, QuerySet
from typing_extensions import Sentinel

if typing.TYPE_CHECKING:
    from .base import Merger


@dataclass(frozen=True, slots=True)
class NaturalKey:
    """What a merger finds the object it merges into by.

    :ivar filters: The query filters matching the objects with this key.
    :ivar attnames: The model attributes holding the key's values.
    :ivar values: The key's values, as text so that scraped and stored values
        compare equal. Two keys with the same `attnames` identify the same
        object when their `values` are equal."""

    filters: Mapping[str, Any]
    attnames: tuple[str, ...]
    values: tuple[str, ...]

    def values_of(self, obj: Model) -> tuple[str, ...]:
        """The `values` of the key an object would be found by."""
        return tuple([str(getattr(obj, name)) for name in self.attnames])


Duplicate = Sentinel("Duplicate")
"""Another merger created alongside this one is looking for the same object."""


class SiblingLookup[M: Model](ABC):
    """Finds the objects a group of mergers created together merge into, so
    the group costs a fixed number of queries rather than one per merger.

    Every merger of the group has to be created before any of them is merged:
    a merger's lookup only sees the claims made before it runs.

    Whatever a lookup queries for, it loads as `Merger.loading` has it."""

    def __init__(self, merger: type[Merger[Any, Any, M]]) -> None:
        """
        Args:
            merger: The class of the mergers in the group."""
        self._merger: type[Merger[Any, Any, M]] = merger
        self._owners: dict[tuple[str, ...], Merger[Any, Any, M]] = {}
        self._rows: list[M] = []
        self._indexed: int = 0
        self._found: dict[tuple[str, ...], list[M]] = {}

    def claim(self, key: NaturalKey, merger: Merger[Any, Any, M]) -> None:
        """Register a merger's interest in the object matching a natural key.
        When several mergers claim the same key, the last one owns it.

        Args:
            key: The key the merger will look its object up by.
            merger: The merger that will look the object up."""
        self._owners[key.values] = merger

    def candidates(
        self, key: NaturalKey, merger: Merger[Any, Any, M]
    ) -> Sequence[M] | Duplicate:
        """Find the objects matching a natural key.

        Args:
            key: A key the merger has claimed.
            merger: The merger looking the object up.

        Returns:
            The matching objects, or `Duplicate` if a merger created later
            claimed the same key."""
        if self._owners[key.values] is not merger:
            return Duplicate
        self._fetch(key)
        return self._found.get(key.values, ())

    def _index(self, key: NaturalKey) -> None:
        """File the rows read since the last call under their natural keys.

        Args:
            key: Any key of the group, for the attributes its keys are made
                of."""
        for obj in self._rows[self._indexed :]:
            self._found.setdefault(key.values_of(obj), []).append(obj)
        self._indexed = len(self._rows)

    @abstractmethod
    def _fetch(self, key: NaturalKey) -> None:
        """Read and index whatever is needed to answer the claims made so far
        and hasn't been yet.

        Args:
            key: The key being looked up."""


class KeyLookup[M: Model](SiblingLookup[M]):
    """Looks the claimed natural keys up with a single query."""

    def __init__(self, merger: type[Merger[Any, Any, M]]) -> None:
        super().__init__(merger)
        self._unfetched: list[tuple[NaturalKey, Merger[Any, Any, M]]] = []

    @override
    def claim(self, key: NaturalKey, merger: Merger[Any, Any, M]) -> None:
        super().claim(key, merger)
        self._unfetched.append((key, merger))

    @override
    def _fetch(self, key: NaturalKey) -> None:
        if not self._unfetched:
            return
        manager = self._unfetched[0][1].manager
        matching = reduce(
            operator.or_, [Q(**key.filters) for key, _ in self._unfetched]
        )
        self._unfetched = []
        self._rows.extend(self._merger.loading(manager.filter(matching)))
        self._index(key)


class RelationLookup[M: Model](SiblingLookup[M]):
    """Matches natural keys against all of the objects that could be merged
    into, such as everything a parent holds in a relation."""

    def __init__(
        self, merger: type[Merger[Any, Any, M]], related: QuerySet[M]
    ) -> None:
        """
        Args:
            merger: The class of the mergers in the group.
            related: The objects to match against. Nothing is queried for
                when they have already been loaded."""
        super().__init__(merger)
        self._related: QuerySet[M] | None = related

    def existing(self) -> Sequence[M]:
        """The objects matched against, as they were when first read.
        Objects created since then are not included."""
        self._read()
        return self._rows

    def _read(self) -> None:
        """Load the objects to match against, once."""
        if (related := self._related) is None:
            return
        self._related = None
        if related._result_cache is None:
            related = self._merger.loading(related)
        self._rows.extend(related)

    @override
    def _fetch(self, key: NaturalKey) -> None:
        self._read()
        self._index(key)
