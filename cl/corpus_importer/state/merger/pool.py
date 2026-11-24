"""Pools: which stored rows a group of sibling mergers can match, and the readers that fetch them."""

from __future__ import annotations

import copy
import typing
from abc import ABC, abstractmethod
from collections.abc import Collection, Iterable, Mapping, Sequence
from operator import attrgetter
from typing import Any, ClassVar, Self, cast, override

from django.db.models import Manager, Model, Q, QuerySet
from django.db.models.expressions import Combinable

from .specifications import AttributeMerger, Source

if typing.TYPE_CHECKING:
    from .base import Merger

type Ordering = tuple[str, ...]
"""Fields rows are ordered by, each a field name or `pk` with an optional `-`."""

FILTER_SOURCES = Source.PARAMS | Source.ANCESTOR | Source.CONSTANT
"""What a pool filter may read: a pool is built once per sibling group, so it cannot read an individual scrape or row."""


def sort_rows[M](rows: Iterable[M], ordering: Ordering) -> list[M]:
    """Sort rows in memory as the database would order them.

    Args:
        rows: The rows to sort.
        ordering: The attributes to sort by, in priority order, each with an
            optional leading `-` for descending.

    Returns:
        The rows as a new list, with nulls after every value in both
        directions, as PostgreSQL does.
    """
    ordered = list(rows)
    # Sorting is stable, so sorting by the least significant field first
    # leaves the rows ordered by the most significant one.
    for item in reversed(ordering):
        value = attrgetter(item.removeprefix("-"))
        ordered.sort(
            key=lambda row: (value(row) is None, value(row)),
            reverse=item.startswith("-"),
        )
        # Descending order puts nulls first; moving them to the end keeps the
        # order of everything else.
        ordered.sort(key=lambda row: value(row) is None)
    return ordered


class PoolReader[M: Model](ABC):
    """Hands out the rows of a pool to the mergers of a sibling group.

    A reader is built per sibling group by `Pool.reader` and lives as long as
    the group's matching does.
    """

    @abstractmethod
    def rows(self, where: Q, ordering: Ordering) -> Sequence[M]:
        """Get the rows that may match what a match tier claims.

        Args:
            where: A filter every row matching the tier satisfies. A reader
                may return rows that do not satisfy it, so callers match the
                rows they get back.
            ordering: The order the rows are wanted in.

        Returns:
            The rows, in `ordering`.
        """

    @abstractmethod
    def prune(self, relation: QuerySet[M], keep: Collection[Any]) -> None:
        """Delete the rows of a parent's relation that were not kept.

        Args:
            relation: The parent's rows in the relation being replaced.
            keep: The primary keys of the rows to keep.
        """


class WholeReader[M: Model](PoolReader[M]):
    """Reads a pool's rows in one query, so every tier is matched in memory.

    Suits pools that are small and bounded by the group, such as what a parent
    holds in a relation.
    """

    def __init__(self, query: QuerySet[M], ordering: Ordering) -> None:
        """Start a reader over a query.

        Args:
            query: The pool's query. It is read on the first request for rows.
            ordering: The order the query's rows come in. Pass `()` when that
                is unknown, as for a prefetched relation, so that every other
                ordering is sorted in memory.
        """
        self._query: QuerySet[M] = query
        self._ordering: Ordering = ordering
        self._rows: list[M] | None = None

    def _read(self) -> list[M]:
        """The query's rows, read on the first call only."""
        if self._rows is None:
            self._rows = list(self._query)
        return self._rows

    @override
    def rows(self, where: Q, ordering: Ordering) -> Sequence[M]:
        """Get every row of the pool; `where` is ignored.

        Rows created after the first call are not included.
        """
        rows = self._read()
        if ordering == self._ordering:
            return rows
        return sort_rows(rows, ordering)

    @override
    def prune(self, relation: QuerySet[M], keep: Collection[Any]) -> None:
        """Delete the pool's rows whose primary key is not kept, reading them first if they have not been read."""
        read = {row.pk for row in self._read()}
        self._query.model._default_manager.filter(
            pk__in=read - set(keep)
        ).delete()


class KeyedReader[M: Model](PoolReader[M]):
    """Reads a pool's rows with one query per request, filtered by what the request claims.

    Suits pools whose scope is larger than a group needs, such as everything
    under a docket where a group is one party's attorneys.
    """

    def __init__(self, query: QuerySet[M]) -> None:
        """Start a reader over a query.

        Args:
            query: The pool's query, which each request narrows.
        """
        self._query: QuerySet[M] = query

    @override
    def rows(self, where: Q, ordering: Ordering) -> Sequence[M]:
        """Query the pool's rows satisfying `where`; every call is a query."""
        return list(self._query.filter(where).order_by(*ordering))

    @override
    def prune(self, relation: QuerySet[M], keep: Collection[Any]) -> None:
        """Delete the relation's rows whose primary key is not kept, without reading them first."""
        relation.exclude(pk__in=keep).delete()


