"""Declarations of how a merger picks the stored row it merges into, and the checks that bind them to a merger."""

from __future__ import annotations

import logging
import operator
import typing
from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from functools import reduce
from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db.models import Field, Model, Q, QuerySet
from typing_extensions import Sentinel

from cl.corpus_importer.state.utils import MergeResult

from . import state as MergerState
from .parameters import Create, Update
from .pool import Ordering, Pool, PoolReader, Relatives
from .specifications import (
    AttributeMerger,
    Comparison,
    Source,
    _DatabaseProxy,
)

if typing.TYPE_CHECKING:
    from .base import Merger

logger = logging.getLogger(__name__)

Next = Sentinel("Next")
"""Fall through to the next tier. After the last tier, a merger that matched nothing creates and one that is a duplicate is judged by its candidates."""

STORED_SOURCES = Source.DATABASE | Source.ANNOTATION
"""What marks an expression as reading the stored row."""

ALLOWED_STORED_SOURCES = STORED_SOURCES | Source.CONSTANT
"""What the stored side of a term may read, so that a row has one value for every member of a group."""


@dataclass(frozen=True, slots=True)
class Fail:
    """Fail the merger, or as a `duplicate` outcome every merger sharing the key.

    :ivar message: The reason given for the failure, used verbatim. Without
        one, the failure is described by the outcome it stands in for.
    """

    message: str | None = None

    def reason(self, default: str) -> str:
        """Say why the merger failed.

        Args:
            default: The reason to give when the failure has no message.

        Returns:
            The failure's message, or `default` if it has none.
        """
        return default if self.message is None else self.message


type Term = str | Comparison | bool
"""A field name, as shorthand for comparing that stored field with the merger's computed value of it, or an `==` between two expressions.

Expressions are typed as the value they evaluate to, so a type checker sees `==` between them as a `bool`. A `bool` is accepted statically for that reason only: `Match.bind` rejects any term that is not a field name or a `Comparison`."""

type Outcome = Next | Create | Fail
"""What can end a tier's `missing` and `ambiguous` outcomes without a further choice."""

type MissingOutcome = Next | Create | Fail | type[Fail]
"""What a declaration accepts for a `missing` outcome: an `Outcome`, with `Fail` allowed as a bare class."""

type AmbiguousOutcome = MissingOutcome | First | Narrow
"""What a declaration accepts for an `ambiguous` outcome: a `MissingOutcome`, or a `First` or `Narrow` to choose among the candidates."""

type DuplicateOutcome = Next | Fail | type[Fail]
"""What a declaration accepts for a `duplicate` outcome: fall through or fail, with `Fail` allowed as a bare class."""


def failure_text(
    merger: type[Merger],
    text: str,
    *,
    tier: int | None = None,
    key: tuple[Any, ...] = (),
) -> str:
    """Build the reason a merger's lookup failed.

    Args:
        merger: The class of the merger that failed.
        text: What went wrong.
        tier: The tier the failure happened in, counted from 1. Without one,
            the reason names no tier or key.
        key: The values the member was told apart by when it failed. Only
            reported with a tier.

    Returns:
        The reason, as given to the failed state and the log.
    """
    reason = f"{merger.__name__}: {text}"
    if tier is None:
        return reason
    return f"{reason} (tier {tier}, key {key})"


def _settled[T](outcome: T | type[Fail]) -> T | Fail:
    """Turn `Fail` passed as a class into an instance.

    Args:
        outcome: An outcome as declared.

    Returns:
        The outcome, with a bare `Fail` replaced by `Fail()`.
    """
    return Fail() if outcome is Fail else cast(T, outcome)


def ambiguous_text(model: type[Model], rows: int, items: int) -> str:
    """Say why one stored row could not be picked.

    Args:
        model: The model of the rows.
        rows: How many rows the scraped item could be.
        items: How many scraped items hold any of those rows, including the
            one being picked for.

    Returns:
        The reason a failed lookup gives when it has no message of its own.
    """
    return (
        f"cannot pick one {model.__name__}: {rows} rows for "
        f"{items} scraped items"
    )


@dataclass(frozen=True, slots=True, init=False)
class First:
    """Take the first candidate in a given order.

    :ivar ordering: The fields to order candidates by, each a concrete field
        name or `pk` with an optional leading `-` for descending. A tier's
        ordering always ends in ascending `pk`, appended when not named.
    """

    ordering: Ordering

    def __init__(self, *ordering: str) -> None:
        """Declare the order to take the first candidate in.

        Args:
            *ordering: The fields to order by. Nothing is checked until the
                declaration is bound to a merger.
        """
        object.__setattr__(self, "ordering", ordering)


