"""Tests for ``pair_by_nk``.

``pair_by_nk`` is a hash-join: O(n + m) over scrape items + db items, given
a key function that produces a hashable natural key per item. Returns a
``Pairing`` with three buckets:

- ``pairs``: ``[(scrape_item, db_item)]`` for matched NKs.
- ``scrape_only``: items in scrape with no DB match.
- ``db_only``: items in DB with no scrape match.

Preconditions (no ``allow_duplicates`` here):
- All NKs in scrape are distinct.
- All NKs in db are distinct.

Both preconditions raise ``ValueError`` on violation.
"""

from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from cl.scrapers.mergers.ops import Pairing
from cl.scrapers.mergers.reconcile import pair_by_nk
from cl.tests.cases import SimpleTestCase as TestCase


# Test items: (name, payload). Key = name.
def _name_key(item: tuple[str, Any]) -> str:
    return item[0]


class EmptyInputsTest(TestCase):
    def test_both_empty(self) -> None:
        result = pair_by_nk([], [], _name_key)
        self.assertEqual(result, Pairing(pairs=[], scrape_only=[], db_only=[]))

    def test_scrape_empty_db_has(self) -> None:
        result = pair_by_nk([], [("a", 1)], _name_key)
        self.assertEqual(result.pairs, [])
        self.assertEqual(result.scrape_only, [])
        self.assertEqual(result.db_only, [("a", 1)])

    def test_db_empty_scrape_has(self) -> None:
        result = pair_by_nk([("a", 1)], [], _name_key)
        self.assertEqual(result.pairs, [])
        self.assertEqual(result.scrape_only, [("a", 1)])
        self.assertEqual(result.db_only, [])


class FullPairingTest(TestCase):
    def test_all_keys_match(self) -> None:
        scrape = [("a", "s_a"), ("b", "s_b")]
        db = [("a", "d_a"), ("b", "d_b")]
        result = pair_by_nk(scrape, db, _name_key)
        self.assertEqual(
            sorted(result.pairs),
            sorted([(("a", "s_a"), ("a", "d_a")), (("b", "s_b"), ("b", "d_b"))]),
        )
        self.assertEqual(result.scrape_only, [])
        self.assertEqual(result.db_only, [])

    def test_partial_overlap(self) -> None:
        scrape = [("a", "s_a"), ("c", "s_c")]
        db = [("a", "d_a"), ("b", "d_b")]
        result = pair_by_nk(scrape, db, _name_key)
        self.assertEqual(result.pairs, [(("a", "s_a"), ("a", "d_a"))])
        self.assertEqual(result.scrape_only, [("c", "s_c")])
        self.assertEqual(result.db_only, [("b", "d_b")])

    def test_disjoint(self) -> None:
        scrape = [("a", 1), ("b", 2)]
        db = [("c", 3), ("d", 4)]
        result = pair_by_nk(scrape, db, _name_key)
        self.assertEqual(result.pairs, [])
        self.assertEqual(result.scrape_only, scrape)
        self.assertEqual(result.db_only, db)


class OrderPreservationTest(TestCase):
    def test_pairs_in_scrape_iteration_order(self) -> None:
        scrape = [("c", 1), ("a", 2), ("b", 3)]
        db = [("a", 10), ("b", 20), ("c", 30)]
        result = pair_by_nk(scrape, db, _name_key)
        # Pairs should follow scrape order.
        scrape_keys_in_pairs = [s[0] for s, _ in result.pairs]
        self.assertEqual(scrape_keys_in_pairs, ["c", "a", "b"])

    def test_scrape_only_preserves_scrape_order(self) -> None:
        scrape = [("z", 1), ("y", 2), ("x", 3)]
        result = pair_by_nk(scrape, [], _name_key)
        self.assertEqual(
            [s[0] for s in result.scrape_only], ["z", "y", "x"]
        )

    def test_db_only_preserves_db_order(self) -> None:
        db = [("z", 1), ("y", 2), ("x", 3)]
        result = pair_by_nk([], db, _name_key)
        self.assertEqual([d[0] for d in result.db_only], ["z", "y", "x"])


class DuplicateRejectionTest(TestCase):
    def test_duplicate_scrape_keys_raises(self) -> None:
        scrape = [("a", 1), ("a", 2)]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            pair_by_nk(scrape, [], _name_key)

    def test_duplicate_db_keys_raises(self) -> None:
        db = [("a", 1), ("a", 2)]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            pair_by_nk([], db, _name_key)


