"""Declarations of how a merger picks the stored row it merges into, and the checks that bind them to a merger."""

from __future__ import annotations

import logging
import operator
import typing
from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from functools import reduce
from typing import Any, Final, cast

from django.core.exceptions import ValidationError
from django.db.models import Field, Model, Q, QuerySet
from typing_extensions import Sentinel

from cl.corpus_importer.state.utils import MergeResult

from . import state as MergerState
from .parameters import Create, Update
from .pool import Ordering, Pool, PoolReader
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


@dataclass(slots=True)
class Fail:
    """Fail the merger, or as a `duplicate` outcome every merger sharing the key.

    Attributes:
        message: The reason given for the failure, used verbatim. Without one, the failure is described by the outcome it stands in for.
    """

    message: Final[str | None] = None

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

type MissingOutcome = Next | Create | Fail
"""What a declaration accepts for a `missing` outcome: an `Outcome`, with `Fail` allowed as a bare class."""

type AmbiguousOutcome = MissingOutcome | First | Narrow
"""What a declaration accepts for an `ambiguous` outcome: a `MissingOutcome`, or a `First` or `Narrow` to choose among the candidates."""

type DuplicateOutcome = Next | Fail
"""What a declaration accepts for a `duplicate` outcome: fall through or fail, with `Fail` allowed as a bare class."""


def failure_text(
    merger: type[Merger],
    text: str,
    *,
    tier: int,
    key: tuple[Any, ...] = (),
) -> str:
    """Build the reason a merger's lookup failed.

    Args:
        merger: The class of the merger that failed.
        text: What went wrong.
        tier: The tier the failure happened in, counted from 1.
        key: The values the member was told apart by when it failed.

    Returns:
        The reason, as given to the failed state and the log.
    """
    return f"{merger.__name__}: {text} (tier {tier}, key {key})"


def ambiguous_text(model: type[Model], rows: int, items: int) -> str:
    """Say why one stored row could not be picked.

    Args:
        model: The model of the rows.
        rows: How many rows the scraped item could be.
        items: How many scraped items hold any of those rows, including the one being picked for.

    Returns:
        The reason a failed lookup gives when it has no message of its own.
    """
    return f"cannot pick one {model.__name__}: {rows} rows for {items} scraped items"


class First:
    """Take the first candidate in a given order.

    Attributes:
        ordering: The fields to order candidates by, each a concrete field name or `pk` with an optional leading `-` for descending. A tier's ordering always ends in ascending `pk`, appended when not named.
    """

    __slots__ = ("ordering",)

    def __init__(self, *ordering: str) -> None:
        """Declare the order to take the first candidate in.

        Args:
            *ordering: The fields to order by. Nothing is checked until the declaration is bound to a merger.
        """
        self.ordering: Final[Ordering] = ordering


class Narrow:
    """Filter an ambiguous member's candidates on more terms, then apply outcomes of its own.

    A `Narrow` separates scraped items sharing a key as well as stored rows
    sharing one.

    Attributes:
        terms: The terms the candidates are filtered on.
        missing: What happens when the filter leaves no candidates.
        ambiguous: What happens when more than one candidate remains.
    """

    __slots__ = ("terms", "missing", "ambiguous")

    def __init__(
        self,
        *terms: Term,
        missing: MissingOutcome = Fail(),
        ambiguous: AmbiguousOutcome = Fail(),
    ) -> None:
        """Declare a narrowing.

        Args:
            *terms: The terms to filter the candidates on.
            missing: The outcome when no candidate satisfies the terms.
            ambiguous: The outcome when several still do.
        """
        self.terms: Final[tuple[Term, ...]] = terms
        self.missing: Final[Outcome] = missing
        self.ambiguous: Final[Outcome | First | Narrow] = ambiguous


class Key:
    """A match tier: the terms that find a member's candidate rows, and what to do when it finds none, several, or shares them.

    Attributes:
        terms: The terms the stored rows must equal the member on.
        missing: What happens when no available row matches.
        ambiguous: What happens when the match is not one member to one row.
        duplicate: What happens when another member has equal values for every term of the tier.
    """

    __slots__ = ("terms", "missing", "ambiguous", "duplicate")

    def __init__(
        self,
        *terms: Term,
        missing: MissingOutcome = Next,
        ambiguous: AmbiguousOutcome = Fail(),
        duplicate: DuplicateOutcome = Fail(),
    ) -> None:
        """Declare a tier.

        Args:
            *terms: The terms the stored rows must equal the member on.
            missing: The outcome when no available row matches.
            ambiguous: The outcome when several rows match, or when members that are not duplicates share a candidate.
            duplicate: The outcome for members that nothing in the tier can tell apart.
        """
        self.terms: Final[tuple[Term, ...]] = terms
        self.missing: Final[Outcome] = missing
        self.ambiguous: Final[Outcome | First | Narrow] = ambiguous
        self.duplicate: Final[Next | Fail] = duplicate