@dataclass(frozen=True, slots=True, init=False, eq=False)
class Narrow:
    """Filter an ambiguous member's candidates on more terms, then apply outcomes of its own.

    A `Narrow` separates scraped items sharing a key as well as stored rows
    sharing one.

    :ivar terms: The terms the candidates are filtered on.
    :ivar missing: What happens when the filter leaves no candidates.
    :ivar ambiguous: What happens when more than one candidate remains.
    """

    terms: tuple[Term, ...]
    missing: Outcome
    ambiguous: Outcome | First | Narrow

    def __init__(
        self,
        *terms: Term,
        missing: MissingOutcome = Fail,
        ambiguous: AmbiguousOutcome = Fail,
    ) -> None:
        """Declare a narrowing.

        Args:
            *terms: The terms to filter the candidates on.
            missing: The outcome when no candidate satisfies the terms.
            ambiguous: The outcome when several still do.
        """
        object.__setattr__(self, "terms", terms)
        object.__setattr__(self, "missing", _settled(missing))
        object.__setattr__(self, "ambiguous", _settled(ambiguous))


@dataclass(frozen=True, slots=True, init=False, eq=False)
class Key:
    """A match tier: the terms that find a member's candidate rows, and what to do when it finds none, several, or shares them.

    :ivar terms: The terms the stored rows must equal the member on.
    :ivar missing: What happens when no available row matches.
    :ivar ambiguous: What happens when the match is not one member to one row.
    :ivar duplicate: What happens when another member has equal values for
        every term of the tier, `Narrow` chain included.
    """

    terms: tuple[Term, ...]
    missing: Outcome
    ambiguous: Outcome | First | Narrow
    duplicate: Next | Fail

    def __init__(
        self,
        *terms: Term,
        missing: MissingOutcome = Next,
        ambiguous: AmbiguousOutcome = Fail,
        duplicate: DuplicateOutcome = Fail,
    ) -> None:
        """Declare a tier.

        Args:
            *terms: The terms the stored rows must equal the member on.
            missing: The outcome when no available row matches.
            ambiguous: The outcome when several rows match, or when members
                that are not duplicates share a candidate.
            duplicate: The outcome for members that nothing in the tier can
                tell apart.
        """
        object.__setattr__(self, "terms", terms)
        object.__setattr__(self, "missing", _settled(missing))
        object.__setattr__(self, "ambiguous", _settled(ambiguous))
        object.__setattr__(self, "duplicate", _settled(duplicate))


@dataclass(frozen=True, eq=False)
class BoundTerm:
    """A term checked against its merger, ready to evaluate on either side.

    Compared by identity: expressions overload `==`.

    :ivar stored: The side that reads the stored row.
    :ivar field: The stored field, set when `stored` is a bare `Database`.
        The scraped value is converted by it before it is compared.
    :ivar attribute: The merger attribute holding the scraped value, set for
        the string shorthand.
    :ivar scraped: The expression for the scraped value, set for an explicit
        term.
    """

    stored: AttributeMerger
    field: Field | None = None
    attribute: str | None = None
    scraped: AttributeMerger | None = None

    def stored_value(self, row: Model) -> Any:
        """Evaluate the stored side on a row.

        Args:
            row: A stored row, loaded with the pool's annotations if the term
                reads any.

        Returns:
            The row's value for the term.
        """
        return self.stored.transform(None, None, row)

    def scraped_raw(
        self, merger: Merger, state: MergerState.Lookup[Any, Any, Any]
    ) -> Any:
        """Evaluate the scraped side for a merger, before the stored field converts it.

        Args:
            merger: The merger being matched; the shorthand reads the value it
                computed for its attribute.
            state: The merger's state, whose scrape and params an explicit
                term is evaluated against.

        Returns:
            The scraped value as the merger has it.
        """
        if self.attribute is not None:
            return getattr(merger, self.attribute)
        return cast(AttributeMerger, self.scraped).transform(
            state.scrape, state.params, None
        )

    def scraped_value(
        self, merger: Merger, state: MergerState.Lookup[Any, Any, Any]
    ) -> Any:
        """Evaluate the scraped side for a merger.

        Args:
            merger: The merger being matched; the shorthand reads the value it
                computed for its attribute.
            state: The merger's state, whose scrape and params an explicit
                term is evaluated against.

        Returns:
            The value to compare with `stored_value`, converted by the stored
            field when there is one.

        Raises:
            django.core.exceptions.ValidationError: If the stored field
                rejects the scraped value.
        """
        value = self.scraped_raw(merger, state)
        if self.field is None:
            return value
        return self.field.to_python(value)