class CompositeKeyTest(TestCase):
    def test_tuple_keys_work(self) -> None:
        scrape = [("2024-01-01", "motion", "x"), ("2024-01-02", "order", "y")]
        db = [("2024-01-01", "motion", "X"), ("2024-01-03", "order", "Z")]
        result = pair_by_nk(scrape, db, key_fn=lambda i: (i[0], i[1]))
        self.assertEqual(
            result.pairs,
            [(
                ("2024-01-01", "motion", "x"),
                ("2024-01-01", "motion", "X"),
            )],
        )
        self.assertEqual(
            result.scrape_only, [("2024-01-02", "order", "y")]
        )
        self.assertEqual(
            result.db_only, [("2024-01-03", "order", "Z")]
        )


class PairingPropertyTest(TestCase):
    @given(
        scrape_keys=st.lists(
            st.integers(min_value=0, max_value=20), unique=True, max_size=10
        ),
        db_keys=st.lists(
            st.integers(min_value=0, max_value=20), unique=True, max_size=10
        ),
    )
    def test_lengths_sum_correctly(
        self, scrape_keys: list[int], db_keys: list[int]
    ) -> None:
        scrape = [(k, f"s{k}") for k in scrape_keys]
        db = [(k, f"d{k}") for k in db_keys]
        result = pair_by_nk(scrape, db, _name_key)
        self.assertEqual(
            len(result.pairs) + len(result.scrape_only), len(scrape)
        )
        self.assertEqual(
            len(result.pairs) + len(result.db_only), len(db)
        )

    @given(
        scrape_keys=st.lists(
            st.integers(min_value=0, max_value=20), unique=True, max_size=10
        ),
        db_keys=st.lists(
            st.integers(min_value=0, max_value=20), unique=True, max_size=10
        ),
    )
    def test_all_pair_keys_match(
        self, scrape_keys: list[int], db_keys: list[int]
    ) -> None:
        scrape = [(k, f"s{k}") for k in scrape_keys]
        db = [(k, f"d{k}") for k in db_keys]
        result = pair_by_nk(scrape, db, _name_key)
        for s, d in result.pairs:
            self.assertEqual(_name_key(s), _name_key(d))

    @given(
        scrape_keys=st.lists(
            st.integers(min_value=0, max_value=20), unique=True, max_size=10
        ),
        db_keys=st.lists(
            st.integers(min_value=0, max_value=20), unique=True, max_size=10
        ),
    )
    def test_pairs_equals_intersection(
        self, scrape_keys: list[int], db_keys: list[int]
    ) -> None:
        scrape = [(k, f"s{k}") for k in scrape_keys]
        db = [(k, f"d{k}") for k in db_keys]
        result = pair_by_nk(scrape, db, _name_key)
        pair_keys = {_name_key(s) for s, _ in result.pairs}
        self.assertEqual(pair_keys, set(scrape_keys) & set(db_keys))

    @given(
        scrape_keys=st.lists(
            st.integers(min_value=0, max_value=20), unique=True, max_size=10
        ),
        db_keys=st.lists(
            st.integers(min_value=0, max_value=20), unique=True, max_size=10
        ),
    )
    def test_pairing_is_complete_partition(
        self, scrape_keys: list[int], db_keys: list[int]
    ) -> None:
        """Every scrape item is in pairs or scrape_only (not both, not
        neither). Same for db."""
        scrape = [(k, f"s{k}") for k in scrape_keys]
        db = [(k, f"d{k}") for k in db_keys]
        result = pair_by_nk(scrape, db, _name_key)

        in_pairs_scrape = {_name_key(s) for s, _ in result.pairs}
        in_scrape_only = {_name_key(s) for s in result.scrape_only}
        self.assertEqual(in_pairs_scrape | in_scrape_only, set(scrape_keys))
        self.assertEqual(in_pairs_scrape & in_scrape_only, set())

        in_pairs_db = {_name_key(d) for _, d in result.pairs}
        in_db_only = {_name_key(d) for d in result.db_only}
        self.assertEqual(in_pairs_db | in_db_only, set(db_keys))
        self.assertEqual(in_pairs_db & in_db_only, set())
