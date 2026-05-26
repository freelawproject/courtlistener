"""Reconciliation strategies for scalar and collection fields.

Scalar and collection strategies are two disjoint hierarchies so that
applying the wrong one to a field can be detected at class-creation
time. The simple cases are public singletons of internal types; the
``Custom`` / ``CustomCollection`` classes carry user functions.

See cl/scrapers/MERGERS_IN_THEORY.md (Strategies section).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Bases
# ---------------------------------------------------------------------------

class ScalarStrategy:
    """Base class for scalar field strategies."""


class CollectionStrategy:
    """Base class for collection field strategies."""


# ---------------------------------------------------------------------------
# Scalar strategies
# ---------------------------------------------------------------------------

class _ScrapeWins(ScalarStrategy):
    """Write the scrape value (skip if ``==`` to DB value)."""


class _ScrapeWinsIfPresent(ScalarStrategy):
    """Write the scrape value only when it is not ``None``.

    Use for optional refs where the scraper passes ``None`` to mean
    "missing" and we don't want to clobber a real DB value with it.
    """


class _DBWins(ScalarStrategy):
    """Leave the DB value alone."""


@dataclass(frozen=True)
class Custom(ScalarStrategy):
    """Custom scalar strategy: ``fn(scrape_val, db_val) -> field_val``."""

    fn: Callable[[Any, Any], Any]


# ---------------------------------------------------------------------------
# Collection strategies
# ---------------------------------------------------------------------------

class _ScrapeClobbers(CollectionStrategy):
    """Scrape rules: unmatched DB rows are deleted; unmatched scrape rows are
    created."""


class _DBClobbers(CollectionStrategy):
    """DB rules: unmatched DB rows are kept; unmatched scrape rows are
    skipped."""


class _Union(CollectionStrategy):
    """Unmatched DB rows are kept; unmatched scrape rows are created."""


@dataclass(frozen=True)
class CustomCollection(CollectionStrategy):
    """Custom collection strategy: ``fn(pairs, scrape_only, db_only) -> ops``."""

    fn: Callable[[Any, Any, Any], Any]


# ---------------------------------------------------------------------------
# Public singletons
# ---------------------------------------------------------------------------

ScrapeWins: _ScrapeWins = _ScrapeWins()
ScrapeWinsIfPresent: _ScrapeWinsIfPresent = _ScrapeWinsIfPresent()
DBWins: _DBWins = _DBWins()

ScrapeClobbers: _ScrapeClobbers = _ScrapeClobbers()
DBClobbers: _DBClobbers = _DBClobbers()
Union: _Union = _Union()