@dataclass(frozen=True)
class BoundNarrow:
    """A `Narrow` whose terms are bound.

    :ivar terms: The bound terms the candidates are filtered on.
    :ivar missing: What happens when the filter leaves no candidates.
    :ivar ambiguous: What happens when more than one candidate remains.
    """

    terms: tuple[BoundTerm, ...]
    missing: Outcome
    ambiguous: AmbiguousBound


type AmbiguousBound = Outcome | First | BoundNarrow


@dataclass(frozen=True)
class BoundTier:
    """A `Key` checked against its merger.

    :ivar index: The tier's position in the match, counted from 1.
    :ivar terms: The tier's bound key terms.
    :ivar missing: What happens when no available row matches.
    :ivar ambiguous: What happens when the match is not one member to one row.
    :ivar duplicate: What happens to members the tier cannot tell apart.
    :ivar ordering: The order candidates are taken in, always ending in `pk`
        so the pick is deterministic.
    """

    index: int
    terms: tuple[BoundTerm, ...]
    missing: Outcome
    ambiguous: AmbiguousBound
    duplicate: Next | Fail
    ordering: Ordering

    @property
    def chain_terms(self) -> tuple[BoundTerm, ...]:
        """The terms of every `Narrow` the tier's `ambiguous` outcome chains through, in order."""
        terms: list[BoundTerm] = []
        outcome = self.ambiguous
        while isinstance(outcome, BoundNarrow):
            terms.extend(outcome.terms)
            outcome = outcome.ambiguous
        return tuple(terms)


@dataclass(frozen=True)
class BoundMatch:
    """A `Match` checked against its merger.

    :ivar tiers: The bound tiers, in priority order.
    :ivar columns: The model fields the match reads from stored rows: every
        stored side's database fields and every ordering field.
    """

    tiers: tuple[BoundTier, ...]
    columns: frozenset[str]

    def check_pool(self, pool: Pool) -> list[Exception]:
        """Check the match against the pool its rows are read from.

        A keyed pool queries each tier by the terms comparing a stored column
        directly, so a tier without one would read the pool whole. A pool read
        whole has no such need.

        Args:
            pool: The pool the merger's rows are read from.

        Returns:
            One error per tier that cannot be queried in `pool`.
        """
        if not isinstance(pool, Relatives):
            return []
        return [
            ValueError(
                f"tier {tier.index}: a keyed pool needs a term comparing a "
                "stored field directly, or it would read every row"
            )
            for tier in self.tiers
            if all(term.field is None for term in tier.terms)
        ]


