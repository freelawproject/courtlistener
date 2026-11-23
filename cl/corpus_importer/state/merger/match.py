"""Declarations of how a merger picks the stored row it merges into, and the checks that bind them to a merger."""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import Any, cast

from django.db.models import Field, Model
from typing_extensions import Sentinel

from . import state as MergerState
from .parameters import Create
from .pool import Ordering, Pool, Relatives
from .specifications import (
    AttributeMerger,
    Comparison,
    Source,
    _DatabaseProxy,
)

if typing.TYPE_CHECKING:
    from .base import Merger

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


type Term = str | Comparison | bool
"""A field name, as shorthand for comparing that stored field with the merger's computed value of it, or an `==` between two expressions.

Expressions are typed as the value they evaluate to, so a type checker sees `==` between them as a `bool`. A `bool` is accepted statically for that reason only: `Match.bind` rejects any term that is not a field name or a `Comparison`."""

type Outcome = Next | Create | Fail
"""What can end a tier's `missing` and `ambiguous` outcomes without a further choice."""

type MissingOutcome = Next | Create | Fail | type[Fail]
type AmbiguousOutcome = MissingOutcome | First | Narrow
type DuplicateOutcome = Next | Fail | type[Fail]


def _settled[T](outcome: T | type[Fail]) -> T | Fail:
    """Turn `Fail` passed as a class into an instance.

    Args:
        outcome: An outcome as declared.

    Returns:
        The outcome, with a bare `Fail` replaced by `Fail()`.
    """
    return Fail() if outcome is Fail else cast(T, outcome)


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
        if self.attribute is not None:
            value = getattr(merger, self.attribute)
        else:
            value = cast(AttributeMerger, self.scraped).transform(
                state.scrape, state.params, None
            )
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

        Returns:
            The bound term, or `None` if the name is not a concrete field of the
            model that the merger computes, which is recorded.
        """
        if (field := self.fields.get(name)) is None:
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
