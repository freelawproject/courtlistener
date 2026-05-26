"""Reconciliation result types: scalar decisions and collection ops.

These are the data types produced by reconciliation (phase 3) and
consumed by application (phase 4). They are deliberately tiny dataclasses
with no behavior so consumers can pattern-match on them cleanly.

See cl/scrapers/MERGERS_IN_THEORY.md.
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Scalar decisions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Write[T]:
    """The value to write to a scalar field."""

    value: T


class _NoChange:
    """Singleton: this field should not be written."""

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "NoChange"


NoChange: _NoChange = _NoChange()


type ScalarDecision[T] = Write[T] | _NoChange


# ---------------------------------------------------------------------------
# Collection ops
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Create[ScrapeT]:
    """Insert a new row from a scrape node."""

    scrape: ScrapeT


@dataclass(frozen=True)
class Update[ScrapeT, DBT]:
    """Reconcile fields of an existing row against the scrape node.

    Whether anything actually changes is determined by the per-field
    scalar strategies during the reconcile walk.
    """

    scrape: ScrapeT
    db: DBT


@dataclass(frozen=True)
class Delete[DBT]:
    """Remove an existing row from the DB."""

    db: DBT


type Op[ScrapeT, DBT] = Create[ScrapeT] | Update[ScrapeT, DBT] | Delete[DBT]


# ---------------------------------------------------------------------------
# Collection pairing result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Pairing[ScrapeT, DBT]:
    """Output of ``pair_by_nk``: scrape and DB items partitioned by NK match.

    :ivar pairs: ``(scrape, db)`` for items whose NK matched on both sides.
    :ivar scrape_only: scrape items with no DB match.
    :ivar db_only: DB items with no scrape match.
    """

    pairs: list[tuple[ScrapeT, DBT]] = field(default_factory=list)
    scrape_only: list[ScrapeT] = field(default_factory=list)
    db_only: list[DBT] = field(default_factory=list)
