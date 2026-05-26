"""Tests for MergeOutcome.

MergeOutcome is the return value of a merge. It records:
- root: the resolved Django root instance (for single-merge outcomes).
- creates/updates/deletes: per-model sets of PKs that changed.
- follow_ups: ordered list of post-commit callables.

`|` composition lets a batch caller accumulate outcomes:
- creates/updates/deletes: per-model set union (commutative).
- follow_ups: list concatenation (order-preserving).
- root: prefer left's; fall through to right's if left is None.

For tests we use plain empty classes as "model" stand-ins to avoid pulling
Django into L0 tests.
"""

from hypothesis import given
from hypothesis import strategies as st

from cl.scrapers.mergers.follow_up import FollowUp
from cl.scrapers.mergers.outcome import MergeOutcome
from cl.tests.cases import SimpleTestCase as TestCase


# Fake "Django models" — any class will do as a dict key for these tests.
class _M1:
    pass


class _M2:
    pass


def _noop() -> None:
    pass


class MergeOutcomeConstructionTest(TestCase):
    def test_empty_defaults(self) -> None:
        oc: MergeOutcome[object] = MergeOutcome()
        self.assertIsNone(oc.root)
        self.assertEqual(oc.creates, {})
        self.assertEqual(oc.updates, {})
        self.assertEqual(oc.deletes, {})
        self.assertEqual(oc.follow_ups, [])

    def test_full_construction(self) -> None:
        root = object()
        fu = FollowUp(name="x", fn=_noop)
        oc: MergeOutcome[object] = MergeOutcome(
            root=root,
            creates={_M1: {1, 2}, _M2: {3}},
            updates={_M1: {4}},
            deletes={_M2: {5}},
            follow_ups=[fu],
        )
        self.assertIs(oc.root, root)
        self.assertEqual(oc.creates, {_M1: {1, 2}, _M2: {3}})
        self.assertEqual(oc.follow_ups, [fu])

    def test_default_dict_and_list_factories_are_independent(self) -> None:
        # Frozen dataclass with mutable defaults must use field(default_factory=...)
        # so two instances don't share state.
        a: MergeOutcome[object] = MergeOutcome()
        b: MergeOutcome[object] = MergeOutcome()
        a.creates.setdefault(_M1, set()).add(1)
        self.assertEqual(b.creates, {})


class MergeOutcomeOrIdentityTest(TestCase):
    def test_empty_or_x_equals_x(self) -> None:
        x: MergeOutcome[object] = MergeOutcome(
            root="r", creates={_M1: {1}}, follow_ups=[FollowUp("fu", _noop)]
        )
        self.assertEqual(MergeOutcome() | x, x)

    def test_x_or_empty_equals_x(self) -> None:
        x: MergeOutcome[object] = MergeOutcome(
            root="r", creates={_M1: {1}}, follow_ups=[FollowUp("fu", _noop)]
        )
        self.assertEqual(x | MergeOutcome(), x)


class MergeOutcomeOrCompositionTest(TestCase):
    def test_or_unions_creates_for_same_model(self) -> None:
        a: MergeOutcome[object] = MergeOutcome(creates={_M1: {1, 2}})
        b: MergeOutcome[object] = MergeOutcome(creates={_M1: {2, 3}})
        c = a | b
        self.assertEqual(c.creates, {_M1: {1, 2, 3}})

    def test_or_unions_creates_across_models(self) -> None:
        a: MergeOutcome[object] = MergeOutcome(creates={_M1: {1}})
        b: MergeOutcome[object] = MergeOutcome(creates={_M2: {2}})
        c = a | b
        self.assertEqual(c.creates, {_M1: {1}, _M2: {2}})

    def test_or_unions_updates_and_deletes_too(self) -> None:
        a: MergeOutcome[object] = MergeOutcome(
            updates={_M1: {10}}, deletes={_M2: {20}}
        )
        b: MergeOutcome[object] = MergeOutcome(
            updates={_M1: {11}}, deletes={_M2: {21}}
        )
        c = a | b
        self.assertEqual(c.updates, {_M1: {10, 11}})
        self.assertEqual(c.deletes, {_M2: {20, 21}})

    def test_or_concatenates_follow_ups_preserving_order(self) -> None:
        fu1 = FollowUp(name="1", fn=_noop)
        fu2 = FollowUp(name="2", fn=_noop)
        fu3 = FollowUp(name="3", fn=_noop)
        a: MergeOutcome[object] = MergeOutcome(follow_ups=[fu1, fu2])
        b: MergeOutcome[object] = MergeOutcome(follow_ups=[fu3])
        self.assertEqual((a | b).follow_ups, [fu1, fu2, fu3])
        self.assertEqual((b | a).follow_ups, [fu3, fu1, fu2])

    def test_or_prefers_left_root(self) -> None:
        a: MergeOutcome[str] = MergeOutcome(root="a-root")
        b: MergeOutcome[str] = MergeOutcome(root="b-root")
        self.assertEqual((a | b).root, "a-root")

    def test_or_falls_through_to_right_root_when_left_is_none(self) -> None:
        a: MergeOutcome[str] = MergeOutcome()
        b: MergeOutcome[str] = MergeOutcome(root="b-root")
        self.assertEqual((a | b).root, "b-root")

    def test_or_does_not_mutate_operands(self) -> None:
        a: MergeOutcome[object] = MergeOutcome(creates={_M1: {1}})
        b: MergeOutcome[object] = MergeOutcome(creates={_M1: {2}})
        _ = a | b
        self.assertEqual(a.creates, {_M1: {1}})
        self.assertEqual(b.creates, {_M1: {2}})


class MergeOutcomeOrPropertyTest(TestCase):
    """Property-based tests for | algebra."""

    # Use str keys + int PKs to keep hypothesis-generated outcomes simple.
    _outcome_strategy = st.builds(
        MergeOutcome,
        creates=st.dictionaries(
            st.sampled_from(["A", "B", "C"]),
            st.sets(st.integers(min_value=0, max_value=20), max_size=5),
            max_size=3,
        ),
        updates=st.dictionaries(
            st.sampled_from(["A", "B", "C"]),
            st.sets(st.integers(min_value=0, max_value=20), max_size=5),
            max_size=3,
        ),
        deletes=st.dictionaries(
            st.sampled_from(["A", "B", "C"]),
            st.sets(st.integers(min_value=0, max_value=20), max_size=5),
            max_size=3,
        ),
        follow_ups=st.lists(
            st.builds(FollowUp, name=st.text(min_size=1, max_size=5), fn=st.just(_noop)),
            max_size=5,
        ),
    )

    @given(a=_outcome_strategy, b=_outcome_strategy, c=_outcome_strategy)
    def test_or_is_associative(
        self,
        a: MergeOutcome[object],
        b: MergeOutcome[object],
        c: MergeOutcome[object],
    ) -> None:
        self.assertEqual((a | b) | c, a | (b | c))

    @given(a=_outcome_strategy)
    def test_empty_is_identity(self, a: MergeOutcome[object]) -> None:
        empty: MergeOutcome[object] = MergeOutcome()
        self.assertEqual(empty | a, a)
        self.assertEqual(a | empty, a)

    @given(a=_outcome_strategy, b=_outcome_strategy)
    def test_creates_is_commutative_under_or(
        self,
        a: MergeOutcome[object],
        b: MergeOutcome[object],
    ) -> None:
        # creates/updates/deletes use set union → commutative.
        self.assertEqual((a | b).creates, (b | a).creates)
        self.assertEqual((a | b).updates, (b | a).updates)
        self.assertEqual((a | b).deletes, (b | a).deletes)