@dataclass(slots=True)
class BoundTerm:
    """A term checked against its merger, ready to evaluate on either side.

    Compared by identity: expressions overload `==`.

    Attributes:
        stored: The side that reads the stored row.
        field: The stored field, set when `stored` is a bare `Database`. The scraped value is converted by it before it is compared.
        attribute: The merger attribute holding the scraped value, set for the string shorthand.
        scraped: The expression for the scraped value, set for an explicit term.
    """

    stored: Final[AttributeMerger]
    field: Final[Field | None] = None
    attribute: Final[str | None] = None
    scraped: Final[AttributeMerger | None] = None

    def stored_value(self, row: Model) -> Any:
        """Evaluate the stored side on a row.

        Args:
            row: A stored row, loaded with the pool's annotations if the term reads any.

        Returns:
            The row's value for the term.
        """
        return self.stored.transform(None, None, row)

    def scraped_raw(
        self, merger: Merger, state: MergerState.Lookup[Any, Any, Any]
    ) -> Any:
        """Evaluate the scraped side for a merger, before the stored field converts it.

        Args:
            merger: The merger being matched; the shorthand reads the value it computed for its attribute.
            state: The merger's state, whose scrape and params an explicit term is evaluated against.

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
            merger: The merger being matched; the shorthand reads the value it computed for its attribute.
            state: The merger's state, whose scrape and params an explicit term is evaluated against.

        Returns:
            The value to compare with `stored_value`, converted by the stored field when there is one.

        Raises:
            django.core.exceptions.ValidationError: If the stored field rejects the scraped value.
        """
        value = self.scraped_raw(merger, state)
        if self.field is None:
            return value
        return self.field.to_python(value)


@dataclass(slots=True)
class BoundNarrow:
    """A `Narrow` whose terms are bound.

    Attributes:
        terms: The bound terms the candidates are filtered on.
        missing: What happens when the filter leaves no candidates.
        ambiguous: What happens when more than one candidate remains.
    """

    terms: Final[tuple[BoundTerm, ...]]
    missing: Final[Outcome]
    ambiguous: Final[AmbiguousBound]


type AmbiguousBound = Outcome | First | BoundNarrow
"""What a bound `ambiguous` outcome can be: an `Outcome`, or a `First` or `BoundNarrow` to choose among the candidates."""


@dataclass(slots=True)
class BoundTier:
    """A `Key` checked against its merger.

    Attributes:
        index: The tier's position in the match, counted from 1.
        terms: The tier's bound key terms.
        missing: What happens when no available row matches.
        ambiguous: What happens when the match is not one member to one row.
        duplicate: What happens to members the tier cannot tell apart.
        ordering: The order candidates are taken in, always ending in `pk` so the pick is deterministic.
    """

    index: Final[int]
    terms: Final[tuple[BoundTerm, ...]]
    missing: Final[Outcome]
    ambiguous: Final[AmbiguousBound]
    duplicate: Final[Next | Fail]
    ordering: Final[Ordering]

    @property
    def chain_terms(self) -> tuple[BoundTerm, ...]:
        """The terms of every `Narrow` the tier's `ambiguous` outcome chains through, in order."""
        terms: list[BoundTerm] = []
        outcome = self.ambiguous
        while isinstance(outcome, BoundNarrow):
            terms.extend(outcome.terms)
            outcome = outcome.ambiguous
        return tuple(terms)


