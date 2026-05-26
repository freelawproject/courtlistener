"""Tests for FollowUp.

FollowUp is a callable record of post-commit work that lifecycle hooks
return. The framework collects them; the caller dispatches them with
transaction.on_commit (or however it sees fit).

Contract:
- Frozen dataclass holding (name, fn, args, kwargs, tags).
- Calling it delegates to fn(*args, **kwargs).
- Two instances with the same fields compare equal (kwargs is a mutable
  dict so hashability isn't required; callers that want to dedupe can
  compare via ==).
"""

import dataclasses
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from cl.scrapers.mergers.follow_up import FollowUp
from cl.tests.cases import SimpleTestCase as TestCase


class FollowUpConstructionTest(TestCase):
    def test_minimal_construction(self) -> None:
        fu = FollowUp(name="noop", fn=lambda: None)
        self.assertEqual(fu.name, "noop")
        self.assertEqual(fu.args, ())
        self.assertEqual(fu.kwargs, {})
        self.assertEqual(fu.tags, frozenset())

    def test_full_construction(self) -> None:
        def f(x: int, y: int = 0) -> int:
            return x + y

        fu = FollowUp(
            name="add",
            fn=f,
            args=(1,),
            kwargs={"y": 2},
            tags=frozenset({"math"}),
        )
        self.assertEqual(fu.args, (1,))
        self.assertEqual(fu.kwargs, {"y": 2})
        self.assertEqual(fu.tags, frozenset({"math"}))

    def test_is_frozen(self) -> None:
        fu = FollowUp(name="x", fn=lambda: None)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            fu.name = "y"  # type: ignore[misc]


class FollowUpInvocationTest(TestCase):
    def test_call_with_no_args(self) -> None:
        called = []
        fu = FollowUp(name="x", fn=lambda: called.append(1))
        fu()
        self.assertEqual(called, [1])

    def test_call_delegates_args_and_kwargs(self) -> None:
        received: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        def capture(*a: Any, **k: Any) -> None:
            received.append((a, k))

        fu = FollowUp(
            name="x", fn=capture, args=(1, 2, 3), kwargs={"k": "v"}
        )
        fu()
        self.assertEqual(received, [((1, 2, 3), {"k": "v"})])

    def test_call_returns_fn_result(self) -> None:
        fu = FollowUp(name="x", fn=lambda a, b: a * b, args=(3, 4))
        self.assertEqual(fu(), 12)


class FollowUpEqualityTest(TestCase):
    def test_equal_when_all_fields_match(self) -> None:
        fn = lambda: None  # noqa: E731 — comparable identity
        a = FollowUp(name="x", fn=fn, args=(1,), kwargs={"k": 2})
        b = FollowUp(name="x", fn=fn, args=(1,), kwargs={"k": 2})
        self.assertEqual(a, b)

    def test_unequal_when_name_differs(self) -> None:
        fn = lambda: None  # noqa: E731
        self.assertNotEqual(
            FollowUp(name="x", fn=fn),
            FollowUp(name="y", fn=fn),
        )



class FollowUpPropertyTest(TestCase):
    @given(
        name=st.text(min_size=1, max_size=20),
        args=st.tuples(st.integers(), st.integers()),
        kwargs=st.dictionaries(
            st.text(min_size=1, max_size=5), st.integers(), max_size=3
        ),
    )
    def test_call_always_delegates(
        self,
        name: str,
        args: tuple[int, int],
        kwargs: dict[str, int],
    ) -> None:
        """For any fn/args/kwargs, calling a FollowUp produces the same
        result as calling fn directly."""
        received: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        def capture(*a: Any, **k: Any) -> int:
            received.append((a, k))
            return sum(a) + sum(k.values())

        fu = FollowUp(name=name, fn=capture, args=args, kwargs=kwargs)
        result = fu()

        expected_result = sum(args) + sum(kwargs.values())
        self.assertEqual(result, expected_result)
        self.assertEqual(received, [(args, kwargs)])