class _Binder:
    """Checks declarations against one merger and pool, collecting every problem found."""

    def __init__(self, merger: type[Merger], pool: Pool | None) -> None:
        """Start binding declarations.

        Args:
            merger: The merger class the declarations are for.
            pool: The merger's declared pool, if any.
        """
        self.merger: type[Merger] = merger
        self.model: type[Model] = merger.config.model
        self.annotations: frozenset[str] = frozenset(
            pool.annotations if pool is not None else ()
        )
        self.fields: dict[str, Field] = {
            f.name: f for f in self.model._meta.concrete_fields
        }
        self.named_fields: dict[str, Field] = {
            **{f.attname: f for f in self.model._meta.concrete_fields},
            **self.fields,
        }
        self.errors: list[Exception] = []
        self.tier_index: int = 0

    def problem(self, error: Exception) -> None:
        """Record a problem, naming the tier being bound."""
        error.args = (f"tier {self.tier_index}: {error}",)
        self.errors.append(error)

    def tier(self, index: int, key: Key) -> BoundTier:
        """Bind a tier.

        Args:
            index: The tier's position in the match, counted from 1.
            key: The tier as declared.

        Returns:
            The bound tier.
        """
        self.tier_index = index
        terms = self.terms(key.terms)
        ambiguous = self.ambiguous(key.ambiguous)
        first = ambiguous
        while isinstance(first, BoundNarrow):
            first = first.ambiguous
        ordering = first.ordering if isinstance(first, First) else ()
        if not {"pk", "-pk"} & set(ordering):
            ordering = (*ordering, "pk")
        return BoundTier(
            index=index,
            terms=terms,
            missing=key.missing,
            ambiguous=ambiguous,
            duplicate=key.duplicate,
            ordering=ordering,
        )

    def ambiguous(self, outcome: Outcome | First | Narrow) -> AmbiguousBound:
        """Bind an `ambiguous` outcome, and everything it chains to.

        Args:
            outcome: The outcome as declared.

        Returns:
            The outcome, with a `Narrow` bound.
        """
        match outcome:
            case Narrow():
                return BoundNarrow(
                    terms=self.terms(outcome.terms),
                    missing=outcome.missing,
                    ambiguous=self.ambiguous(outcome.ambiguous),
                )
            case First():
                self.check_ordering(outcome)
                return outcome
            case _:
                return outcome

    def check_ordering(self, first: First) -> None:
        """Record a problem for each ordering that is not `pk` or a concrete field, with an optional `-`."""
        for item in first.ordering:
            if item.removeprefix("-") not in {"pk", *self.fields}:
                self.problem(
                    ValueError(
                        f"cannot order by {item!r}: an ordering is a concrete "
                        f"field of {self.model.__name__} or pk, optionally "
                        "prefixed with '-'"
                    )
                )

    def terms(self, terms: tuple[Term, ...]) -> tuple[BoundTerm, ...]:
        """Bind terms, recording the problems of those that are invalid."""
        bound = (self.term(term) for term in terms)
        return tuple(b for b in bound if b is not None)

    def term(self, term: object) -> BoundTerm | None:
        """Bind one term.

        Args:
            term: The term as declared.

        Returns:
            The bound term, or `None` if it has a problem, which is recorded.
        """
        match term:
            case str():
                return self.shorthand(term)
            case Comparison():
                return self.comparison(term)
            case _:
                self.problem(
                    TypeError(
                        f"{term!r} is not a term: use a field name or an "
                        "== between two expressions"
                    )
                )
                return None

    def shorthand(self, name: str) -> BoundTerm | None:
        """Bind a field name as a comparison of that stored field with the merger's computed value.

        The name is a concrete field's name or, for a foreign key, its attname;
        the merger must compute it under the name as written.

        Returns:
            The bound term, or `None` if the name is not a concrete field of the
            model that the merger computes, which is recorded.
        """
        if (field := self.named_fields.get(name)) is None:
            self.problem(
                ValueError(
                    f"{name!r} is not a concrete field of {self.model.__name__}"
                )
            )
            return None
        if name not in self.merger.config.registry.attr:
            self.problem(
                ValueError(
                    f"{self.merger.__name__} does not compute {name!r}, so "
                    "the shorthand term has no scraped value"
                )
            )
            return None
        return BoundTerm(
            stored=_DatabaseProxy(field), field=field, attribute=name
        )

    def comparison(self, term: Comparison) -> BoundTerm | None:
        """Bind an `==` between two expressions.

        Exactly one side must read the stored row, built only from `Database`,
        annotations of the pool and constants.

        Returns:
            The bound term, or `None` if it breaks those rules, which is
            recorded.
        """
        stored_sides = [
            side
            for side in (term.left, term.right)
            if side._sources & STORED_SOURCES
        ]
        if len(stored_sides) != 1:
            self.problem(
                ValueError(
                    "exactly one side of a term must read the stored row "
                    "(Database or Annotation)"
                )
            )
            return None
        stored = stored_sides[0]
        scraped = term.right if stored is term.left else term.left
        valid = True
        if disallowed := stored._sources & ~ALLOWED_STORED_SOURCES:
            self.problem(
                ValueError(
                    "the stored side of a term may only read Database, "
                    f"Annotation and Constant, not {disallowed}"
                )
            )
            valid = False
        for key in stored._annotations:
            if key not in self.annotations:
                self.problem(
                    ValueError(
                        f"annotation {key!r} is not annotated by the "
                        f"pool of {self.merger.__name__}"
                    )
                )
                valid = False
        if not valid:
            return None
        return BoundTerm(
            stored=stored,
            field=stored._field
            if isinstance(stored, _DatabaseProxy)
            else None,
            scraped=scraped,
        )


