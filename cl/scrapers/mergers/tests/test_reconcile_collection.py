"""Tests for ``apply_collection_strategy``.

Given a ``Pairing`` (pairs / scrape_only / db_only) and a
``CollectionStrategy``, return the list of ops to apply.

Per the theory doc:
| Strategy        | pairs       | scrape_only  | db_only  |
| --------------- | ----------- | ------------ | -------- |
| ScrapeClobbers  | Update      | Create       | Delete   |
| DBClobbers      | Update      | (skip)       | (keep)   |
| Union           | Update      | Create       | (keep)   |
| CustomCollection| caller decides via fn                     |

Pairs always emit Update; per-field strategies during the reconcile walk
decide whether the Update actually writes anything.
"""

from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from cl.scrapers.mergers.ops import (
    Create,
    Delete,
    Op,
    Pairing,
    Update,
)
from cl.scrapers.mergers.reconcile import apply_collection_strategy
from cl.scrapers.mergers.strategies import (
    CustomCollection,
    DBClobbers,
    ScrapeClobbers,
    ScrapeWins,
    Union,
)
from cl.tests.cases import SimpleTestCase as TestCase


def _sample_pairing() -> Pairing[str, str]:
    """A pairing with one of each bucket."""
    return Pairing(
        pairs=[("s_a", "d_a")],
        scrape_only=["s_b"],
        db_only=["d_c"],
    )


class ScrapeClobbersTest(TestCase):
    def test_emits_all_three_op_types(self) -> None:
        ops = apply_collection_strategy(ScrapeClobbers, _sample_pairing())
        self.assertEqual(
            ops,
            [
                Update("s_a", "d_a"),
                Create("s_b"),
                Delete("d_c"),
            ],
        )

    def test_empty_pairing(self) -> None:
        ops = apply_collection_strategy(ScrapeClobbers, Pairing())
        self.assertEqual(ops, [])

    def test_only_pairs(self) -> None:
        p = Pairing(pairs=[("s1", "d1"), ("s2", "d2")], scrape_only=[], db_only=[])
        ops = apply_collection_strategy(ScrapeClobbers, p)
        self.assertEqual(ops, [Update("s1", "d1"), Update("s2", "d2")])

    def test_only_scrape_side(self) -> None:
        p = Pairing(pairs=[], scrape_only=["s1", "s2"], db_only=[])
        ops = apply_collection_strategy(ScrapeClobbers, p)
        self.assertEqual(ops, [Create("s1"), Create("s2")])

    def test_only_db_side(self) -> None:
        p = Pairing(pairs=[], scrape_only=[], db_only=["d1", "d2"])
        ops = apply_collection_strategy(ScrapeClobbers, p)
        self.assertEqual(ops, [Delete("d1"), Delete("d2")])


class DBClobbersTest(TestCase):
    def test_emits_only_updates_for_pairs(self) -> None:
        ops = apply_collection_strategy(DBClobbers, _sample_pairing())
        self.assertEqual(ops, [Update("s_a", "d_a")])

    def test_no_ops_for_unmatched_buckets(self) -> None:
        p = Pairing(pairs=[], scrape_only=["s1"], db_only=["d1"])
        self.assertEqual(apply_collection_strategy(DBClobbers, p), [])


class UnionTest(TestCase):
    def test_emits_updates_and_creates_no_deletes(self) -> None:
        ops = apply_collection_strategy(Union, _sample_pairing())
        self.assertEqual(
            ops,
            [
                Update("s_a", "d_a"),
                Create("s_b"),
            ],
        )

    def test_db_only_is_silent(self) -> None:
        p = Pairing(pairs=[], scrape_only=[], db_only=["d1", "d2"])
        self.assertEqual(apply_collection_strategy(Union, p), [])


class CustomCollectionTest(TestCase):
    def test_delegates_to_fn(self) -> None:
        received: list[tuple[Any, Any, Any]] = []

        def fn(
            pairs: list[Any], scrape_only: list[Any], db_only: list[Any]
        ) -> list[Op[Any, Any]]:
            received.append((pairs, scrape_only, db_only))
            return [Create("custom")]

        ops = apply_collection_strategy(
            CustomCollection(fn), _sample_pairing()
        )
        self.assertEqual(ops, [Create("custom")])
        self.assertEqual(
            received,
            [([("s_a", "d_a")], ["s_b"], ["d_c"])],
        )

    def test_fn_can_return_empty_list(self) -> None:
        c = CustomCollection(lambda p, s, d: [])
        self.assertEqual(
            apply_collection_strategy(c, _sample_pairing()), []
        )

    def test_fn_can_return_mixed_ops(self) -> None:
        def fn(
            pairs: list[Any], scrape_only: list[Any], db_only: list[Any]
        ) -> list[Op[Any, Any]]:
            return [Delete(d) for d in db_only] + [Create(s) for s in scrape_only]

        ops = apply_collection_strategy(
            CustomCollection(fn), _sample_pairing()
        )
        self.assertEqual(ops, [Delete("d_c"), Create("s_b")])


class MisapplicationTest(TestCase):
    def test_scalar_strategy_raises(self) -> None:
        with self.assertRaises(TypeError):
            apply_collection_strategy(ScrapeWins, _sample_pairing())  # type: ignore[arg-type]

    def test_unknown_strategy_raises(self) -> None:
        with self.assertRaises(TypeError):
            apply_collection_strategy("not-a-strategy", _sample_pairing())  # type: ignore[arg-type]


class CollectionStrategyPropertyTest(TestCase):
    _pairing_strategy = st.builds(
        Pairing,
        pairs=st.lists(
            st.tuples(st.integers(), st.integers()), max_size=5
        ),
        scrape_only=st.lists(st.integers(), max_size=5),
        db_only=st.lists(st.integers(), max_size=5),
    )

    @given(p=_pairing_strategy)
    def test_scrape_clobbers_emits_one_op_per_input(
        self, p: Pairing[int, int]
    ) -> None:
        ops = apply_collection_strategy(ScrapeClobbers, p)
        self.assertEqual(
            len(ops), len(p.pairs) + len(p.scrape_only) + len(p.db_only)
        )

    @given(p=_pairing_strategy)
    def test_db_clobbers_emits_only_for_pairs(
        self, p: Pairing[int, int]
    ) -> None:
        ops = apply_collection_strategy(DBClobbers, p)
        self.assertEqual(len(ops), len(p.pairs))
        self.assertTrue(all(isinstance(op, Update) for op in ops))

    @given(p=_pairing_strategy)
    def test_union_emits_for_pairs_and_scrape_only(
        self, p: Pairing[int, int]
    ) -> None:
        ops = apply_collection_strategy(Union, p)
        self.assertEqual(len(ops), len(p.pairs) + len(p.scrape_only))
        # No Deletes under Union.
        self.assertFalse(any(isinstance(op, Delete) for op in ops))
