"""Tests for ``pair_by_nk_allowing_duplicates``.

When a node declares ``allow_duplicates=True``, multiple scrape items and
multiple DB items may share the same NK. The framework pairs them by
minimum total edit cost across the bucket — a small bipartite assignment
problem.

The caller supplies an ``edit_cost_fn(scrape_item, db_item) -> int`` that
returns the number of field changes required to make the DB row match
the scrape row (or any consistent non-negative cost). The pairing picks
the matching with the lowest total cost; unmatched items (when bucket
sizes differ) go to ``scrape_only`` / ``db_only``.

Each NK bucket is handled independently — items with different NKs never
mix.
"""

from itertools import combinations, permutations
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cl.scrapers.mergers.ops import Pairing
from cl.scrapers.mergers.reconcile import pair_by_nk_allowing_duplicates
from cl.tests.cases import SimpleTestCase as TestCase


# Test fixtures: items are (name, extras). Key = name.
def _name_key(item: tuple[str, Any]) -> str:
    return item[0]


def _extras_diff_cost(s: tuple[str, Any], d: tuple[str, Any]) -> int:
    """Cost = 0 if extras match, 1 otherwise."""
    return 0 if s[1] == d[1] else 1


class EmptyInputsTest(TestCase):
    def test_both_empty(self) -> None:
        result = pair_by_nk_allowing_duplicates(
            [], [], _name_key, _extras_diff_cost
        )
        self.assertEqual(result, Pairing())

    def test_scrape_empty_db_populated(self) -> None:
        db = [("a", 1), ("a", 2)]
        result = pair_by_nk_allowing_duplicates(
            [], db, _name_key, _extras_diff_cost
        )
        self.assertEqual(result.pairs, [])
        self.assertEqual(result.scrape_only, [])
        self.assertEqual(result.db_only, db)


class NoDuplicatesActualTest(TestCase):
    """When there are no actual duplicates, behavior matches the strict
    pair_by_nk."""

    def test_simple_one_to_one(self) -> None:
        scrape = [("a", "X"), ("b", "Y")]
        db = [("a", "X"), ("b", "Z")]
        result = pair_by_nk_allowing_duplicates(
            scrape, db, _name_key, _extras_diff_cost
        )
        self.assertEqual(
            sorted(result.pairs),
            sorted([(("a", "X"), ("a", "X")), (("b", "Y"), ("b", "Z"))]),
        )
        self.assertEqual(result.scrape_only, [])
        self.assertEqual(result.db_only, [])


class SingleBucketAssignmentTest(TestCase):
    def test_two_by_two_lowest_cost_wins(self) -> None:
        # All same NK ("john"). Match by extras to minimize cost.
        # Optimal: ("john", "A") <-> ("john", "A"); ("john", "B") <-> ("john", "B").
        scrape = [("john", "A"), ("john", "B")]
        db = [("john", "B"), ("john", "A")]
        result = pair_by_nk_allowing_duplicates(
            scrape, db, _name_key, _extras_diff_cost
        )
        self.assertEqual(
            set(result.pairs),
            {(("john", "A"), ("john", "A")), (("john", "B"), ("john", "B"))},
        )
        self.assertEqual(result.scrape_only, [])
        self.assertEqual(result.db_only, [])

    def test_three_by_three_partial_match(self) -> None:
        scrape = [("john", "A"), ("john", "B"), ("john", "C")]
        db = [("john", "X"), ("john", "B"), ("john", "Y")]
        # Optimal: B <-> B (cost 0), A <-> X or Y (cost 1), C <-> the other (cost 1).
        # Total cost: 2.
        result = pair_by_nk_allowing_duplicates(
            scrape, db, _name_key, _extras_diff_cost
        )
        self.assertEqual(len(result.pairs), 3)
        total_cost = sum(_extras_diff_cost(s, d) for s, d in result.pairs)
        self.assertEqual(total_cost, 2)
        # The exact B <-> B pair must be present.
        self.assertIn((("john", "B"), ("john", "B")), result.pairs)

    def test_scrape_larger_than_db(self) -> None:
        scrape = [("john", "A"), ("john", "B"), ("john", "C")]
        db = [("john", "B")]
        result = pair_by_nk_allowing_duplicates(
            scrape, db, _name_key, _extras_diff_cost
        )
        # Best match: ("john", "B") <-> ("john", "B"); other two scrape go to scrape_only.
        self.assertEqual(result.pairs, [(("john", "B"), ("john", "B"))])
        self.assertEqual(
            set(result.scrape_only), {("john", "A"), ("john", "C")}
        )
        self.assertEqual(result.db_only, [])

    def test_db_larger_than_scrape(self) -> None:
        scrape = [("john", "B")]
        db = [("john", "A"), ("john", "B"), ("john", "C")]
        result = pair_by_nk_allowing_duplicates(
            scrape, db, _name_key, _extras_diff_cost
        )
        self.assertEqual(result.pairs, [(("john", "B"), ("john", "B"))])
        self.assertEqual(result.scrape_only, [])
        self.assertEqual(
            set(result.db_only), {("john", "A"), ("john", "C")}
        )