@dataclass(frozen=True, slots=True, init=False, eq=False)
class Match:
    """An ordered list of tiers that picks the stored row a merger merges into.

    :ivar tiers: The tiers, in priority order.
    """

    tiers: tuple[Key, ...]

    def __init__(self, *tiers: Key) -> None:
        """Declare a match. Nothing is checked until `bind`.

        Args:
            *tiers: The tiers, in priority order.
        """
        object.__setattr__(self, "tiers", tiers)

    def bind(self, merger: type[Merger], pool: Pool | None) -> BoundMatch:
        """Check the declaration against a merger and produce what the matcher consumes.

        Args:
            merger: The merger class the match is declared on.
            pool: The merger's declared pool. Annotations a term reads must be
                ones it adds.

        Returns:
            The bound match.

        Raises:
            ExceptionGroup: Of every problem found in the declaration.
        """
        binder = _Binder(merger, pool)
        tiers = tuple(
            binder.tier(index, key)
            for index, key in enumerate(self.tiers, start=1)
        )
        if binder.errors:
            problems = "; ".join(str(error) for error in binder.errors)
            raise ExceptionGroup(
                f"Invalid match for {merger.__name__}: {problems}",
                binder.errors,
            )
        return BoundMatch(
            tiers=tiers,
            columns=frozenset(
                name
                for tier in tiers
                for name in (
                    *(
                        f
                        for term in (*tier.terms, *tier.chain_terms)
                        for f in term.stored._db_fields
                    ),
                    *(
                        item.removeprefix("-")
                        for item in tier.ordering
                        if item.removeprefix("-") != "pk"
                    ),
                )
            ),
        )


class _Rejected(Exception):
    """A scraped value that the stored field it is compared with cannot hold; its message says which."""


@dataclass(frozen=True, slots=True)
class _Failure:
    """How a member's lookup ended in failure.

    :ivar text: The reason, as given to the failed state and the log.
    """

    text: str


type Resolution[M: Model] = Update[M] | Create | _Failure
"""How a member's lookup ended: the row it merges into, a new row, or a failure."""


@dataclass(frozen=True, slots=True)
class _TierKey:
    """What a member is told apart by in one tier.

    :ivar relations: The primary keys of the member's relation params, in
        sorted param-name order.
    :ivar values: The scraped values of the tier's key terms.
    :ivar chain: The scraped values of the terms of every `Narrow` the tier
        chains through.
    """

    relations: tuple[Any, ...]
    values: tuple[Any, ...]
    chain: tuple[Any, ...]

    @property
    def key(self) -> tuple[Any, ...]:
        """The values stored rows must equal to be the member's candidates."""
        return (*self.relations, *self.values)

    @property
    def duplicate(self) -> tuple[Any, ...]:
        """The values that members share when nothing in the tier can tell them apart."""
        return (*self.key, *self.chain)


@dataclass(eq=False)
class _Member[M: Model]:
    """A merger in a group and how its lookup is going.

    :ivar merger: The merger.
    :ivar state: The merger's state, which its scrape and params are read from.
    :ivar keys: The member's `_TierKey` for each tier. Empty until the group is
        assigned.
    :ivar resolution: How the member's lookup ended, or `None` while it is
        still looking.
    """

    merger: Merger[Any, Any, M]
    state: MergerState.Lookup[Any, Any, M]
    keys: tuple[_TierKey, ...] = ()
    resolution: Resolution[M] | None = None


@dataclass(eq=False)
class _Entry[M: Model]:
    """A member's progress through one tier.

    :ivar member: The member.
    :ivar key: The member's key in the tier.
    :ivar candidates: The available rows still matching the member, in the
        order the pool handed them out. A pool that reads one row for each
        join may list a primary key more than once.
    :ivar last: The candidates before the last filter that emptied them, or
        the current ones while there are some.
    :ivar depth: How many terms of the tier's `Narrow` chain have filtered the
        candidates.
    :ivar outcome: What the tier decided for the member so far.
    """

    member: _Member[M]
    key: _TierKey
    candidates: list[M]
    last: list[M]
    depth: int = 0
    outcome: Resolution[M] | Next | None = None

    @property
    def shown_key(self) -> tuple[Any, ...]:
        """The values the member has been told apart by so far, as a failure reports them."""
        return (*self.key.key, *self.key.chain[: self.depth])

    @property
    def pks(self) -> list[Any]:
        """The primary keys of the candidates, each once, in order."""
        return list(dict.fromkeys(row.pk for row in self.candidates))

    def narrow(self, terms: Sequence[BoundTerm]) -> None:
        """Keep the candidates equal to the member on the next terms of its `Narrow` chain.

        Args:
            terms: The terms of the `Narrow` being applied, which must be the
                ones following those already applied.
        """
        values = self.key.chain[self.depth : self.depth + len(terms)]
        self.depth += len(terms)
        self.candidates = [
            row
            for row in self.candidates
            if all(
                term.stored_value(row) == value
                for term, value in zip(terms, values, strict=True)
            )
        ]
        if self.candidates:
            self.last = self.candidates