class Pool(ABC):
    """Says which stored rows a group of sibling mergers can match, and nothing else.

    How the rows are read follows from the pool type and is not a merger's
    concern. A merger declares an instance of a subclass as its `pool`.

    :ivar filters: Expressions bounding the pool's rows, by query filter name.
    :ivar annotations: Expressions put on every row the pool reads, by the key
        they are read back under.
    """

    keyed: ClassVar[bool]
    """Whether the pool's reader queries the rows each match tier claims, so that a tier needs a term comparing a stored field directly to bound its query."""

    prefetchable: ClassVar[bool]
    """Whether the pool's rows are what a parent holds in the relation being merged, so that prefetching the relation loads them."""

    def __init__(self, **filters: Any) -> None:
        """Build a pool bounded by filters.

        Args:
            **filters: Query filters bounding the pool, each an expression
                reading only params, ancestors and constants.

        Raises:
            TypeError: If a filter is not such an expression.
        """
        for name, value in filters.items():
            if not isinstance(value, AttributeMerger):
                raise TypeError(
                    f"Pool filter {name!r} must be an expression, not {value!r}"
                )
            if value._sources & ~FILTER_SOURCES:
                raise TypeError(
                    f"Pool filter {name!r} may only read params, ancestors and constants"
                )
        self.filters: Mapping[str, AttributeMerger] = filters
        self.annotations: Mapping[str, Combinable] = {}

    def annotate(self, **annotations: Combinable) -> Self:
        """Add annotations to the rows the pool reads.

        Annotations are applied after the filters, so one following the same
        join as a filter is restricted by that filter.

        Args:
            **annotations: Django query expressions, by key.

        Returns:
            A new pool with the annotations added; this one is unchanged.

        Raises:
            TypeError: If an annotation is not a Django query expression.
        """
        for key, value in annotations.items():
            if not isinstance(value, Combinable):
                raise TypeError(
                    f"Annotation {key!r} must be a query expression, not {value!r}"
                )
        annotated = copy.copy(self)
        annotated.annotations = {**self.annotations, **annotations}
        return annotated

    def query[M: Model](
        self,
        merger: type[Merger[Any, Any, M]],
        base: QuerySet[M],
        ordering: Ordering,
    ) -> QuerySet[M]:
        """Build the query for the pool's rows out of a base query.

        Args:
            merger: The merger class whose fields the rows are loaded with.
            base: The query bounding the rows by the pool's filters.
            ordering: The order of the rows.

        Returns:
            The base query loading the merger's fields, with the pool's
            annotations, ordered.
        """
        return (
            merger.config.loading(base)
            .annotate(**self.annotations)
            .order_by(*ordering)
        )

    @abstractmethod
    def reader[M: Model](
        self,
        merger: type[Merger[Any, Any, M]],
        *,
        relation: QuerySet[M] | None,
        params: Any,
        ordering: Ordering,
    ) -> PoolReader[M]:
        """Build the reader of this pool's rows for a sibling group.

        Args:
            merger: The class of the group's mergers.
            relation: What the parent holds in the group's relation, if the
                group is a relation of another merger.
            params: The params the group's mergers were created with, which
                the pool's filters are evaluated against.
            ordering: The first match tier's ordering.

        Returns:
            The reader of the pool's rows.
        """


class Siblings(Pool):
    """The rows a parent holds in the relation this merger merges.

    Read whole: the relation is small, is what replacing prunes, and may
    already have been prefetched.
    """

    keyed: ClassVar[bool] = False
    prefetchable: ClassVar[bool] = True

    def __init__(self) -> None:
        """Build the pool."""
        super().__init__()

    @override
    def reader[M: Model](
        self,
        merger: type[Merger[Any, Any, M]],
        *,
        relation: QuerySet[M] | None,
        params: Any,
        ordering: Ordering,
    ) -> PoolReader[M]:
        """Read the parent's relation whole, from its prefetched rows when it has them.

        Raises:
            TypeError: If there is no relation, as for a root merger.
        """
        if relation is None:
            raise TypeError(
                "A Siblings pool needs a parent's relation to read"
            )
        if relation._result_cache is not None:
            return WholeReader(relation, ())
        return WholeReader(self.query(merger, relation, ordering), ordering)


class Relatives(Pool):
    """The model's rows bounded by filters on an ancestor or params.

    Read keyed: the scope has no bound tied to a single group, so reading it
    whole would load every row once per group.
    """

    keyed: ClassVar[bool] = True
    prefetchable: ClassVar[bool] = False

    def __init__(self, **filters: Any) -> None:
        """Build the pool.

        Args:
            **filters: Query filters bounding the pool, each an expression
                reading only params, ancestors and constants.
        """
        super().__init__(**filters)

    @override
    def reader[M: Model](
        self,
        merger: type[Merger[Any, Any, M]],
        *,
        relation: QuerySet[M] | None,
        params: Any,
        ordering: Ordering,
    ) -> PoolReader[M]:
        """Read the model's rows that satisfy the filters, one query per request."""
        manager = cast(Manager[M], merger.config.model._default_manager)
        base = manager.filter(
            **{
                name: value.transform(None, params, None)
                for name, value in self.filters.items()
            }
        )
        return KeyedReader(self.query(merger, base, ordering))


class Global(Relatives):
    """Every row of the model's default manager."""

    def __init__(self) -> None:
        """Build the pool."""
        super().__init__()