class MultipleBucketsTest(TestCase):
    def test_buckets_are_independent(self) -> None:
        scrape = [
            ("alice", "A"),
            ("alice", "B"),
            ("bob", "X"),
        ]
        db = [
            ("alice", "A"),
            ("bob", "X"),
            ("bob", "Y"),  # extra "bob" — should go to db_only
        ]
        result = pair_by_nk_allowing_duplicates(
            scrape, db, _name_key, _extras_diff_cost
        )
        # alice: 2 vs 1 -> pair the matching A
        # bob: 1 vs 2 -> pair X with X, leave Y
        self.assertIn((("alice", "A"), ("alice", "A")), result.pairs)
        self.assertIn((("bob", "X"), ("bob", "X")), result.pairs)
        self.assertEqual(len(result.pairs), 2)
        self.assertEqual(result.scrape_only, [("alice", "B")])
        self.assertEqual(result.db_only, [("bob", "Y")])

    def test_disjoint_nks_are_only(self) -> None:
        scrape = [("a", 1), ("a", 2)]
        db = [("b", 3), ("b", 4)]
        result = pair_by_nk_allowing_duplicates(
            scrape, db, _name_key, _extras_diff_cost
        )
        self.assertEqual(result.pairs, [])
        self.assertEqual(set(result.scrape_only), set(scrape))
        self.assertEqual(set(result.db_only), set(db))


class CostFnInvocationTest(TestCase):
    def test_cost_fn_called_with_scrape_then_db(self) -> None:
        received: list[tuple[Any, Any]] = []

        def cost(s: Any, d: Any) -> int:
            received.append((s, d))
            return 0

        scrape = [("john", "S1")]
        db = [("john", "D1")]
        pair_by_nk_allowing_duplicates(scrape, db, _name_key, cost)
        self.assertIn((("john", "S1"), ("john", "D1")), received)


def _brute_force_min_cost(
    scrape: list[Any], db: list[Any], cost_fn: Any
) -> int:
    """Reference implementation to compare against."""
    n, m = len(scrape), len(db)
    k = min(n, m)
    if k == 0:
        return 0
    best = None
    for s_idx in combinations(range(n), k):
        for d_perm in permutations(range(m), k):
            c = sum(
                cost_fn(scrape[s_idx[i]], db[d_perm[i]])
                for i in range(k)
            )
            if best is None or c < best:
                best = c
    return best or 0


class AssignmentMinimalityPropertyTest(TestCase):
    """Verify the returned pairing has the minimum possible total cost."""

    @given(
        scrape_extras=st.lists(
            st.integers(min_value=0, max_value=5), min_size=1, max_size=4
        ),
        db_extras=st.lists(
            st.integers(min_value=0, max_value=5), min_size=1, max_size=4
        ),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_single_bucket_returns_min_cost(
        self, scrape_extras: list[int], db_extras: list[int]
    ) -> None:
        scrape = [("k", x) for x in scrape_extras]
        db = [("k", x) for x in db_extras]
        result = pair_by_nk_allowing_duplicates(
            scrape, db, _name_key, _extras_diff_cost
        )
        actual_cost = sum(
            _extras_diff_cost(s, d) for s, d in result.pairs
        )
        expected_min = _brute_force_min_cost(scrape, db, _extras_diff_cost)
        self.assertEqual(actual_cost, expected_min)

    @given(
        scrape_extras=st.lists(
            st.integers(min_value=0, max_value=5), max_size=4
        ),
        db_extras=st.lists(
            st.integers(min_value=0, max_value=5), max_size=4
        ),
    )
    def test_pair_count_equals_min_bucket_size(
        self, scrape_extras: list[int], db_extras: list[int]
    ) -> None:
        scrape = [("k", x) for x in scrape_extras]
        db = [("k", x) for x in db_extras]
        result = pair_by_nk_allowing_duplicates(
            scrape, db, _name_key, _extras_diff_cost
        )
        self.assertEqual(
            len(result.pairs), min(len(scrape), len(db))
        )


class CompletePartitionPropertyTest(TestCase):
    """Every input item must appear exactly once in the output."""

    @given(
        scrape=st.lists(
            st.tuples(
                st.sampled_from(["a", "b", "c"]),
                st.integers(min_value=0, max_value=3),
            ),
            max_size=6,
        ),
        db=st.lists(
            st.tuples(
                st.sampled_from(["a", "b", "c"]),
                st.integers(min_value=0, max_value=3),
            ),
            max_size=6,
        ),
    )
    def test_each_scrape_item_appears_once(
        self,
        scrape: list[tuple[str, int]],
        db: list[tuple[str, int]],
    ) -> None:
        result = pair_by_nk_allowing_duplicates(
            scrape, db, _name_key, _extras_diff_cost
        )
        # Track by identity (id()) so duplicate values are still distinct
        from_pairs = [id(s) for s, _ in result.pairs]
        from_only = [id(s) for s in result.scrape_only]
        all_seen = from_pairs + from_only
        self.assertEqual(sorted(all_seen), sorted(id(s) for s in scrape))

    @given(
        scrape=st.lists(
            st.tuples(
                st.sampled_from(["a", "b", "c"]),
                st.integers(min_value=0, max_value=3),
            ),
            max_size=6,
        ),
        db=st.lists(
            st.tuples(
                st.sampled_from(["a", "b", "c"]),
                st.integers(min_value=0, max_value=3),
            ),
            max_size=6,
        ),
    )
    def test_each_db_item_appears_once(
        self,
        scrape: list[tuple[str, int]],
        db: list[tuple[str, int]],
    ) -> None:
        result = pair_by_nk_allowing_duplicates(
            scrape, db, _name_key, _extras_diff_cost
        )
        from_pairs = [id(d) for _, d in result.pairs]
        from_only = [id(d) for d in result.db_only]
        all_seen = from_pairs + from_only
        self.assertEqual(sorted(all_seen), sorted(id(d) for d in db))
