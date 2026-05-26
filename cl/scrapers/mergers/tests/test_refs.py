"""Tests for PathRef and the ``parent`` sentinel descriptor.

PathRef records an attribute path symbolically at class-definition time so
that natural keys can reference parent/ancestor fields without those
fields being bound to values yet. The framework walks the path at phase 2
against concrete tree instances.

Contract:
- ``parent`` is a PathRef whose first part is ``"parent"``.
- Any attribute access on a PathRef returns a new PathRef with the
  accessed name appended to the path.
- ``path_parts(p)`` returns the tuple of names.
- ``resolve_path(obj, p)`` walks ``getattr(obj, name)`` for each name in
  ``path_parts(p)``.
- Two PathRefs with the same parts compare equal and hash the same.
"""

from types import SimpleNamespace

from hypothesis import given
from hypothesis import strategies as st

from cl.scrapers.mergers.refs import (
    PathRef,
    parent,
    path_parts,
    resolve_path,
)
from cl.tests.cases import SimpleTestCase as TestCase


class ParentSentinelTest(TestCase):
    def test_parent_is_pathref(self) -> None:
        self.assertIsInstance(parent, PathRef)

    def test_parent_parts(self) -> None:
        self.assertEqual(path_parts(parent), ("parent",))

    def test_attribute_access_appends_part(self) -> None:
        self.assertEqual(path_parts(parent.docket), ("parent", "docket"))

    def test_chain_traversal(self) -> None:
        self.assertEqual(
            path_parts(parent.parent.field),
            ("parent", "parent", "field"),
        )

    def test_deep_chain(self) -> None:
        self.assertEqual(
            path_parts(parent.parent.parent.parent.x),
            ("parent", "parent", "parent", "parent", "x"),
        )


class PathRefEqualityTest(TestCase):
    def test_equal_when_parts_match(self) -> None:
        self.assertEqual(parent.docket, parent.docket)

    def test_unequal_when_parts_differ(self) -> None:
        self.assertNotEqual(parent.docket, parent.party)

    def test_unequal_when_depths_differ(self) -> None:
        self.assertNotEqual(parent.docket, parent.parent.docket)

    def test_hashable(self) -> None:
        self.assertEqual({parent.docket, parent.docket}, {parent.docket})

    def test_repr_is_dotted(self) -> None:
        self.assertEqual(repr(parent.docket), "parent.docket")


class ResolvePathTest(TestCase):
    def test_single_level(self) -> None:
        parent_node = SimpleNamespace(docket="MY_DOCKET")
        self_node = SimpleNamespace(parent=parent_node)
        self.assertEqual(resolve_path(self_node, parent.docket), "MY_DOCKET")

    def test_multi_level(self) -> None:
        grandparent = SimpleNamespace(field="VAL")
        mid = SimpleNamespace(parent=grandparent)
        leaf = SimpleNamespace(parent=mid)
        self.assertEqual(resolve_path(leaf, parent.parent.field), "VAL")

    def test_raises_on_missing_attr(self) -> None:
        self_node = SimpleNamespace()  # no .parent
        with self.assertRaises(AttributeError):
            resolve_path(self_node, parent.docket)

    def test_returns_object_when_path_terminates_at_object(self) -> None:
        # The path can resolve to any value, not just a primitive.
        leaf_value = object()
        parent_node = SimpleNamespace(thing=leaf_value)
        self_node = SimpleNamespace(parent=parent_node)
        self.assertIs(resolve_path(self_node, parent.thing), leaf_value)


class PathRefDunderSafetyTest(TestCase):
    """Underscore-prefixed names must not become path parts.

    Otherwise things like pickling, copying, or accidentally referencing
    internal attributes would silently turn into PathRef extensions.
    """

    def test_underscore_attr_raises(self) -> None:
        with self.assertRaises(AttributeError):
            parent._private  # noqa: B018 — we want the raise

    def test_dunder_attr_raises(self) -> None:
        with self.assertRaises(AttributeError):
            parent.__some_internal__  # noqa: B018


class PathRefPropertyTest(TestCase):
    @given(
        attr_names=st.lists(
            st.from_regex(r"[a-z][a-z_]{0,8}", fullmatch=True),
            min_size=1,
            max_size=5,
        )
    )
    def test_path_parts_matches_chain(self, attr_names: list[str]) -> None:
        """For any chain of public attribute names, path_parts returns
        ``("parent", *attr_names)``."""
        p = parent
        for name in attr_names:
            p = getattr(p, name)
        self.assertEqual(path_parts(p), ("parent", *attr_names))

    @given(
        attr_names=st.lists(
            st.from_regex(r"[a-z][a-z_]{0,8}", fullmatch=True),
            min_size=1,
            max_size=4,
        )
    )
    def test_resolve_walks_attrs(self, attr_names: list[str]) -> None:
        """For any chain of attribute names, build an object hierarchy
        matching the chain and verify resolution returns the leaf."""
        # Build a chain of SimpleNamespaces representing the parent stack,
        # plus the final field value.
        sentinel = object()
        # The path is ("parent", *attr_names). The "parent" hop walks
        # self_node.parent, so we need parent_obj.<attr_names[0]>...
        # = sentinel.
        obj = sentinel
        # Construct backwards: innermost name is last
        for name in reversed(attr_names):
            obj = SimpleNamespace(**{name: obj})
        self_node = SimpleNamespace(parent=obj)
        p = parent
        for name in attr_names:
            p = getattr(p, name)
        self.assertIs(resolve_path(self_node, p), sentinel)