@dataclass(slots=True)
class BoundMatch:
    """A `Match` checked against its merger.

    Attributes:
        tiers: The bound tiers, in priority order.
        columns: The model fields the match reads from stored rows: every stored side's database fields and every ordering field.
    """

    tiers: Final[tuple[BoundTier, ...]]
    columns: Final[frozenset[str]]

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
        if not pool.keyed:
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

    def tier(self, index: int, key: Key) -> BoundTier:
        """Bind a tier.

        Args:
            index: The tier's position in the match, counted from 1.
            key: The tier as declared.

        Returns:
            The bound tier.
        """
        self.tier_index = index
        bound = (self.term(term) for term in key.terms)
        terms = tuple(b for b in bound if b is not None)
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
                bound = (self.term(term) for term in outcome.terms)
                return BoundNarrow(
                    terms=tuple(b for b in bound if b is not None),
                    missing=outcome.missing,
                    ambiguous=self.ambiguous(outcome.ambiguous),
                )
            case First():
                for item in outcome.ordering:
                    name = item.removeprefix("-")
                    if name == "pk":
                        continue
                    if (field := self.fields.get(name)) is None:
                        self.errors.append(
                            ValueError(
                                f"tier {self.tier_index}: cannot order by {item!r}: an ordering is a concrete field of {self.model.__name__} or pk, optionally prefixed with '-'"
                            )
                        )
                    elif field.is_relation:
                        self.errors.append(
                            ValueError(
                                f"tier {self.tier_index}: cannot order by {item!r}: {name!r} is a relation, which the database orders by the related model's ordering"
                            )
                        )
                return outcome
            case _:
                return outcome

    def term(self, term: object) -> BoundTerm | None:
        """Bind one term.

        Args:
            term: The term as declared.

        Returns:
            The bound term, or `None` if it has a problem, which is recorded.
        """
        match term:
            case str():
                if (field := self.named_fields.get(term)) is None:
                    self.errors.append(
                        ValueError(
                            f"tier {self.tier_index}: {term!r} is not a concrete field of {self.model.__name__}"
                        )
                    )
                    return None
                if term not in self.merger.config.registry.attr:
                    self.errors.append(
                        ValueError(
                            f"tier {self.tier_index}: {self.merger.__name__} does not compute {term!r}, so the shorthand term has no scraped value"
                        )
                    )
                    return None
                return BoundTerm(
                    stored=_DatabaseProxy(field), field=field, attribute=term
                )
            case Comparison():
                stored_sides = [
                    side
                    for side in (term.left, term.right)
                    if side._sources & STORED_SOURCES
                ]
                if len(stored_sides) != 1:
                    self.errors.append(
                        ValueError(
                            f"tier {self.tier_index}: exactly one side of a term must read the stored row (Database or Annotation)"
                        )
                    )
                    return None
                stored = stored_sides[0]
                scraped = term.right if stored is term.left else term.left
                valid = True
                if disallowed := stored._sources & ~ALLOWED_STORED_SOURCES:
                    self.errors.append(
                        ValueError(
                            f"tier {self.tier_index}: the stored side of a term may only read Database, Annotation and Constant, not {disallowed}"
                        )
                    )
                    valid = False
                for key in stored._annotations:
                    if key not in self.annotations:
                        self.errors.append(
                            ValueError(
                                f"tier {self.tier_index}: annotation {key!r} is not annotated by the pool of {self.merger.__name__}"
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
            case _:
                self.errors.append(
                    TypeError(
                        f"tier {self.tier_index}: {term!r} is not a term: use a field name or an == between two expressions"
                    )
                )
                return None


class Match:
    """An ordered list of tiers that picks the stored row a merger merges into.

    Attributes:
        tiers: The tiers, in priority order.
    """

    __slots__ = ("tiers",)

    def __init__(self, *tiers: Key) -> None:
        """Declare a match. Nothing is checked until `bind`.

        Args:
            *tiers: The tiers, in priority order.
        """
        self.tiers: Final[tuple[Key, ...]] = tiers

    def bind(self, merger: type[Merger], pool: Pool | None) -> BoundMatch:
        """Check the declaration against a merger and produce what the matcher consumes.

        Args:
            merger: The merger class the match is declared on.
            pool: The merger's declared pool. Annotations a term reads must be ones it adds.

        Returns:
            The bound match.

        Raises:
            ExceptionGroup: Of every problem found in the declaration.
        """
        binder = _Binder(merger, pool)
        if not self.tiers:
            binder.errors.append(ValueError("a match needs at least one tier"))
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


@dataclass(slots=True)
class _Failure:
    """How a member's lookup ended in failure.

    Attributes:
        text: The reason, as given to the failed state and the log.
    """

    text: Final[str]


type Resolution[M: Model] = Update[M] | Create | _Failure
"""How a member's lookup ended: the row it merges into, a new row, or a failure."""


@dataclass(slots=True)
class _TierKey:
    """What a member is told apart by in one tier.

    Attributes:
        relations: The primary keys of the member's relation params, in sorted param-name order.
        values: The scraped values of the tier's key terms.
        chain: The scraped values of the terms of every `Narrow` the tier chains through.
    """

    relations: Final[tuple[Any, ...]]
    values: Final[tuple[Any, ...]]
    chain: Final[tuple[Any, ...]]

    @property
    def key(self) -> tuple[Any, ...]:
        """The values stored rows must equal to be the member's candidates."""
        return (*self.relations, *self.values)

    @property
    def duplicate(self) -> tuple[Any, ...]:
        """The values that members share when nothing in the tier can tell them apart."""
        return (*self.key, *self.chain)


@dataclass(slots=True)
class _Member[M: Model]:
    """A merger in a group and how its lookup is going.

    Attributes:
        merger: The merger.
        state: The merger's state, which its scrape and params are read from.
        keys: The member's `_TierKey` for each tier. Empty until the group is assigned.
        resolution: How the member's lookup ended, or `None` while it is still looking.
    """

    merger: Merger[Any, Any, M]
    state: MergerState.Lookup[Any, Any, M]
    keys: tuple[_TierKey, ...] = ()
    resolution: Resolution[M] | None = None


@dataclass(slots=True)
class _Entry[M: Model]:
    """A member's progress through one tier.

    Attributes:
        member: The member.
        key: The member's key in the tier.
        candidates: The available rows still matching the member, in the order the pool handed them out. A pool that reads one row for each join may list a primary key more than once.
        last: The candidates before the last filter that emptied them, or the current ones while there are some.
        depth: How many terms of the tier's `Narrow` chain have filtered the candidates.
        outcome: What the tier decided for the member so far.
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
            terms: The terms of the `Narrow` being applied, which must be the ones following those already applied.
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

    Every merger of the group has to be joined before any asks for its verdict: the first verdict assigns every joined merger, so that a tier is a priority across the group and the result does not depend on the order the mergers were created in. Rows created while the group merges are not seen.
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
            reader: The reader of the pool the group's rows come from, built for the first tier's ordering.
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
            relation: What the parent holds in the group's relation, if the group is a relation of another merger.
            params: The params the group's mergers were created with.

        Returns:
            The group, with no members.

        Raises:
            TypeError: If the merger matches by its `match` and that cannot be matched in the pool.
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
            merger: A merger of the group's class with its values computed. Mergers that fail validation or are not looking for their row are not members.
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
            The state the merger moves to: creating a row, updating the row it was assigned, or failed.
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
            position = tier.index - 1
            looking = [m for m in live if m.resolution is None]
            if not looking:
                continue

            position = tier.index - 1
            alternatives: dict[tuple[Any, ...], Q] = {}
            for member in looking:
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
                alternatives[key.key] = Q(
                    **member.state.relation_params
                ) & reduce(operator.and_, terms, Q())

            rows = self._reader.rows(
                reduce(operator.or_, alternatives.values()), tier.ordering
            )
            index: dict[tuple[Any, ...], list[M]] = defaultdict(list)
            for row in rows:
                if row.pk not in self._unavailable:
                    row_key = (
                        *(
                            getattr(row, attname)
                            for attname in self._relation_attnames
                        ),
                        *(term.stored_value(row) for term in tier.terms),
                    )
                    index[row_key].append(row)
            entries = []
            for member in looking:
                key = member.keys[position]
                candidates = index.get(key.key, [])
                entries.append(_Entry(member, key, candidates, candidates))
            # A member that an earlier tier assigned still shares its key.
            sharing = Counter(m.keys[position].duplicate for m in live)
            # On a last tier that lets duplicates through, they are judged by their
            # candidates like any other member.
            checks_duplicates = not (
                position == len(tiers) - 1 and tier.duplicate is Next
            )
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

            claims: dict[Any, list[_Entry[M]]] = defaultdict(list)
            for entry in entries:
                if isinstance(entry.outcome, Update):
                    claims[entry.outcome.instance.pk].append(entry)
            for group in claims.values():
                if len(group) > 1:
                    self._duplicate(tier, group, len(group))

            for entry in entries:
                outcome = entry.outcome
                if isinstance(outcome, Update):
                    self._unavailable.add(outcome.instance.pk)
                elif isinstance(outcome, _Failure):
                    self._unavailable.update(row.pk for row in entry.last)
                if outcome is not None and outcome is not Next:
                    entry.member.resolution = outcome

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
            stage: The tier itself, or a `Narrow` its `ambiguous` outcome chains to, whose outcomes decide the entries.
            entries: The entries that `stage` decides.
            bystanders: Entries that are not decided here but still hold the rows they match, so that they contest them: duplicates, which the chain narrows along with the entries.
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
            group: The entries to fail: one entry, or a set of duplicates. Each carries the reason with its own key; the log line is the first entry's.
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
