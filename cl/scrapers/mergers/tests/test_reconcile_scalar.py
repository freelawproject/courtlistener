"""Tests for ``apply_scalar_strategy``.

Per the theory doc:
- ``ScrapeWins(s, d)`` -> Write(s) if s != d, else NoChange.
- ``ScrapeWinsIfPresent(None, d)`` -> NoChange (don't clobber DB with None).
- ``ScrapeWinsIfPresent(s, d)`` for s != None -> same as ScrapeWins.
- ``DBWins(s, d)`` -> NoChange (always).
- ``Custom(fn)(s, d)`` -> Write(fn(s, d)) if that differs from d, else NoChange.

A misapplied strategy (e.g., passing a CollectionStrategy) raises TypeError.
"""

from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from cl.scrapers.mergers.ops import NoChange, Write
from cl.scrapers.mergers.reconcile import apply_scalar_strategy
from cl.scrapers.mergers.strategies import (
    Custom,
    DBWins,
    ScrapeClobbers,
    ScrapeWins,
    ScrapeWinsIfPresent,
)
from cl.tests.cases import SimpleTestCase as TestCase


class ScrapeWinsTest(TestCase):
    def test_writes_when_different(self) -> None:
        self.assertEqual(apply_scalar_strategy(ScrapeWins, "a", "b"), Write("a"))

    def test_nochange_when_equal(self) -> None:
        self.assertIs(apply_scalar_strategy(ScrapeWins, "a", "a"), NoChange)

    def test_writes_none_to_overwrite(self) -> None:
        """ScrapeWins is truly authoritative — None overwrites."""
        self.assertEqual(apply_scalar_strategy(ScrapeWins, None, "x"), Write(None))


class ScrapeWinsIfPresentTest(TestCase):
    def test_nochange_when_scrape_is_none(self) -> None:
        self.assertIs(
            apply_scalar_strategy(ScrapeWinsIfPresent, None, "x"), NoChange
        )

    def test_nochange_when_scrape_is_none_and_db_is_none(self) -> None:
        self.assertIs(
            apply_scalar_strategy(ScrapeWinsIfPresent, None, None), NoChange
        )

    def test_writes_when_scrape_is_set_and_different(self) -> None:
        self.assertEqual(
            apply_scalar_strategy(ScrapeWinsIfPresent, "a", "b"), Write("a")
        )

    def test_writes_when_scrape_is_set_and_db_is_none(self) -> None:
        self.assertEqual(
            apply_scalar_strategy(ScrapeWinsIfPresent, "x", None), Write("x")
        )

    def test_nochange_when_equal_nonzero(self) -> None:
        self.assertIs(
            apply_scalar_strategy(ScrapeWinsIfPresent, "a", "a"), NoChange
        )

    def test_empty_string_overwrites(self) -> None:
        """Convention: scrapers normalize "" -> None at parse time. If they
        don't, "" is a real value that overwrites under
        ScrapeWinsIfPresent."""
        self.assertEqual(
            apply_scalar_strategy(ScrapeWinsIfPresent, "", "x"), Write("")
        )


class DBWinsTest(TestCase):
    def test_nochange_always(self) -> None:
        self.assertIs(apply_scalar_strategy(DBWins, "a", "b"), NoChange)
        self.assertIs(apply_scalar_strategy(DBWins, None, "b"), NoChange)
        self.assertIs(apply_scalar_strategy(DBWins, "a", None), NoChange)
        self.assertIs(apply_scalar_strategy(DBWins, "a", "a"), NoChange)


class CustomTest(TestCase):
    def test_writes_when_fn_returns_different(self) -> None:
        c = Custom(lambda s, d: s + d)
        self.assertEqual(apply_scalar_strategy(c, 2, 3), Write(5))

    def test_nochange_when_fn_returns_db_value(self) -> None:
        c = Custom(lambda s, d: d)  # always returns db -> no change
        self.assertIs(apply_scalar_strategy(c, "a", "b"), NoChange)

    def test_fn_sees_both_args(self) -> None:
        received: list[tuple[Any, Any]] = []

        def fn(s: Any, d: Any) -> Any:
            received.append((s, d))
            return s

        apply_scalar_strategy(Custom(fn), 1, 2)
        self.assertEqual(received, [(1, 2)])

    def test_bitmask_or_pattern(self) -> None:
        """Realistic case: add_scraper_source bitmask."""
        SCRAPER_BIT = 0b0100
        c = Custom(lambda s, d: (d or 0) | SCRAPER_BIT)
        self.assertEqual(apply_scalar_strategy(c, 0, 0b0001), Write(0b0101))
        self.assertEqual(apply_scalar_strategy(c, 0, None), Write(SCRAPER_BIT))


class MisapplicationTest(TestCase):
    def test_collection_strategy_raises(self) -> None:
        with self.assertRaises(TypeError):
            apply_scalar_strategy(ScrapeClobbers, "a", "b")  # type: ignore[arg-type]

    def test_unknown_strategy_raises(self) -> None:
        with self.assertRaises(TypeError):
            apply_scalar_strategy("not-a-strategy", "a", "b")  # type: ignore[arg-type]


class ScalarStrategyPropertyTest(TestCase):
    @given(
        s=st.one_of(st.integers(), st.text(), st.none()),
        d=st.one_of(st.integers(), st.text(), st.none()),
    )
    def test_scrape_wins_property(self, s: Any, d: Any) -> None:
        """ScrapeWins returns Write(s) iff s != d, else NoChange."""
        result = apply_scalar_strategy(ScrapeWins, s, d)
        if s == d:
            self.assertIs(result, NoChange)
        else:
            self.assertEqual(result, Write(s))

    @given(
        s=st.one_of(st.integers(), st.text(), st.none()),
        d=st.one_of(st.integers(), st.text(), st.none()),
    )
    def test_db_wins_is_total_no_change(self, s: Any, d: Any) -> None:
        """DBWins always returns NoChange."""
        self.assertIs(apply_scalar_strategy(DBWins, s, d), NoChange)

    @given(
        s=st.one_of(st.integers(), st.text(), st.none()),
        d=st.one_of(st.integers(), st.text(), st.none()),
    )
    def test_scrape_wins_if_present_property(
        self, s: Any, d: Any
    ) -> None:
        """ScrapeWinsIfPresent treats None as 'absent'; otherwise behaves
        like ScrapeWins."""
        result = apply_scalar_strategy(ScrapeWinsIfPresent, s, d)
        if s is None:
            self.assertIs(result, NoChange)
        elif s == d:
            self.assertIs(result, NoChange)
        else:
            self.assertEqual(result, Write(s))

    @given(
        s=st.one_of(st.integers(), st.text(), st.none()),
        d=st.one_of(st.integers(), st.text(), st.none()),
    )
    def test_scrape_wins_is_idempotent(self, s: Any, d: Any) -> None:
        """After applying ScrapeWins once and writing the result to the
        DB, applying again should produce NoChange."""
        first = apply_scalar_strategy(ScrapeWins, s, d)
        new_db = first.value if isinstance(first, Write) else d
        second = apply_scalar_strategy(ScrapeWins, s, new_db)
        self.assertIs(second, NoChange)
