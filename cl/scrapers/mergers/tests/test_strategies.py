"""Tests for strategy markers.

Scalar and collection strategies are distinct type hierarchies, so mixing
them in the wrong place can be detected by the framework at runtime
(class-creation time, in L3).

Singletons (``ScrapeWins`` etc.) are public instances of internal
single-class types. ``Custom`` / ``CustomCollection`` are classes whose
instances carry the user-supplied function.

The framework's only concerns at this layer are:
- The base-class hierarchy holds.
- Singletons are the right kind.
- ``Custom`` / ``CustomCollection`` carry their fn.
- Custom instances can be compared by their fn for equality.
"""

from typing import Any

from cl.scrapers.mergers.strategies import (
    CollectionStrategy,
    Custom,
    CustomCollection,
    DBClobbers,
    DBWins,
    ScalarStrategy,
    ScrapeClobbers,
    ScrapeWins,
    ScrapeWinsIfPresent,
    Union,
)
from cl.tests.cases import SimpleTestCase as TestCase


class ScalarSingletonsTest(TestCase):
    def test_scrape_wins_is_scalar(self) -> None:
        self.assertIsInstance(ScrapeWins, ScalarStrategy)

    def test_scrape_wins_if_present_is_scalar(self) -> None:
        self.assertIsInstance(ScrapeWinsIfPresent, ScalarStrategy)

    def test_db_wins_is_scalar(self) -> None:
        self.assertIsInstance(DBWins, ScalarStrategy)

    def test_scalar_singletons_are_not_collection(self) -> None:
        for s in [ScrapeWins, ScrapeWinsIfPresent, DBWins]:
            with self.subTest(strategy=s):
                self.assertNotIsInstance(s, CollectionStrategy)

    def test_scalar_singletons_are_distinct(self) -> None:
        self.assertIsNot(ScrapeWins, DBWins)
        self.assertIsNot(ScrapeWins, ScrapeWinsIfPresent)
        self.assertIsNot(DBWins, ScrapeWinsIfPresent)


class CollectionSingletonsTest(TestCase):
    def test_scrape_clobbers_is_collection(self) -> None:
        self.assertIsInstance(ScrapeClobbers, CollectionStrategy)

    def test_db_clobbers_is_collection(self) -> None:
        self.assertIsInstance(DBClobbers, CollectionStrategy)

    def test_union_is_collection(self) -> None:
        self.assertIsInstance(Union, CollectionStrategy)

    def test_collection_singletons_are_not_scalar(self) -> None:
        for s in [ScrapeClobbers, DBClobbers, Union]:
            with self.subTest(strategy=s):
                self.assertNotIsInstance(s, ScalarStrategy)

    def test_collection_singletons_are_distinct(self) -> None:
        self.assertIsNot(ScrapeClobbers, DBClobbers)
        self.assertIsNot(ScrapeClobbers, Union)
        self.assertIsNot(DBClobbers, Union)


class CustomScalarTest(TestCase):
    def test_custom_is_scalar(self) -> None:
        c = Custom(lambda s, d: s)
        self.assertIsInstance(c, ScalarStrategy)

    def test_custom_is_not_collection(self) -> None:
        c = Custom(lambda s, d: s)
        self.assertNotIsInstance(c, CollectionStrategy)

    def test_custom_carries_fn(self) -> None:
        def fn(s: Any, d: Any) -> Any:
            return s

        c = Custom(fn)
        self.assertIs(c.fn, fn)

    def test_custom_equality_by_fn(self) -> None:
        fn = lambda s, d: s  # noqa: E731
        self.assertEqual(Custom(fn), Custom(fn))

    def test_custom_inequality_when_fn_differs(self) -> None:
        f1 = lambda s, d: s  # noqa: E731
        f2 = lambda s, d: d  # noqa: E731
        self.assertNotEqual(Custom(f1), Custom(f2))


class CustomCollectionTest(TestCase):
    def test_custom_collection_is_collection(self) -> None:
        c = CustomCollection(lambda pairs, scrape_only, db_only: [])
        self.assertIsInstance(c, CollectionStrategy)

    def test_custom_collection_is_not_scalar(self) -> None:
        c = CustomCollection(lambda pairs, scrape_only, db_only: [])
        self.assertNotIsInstance(c, ScalarStrategy)

    def test_custom_collection_carries_fn(self) -> None:
        def fn(
            pairs: list[Any], scrape_only: list[Any], db_only: list[Any]
        ) -> list[Any]:
            return []

        c = CustomCollection(fn)
        self.assertIs(c.fn, fn)


class StrategyBaseHierarchyTest(TestCase):
    """Sanity: the two strategy hierarchies are disjoint."""

    def test_scalar_and_collection_are_disjoint_bases(self) -> None:
        # No common base except `object`.
        self.assertFalse(issubclass(ScalarStrategy, CollectionStrategy))
        self.assertFalse(issubclass(CollectionStrategy, ScalarStrategy))