class MatchGroup[M: Model]:
    """Assigns the stored rows of a pool to the mergers of a sibling group, tier by tier.

    Every merger of the group has to be joined before any asks for its
    verdict: the first verdict assigns every joined merger, so that a tier is
    a priority across the group and the result does not depend on the order
    the mergers were created in. Rows created while the group merges are not
    seen.
    """

    def __init__(
        self,
        merger: type[Merger[Any, Any, M]],
        match: BoundMatch,
        reader: PoolReader[M],
    ) -> None:
        """Start a group.

        Args:
            merger: The class of the group's mergers.
            match: The match the group is assigned by.
            reader: The reader of the pool the group's rows come from, built
                for the first tier's ordering.
        """
        self._merger: type[Merger[Any, Any, M]] = merger
        self._match: BoundMatch = match
        self._reader: PoolReader[M] = reader
        self._members: dict[int, _Member[M]] = {}
        self._relation_names: list[str] = []
        self._relation_attnames: list[str] = []
        self._unavailable: set[Any] = set()
        self._assigned: bool = False

    @classmethod
    def build(
        cls,
        merger: type[Merger[Any, Any, M]],
        pool: Pool,
        *,
        relation: QuerySet[M] | None,
        params: Any,
    ) -> MatchGroup[M]:
        """Start the group of a merger's siblings.

        Args:
            merger: The class of the group's mergers.
            pool: The pool the merger's rows are read from.
            relation: What the parent holds in the group's relation, if the
                group is a relation of another merger.
            params: The params the group's mergers were created with.

        Returns:
            The group, with no members.

        Raises:
            TypeError: If the merger matches by its `match` and that cannot be
                matched in the pool.
        """
        match = merger._bound_match
        if errors := merger.pool_errors(pool):
            raise TypeError(
                f"{merger.__name__} cannot be matched in {type(pool).__name__}: "
                + "; ".join(str(error) for error in errors)
            )
        reader = pool.reader(
            merger,
            relation=relation,
            params=params,
            ordering=match.tiers[0].ordering,
        )
        return cls(merger, match, reader)

    def join(
        self, merger: Merger[Any, Any, M], state: MergerState.Lookup
    ) -> None:
        """Make a merger a member of the group.

        Args:
            merger: A merger of the group's class with its values computed.
                Mergers that fail validation or are not looking for their row
                are not members.
            state: The merger's state.
        """
        self._members[id(merger)] = _Member(merger, state)

    def verdict(
        self, merger: Merger[Any, Any, M], state: MergerState.Lookup
    ) -> (
        MergerState.Create[Any, Any, M]
        | MergerState.Update[Any, Any, M]
        | MergerState.Failed[Any, Any, M]
    ):
        """Say what a member's lookup comes to.

        The first call assigns every joined member.

        Args:
            merger: A member of the group.
            state: The merger's state.

        Returns:
            The state the merger moves to: creating a row, updating the row it
            was assigned, or failed.
        """
        if not self._assigned:
            self._assign()
        resolution = self._members[id(merger)].resolution
        if isinstance(resolution, Update):
            return state.update(resolution.instance)
        if isinstance(resolution, _Failure):
            return state.failed(
                resolution.text,
                MergeResult.failed(self._merger.config.model.__name__),
            )
        return state.create()

    def prune(self, relation: QuerySet[M], keep: Collection[Any]) -> None:
        """Delete the rows of a parent's relation that were not kept.

        Args:
            relation: The parent's rows in the relation being replaced.
            keep: The primary keys of the rows to keep.
        """
        self._reader.prune(relation, keep)

    def _assign(self) -> None:
        """Assign every member, tier by tier."""
        self._assigned = True
        if not self._members:
            return
        first = next(iter(self._members.values()))
        self._relation_names = sorted(first.state.relation_params)
        model = self._merger.config.model
        self._relation_attnames = [
            cast(Field, model._meta.get_field(name)).attname
            for name in self._relation_names
        ]
        live = [m for m in self._members.values() if self._evaluate(m)]
        tiers = self._match.tiers
        for position, tier in enumerate(tiers):
            self._run_tier(tier, live, final=position == len(tiers) - 1)
        for member in live:
            if member.resolution is None:
                member.resolution = Create

    def _evaluate(self, member: _Member[M]) -> bool:
        """Compute a member's key in every tier, failing the member if a stored field rejects one of its values.

        Returns:
            Whether the member can be matched.
        """
        relations = tuple(
            member.state.relation_params[name].pk
            for name in self._relation_names
        )
        try:
            member.keys = tuple(
                _TierKey(
                    relations,
                    tuple(self._scraped(member, t) for t in tier.terms),
                    tuple(self._scraped(member, t) for t in tier.chain_terms),
                )
                for tier in self._match.tiers
            )
        except _Rejected as rejected:
            text = failure_text(self._merger, str(rejected), tier=1)
            logger.error("%s", text)
            member.resolution = _Failure(text)
            return False
        return True

    def _scraped(self, member: _Member[M], term: BoundTerm) -> Any:
        """A member's scraped value for a term.

        Raises:
            _Rejected: If the term's stored field cannot hold the value.
        """
        try:
            return term.scraped_value(member.merger, member.state)
        except ValidationError:
            raise _Rejected(
                f"{cast(Field, term.field).name} cannot hold scraped value "
                f"{term.scraped_raw(member.merger, member.state)!r}"
            ) from None

    def _run_tier(
        self, tier: BoundTier, members: list[_Member[M]], *, final: bool
    ) -> None:
        """Assign the members still looking from the rows a tier matches them with.

        Args:
            tier: The tier.
            members: Every member that can be matched, assigned or not.
            final: Whether the tier is the last one.
        """
        position = tier.index - 1
        looking = [m for m in members if m.resolution is None]
        if not looking:
            return
        rows = self._reader.rows(self._where(tier, looking), tier.ordering)
        index: dict[tuple[Any, ...], list[M]] = defaultdict(list)
        for row in rows:
            if row.pk not in self._unavailable:
                index[self._row_key(row, tier)].append(row)
        entries = []
        for member in looking:
            key = member.keys[position]
            candidates = index.get(key.key, [])
            entries.append(_Entry(member, key, candidates, candidates))
        # A member that an earlier tier assigned still shares its key.
        sharing = Counter(m.keys[position].duplicate for m in members)
        # On a last tier that lets duplicates through, they are judged by their
        # candidates like any other member.
        checks_duplicates = not (final and tier.duplicate is Next)
        duplicates: list[_Entry[M]] = []
        deciding: list[_Entry[M]] = []
        for entry in entries:
            if checks_duplicates and sharing[entry.key.duplicate] > 1:
                duplicates.append(entry)
            else:
                deciding.append(entry)
        self._settle(tier, tier, deciding, duplicates)
        sets: dict[tuple[Any, ...], list[_Entry[M]]] = defaultdict(list)
        for entry in duplicates:
            sets[entry.key.duplicate].append(entry)
        for shared, group in sets.items():
            self._duplicate(tier, group, sharing[shared])
        self._collide(tier, entries)
        self._close(entries)

    def _where(self, tier: BoundTier, members: list[_Member[M]]) -> Q:
        """The filter that finds every row a tier could match the members with.

        Returns:
            One alternative for each distinct key: the member's relation params
            and the values of its terms comparing a stored field directly,
            null as a null check.
        """
        position = tier.index - 1
        alternatives: dict[tuple[Any, ...], Q] = {}
        for member in members:
            key = member.keys[position]
            if key.key in alternatives:
                continue
            terms = [
                Q(**{f"{term.field.name}__isnull": True})
                if value is None
                else Q(**{term.field.name: value})
                for term, value in zip(tier.terms, key.values, strict=True)
                if term.field is not None
            ]
            alternatives[key.key] = Q(**member.state.relation_params) & reduce(
                operator.and_, terms, Q()
            )
        return reduce(operator.or_, alternatives.values())

    def _row_key(self, row: M, tier: BoundTier) -> tuple[Any, ...]:
        """The values of a stored row that members are matched on in a tier."""
        return (
            *(getattr(row, attname) for attname in self._relation_attnames),
            *(term.stored_value(row) for term in tier.terms),
        )

    def _settle(
        self,
        tier: BoundTier,
        stage: BoundTier | BoundNarrow,
        entries: list[_Entry[M]],
        bystanders: list[_Entry[M]],
    ) -> None:
        """Decide what a tier or one of its `Narrow`s does with each entry, and carry on through the `Narrow`s it chains to.

        Args:
            tier: The tier being assigned.
            stage: The tier itself, or a `Narrow` its `ambiguous` outcome
                chains to, whose outcomes decide the entries.
            entries: The entries that `stage` decides.
            bystanders: Entries that are not decided here but still hold the
                rows they match, so that they contest them: duplicates, which
                the chain narrows along with the entries.
        """
        if not entries and not bystanders:
            return
        holders: dict[Any, list[_Entry[M]]] = defaultdict(list)
        for entry in (*entries, *bystanders):
            for pk in entry.pks:
                holders[pk].append(entry)
        model = self._merger.config.model.__name__
        narrowing: list[_Entry[M]] = []
        for entry in entries:
            pks = entry.pks
            if not pks:
                self._decide(tier, entry, stage.missing, f"no {model} matches")
            elif len(pks) == 1 and len(holders[pks[0]]) == 1:
                entry.outcome = Update(entry.candidates[0])
            else:
                match stage.ambiguous:
                    case BoundNarrow():
                        narrowing.append(entry)
                    case First():
                        entry.outcome = Update(entry.candidates[0])
                    case outcome:
                        rivals = {id(h) for pk in pks for h in holders[pk]}
                        self._decide(
                            tier,
                            entry,
                            outcome,
                            ambiguous_text(
                                self._merger.config.model,
                                len(pks),
                                len(rivals),
                            ),
                        )
        if not isinstance(narrow := stage.ambiguous, BoundNarrow):
            return
        for entry in (*narrowing, *bystanders):
            entry.narrow(narrow.terms)
        self._settle(tier, narrow, narrowing, bystanders)

    def _decide(
        self, tier: BoundTier, entry: _Entry[M], outcome: Outcome, default: str
    ) -> None:
        """Apply an outcome that ends an entry's tier without taking a row.

        Args:
            tier: The tier being assigned.
            entry: The entry the outcome is for.
            outcome: The outcome declared.
            default: The reason a `Fail` without a message gives.
        """
        if isinstance(outcome, Fail):
            self._fail(tier, [entry], outcome.reason(default))
            return
        entry.outcome = outcome

    def _duplicate(
        self, tier: BoundTier, group: list[_Entry[M]], count: int
    ) -> None:
        """Apply a tier's `duplicate` outcome to entries that it cannot tell apart.

        Args:
            tier: The tier being assigned.
            group: The entries sharing a key, or picking one row.
            count: How many scraped items share the key.
        """
        outcome = tier.duplicate
        if not isinstance(outcome, Fail):
            for entry in group:
                entry.outcome = outcome
            return
        default = (
            f"{count} scraped items share a key; the key needs another term"
        )
        self._fail(tier, group, outcome.reason(default))

    def _fail(
        self, tier: BoundTier, group: list[_Entry[M]], message: str
    ) -> None:
        """Fail entries with a reason, logging the failure once however many entries it fails.

        Args:
            tier: The tier being assigned.
            group: The entries to fail: one entry, or a set of duplicates.
                Each carries the reason with its own key; the log line is the
                first entry's.
            message: What the reason says before the tier and key.
        """
        texts = [
            failure_text(
                self._merger, message, tier=tier.index, key=entry.shown_key
            )
            for entry in group
        ]
        for entry, text in zip(group, texts, strict=True):
            entry.outcome = _Failure(text)
        logger.error("%s", texts[0])

    def _collide(self, tier: BoundTier, entries: list[_Entry[M]]) -> None:
        """Apply the tier's `duplicate` outcome to entries that took the same row."""
        claims: dict[Any, list[_Entry[M]]] = defaultdict(list)
        for entry in entries:
            if isinstance(entry.outcome, Update):
                claims[entry.outcome.instance.pk].append(entry)
        for group in claims.values():
            if len(group) > 1:
                self._duplicate(tier, group, len(group))

    def _close(self, entries: list[_Entry[M]]) -> None:
        """Record the tier's outcomes on its members and take rows out of reach of later tiers.

        A claimed row is taken, and so are the candidates a failed member last
        had. Those of a member that falls through stay.
        """
        for entry in entries:
            outcome = entry.outcome
            if isinstance(outcome, Update):
                self._unavailable.add(outcome.instance.pk)
            elif isinstance(outcome, _Failure):
                self._unavailable.update(row.pk for row in entry.last)
            if outcome is not None and outcome is not Next:
                entry.member.resolution = outcome
