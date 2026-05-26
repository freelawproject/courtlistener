"""Tests for L3a: Node base class hierarchy + class-kwarg capture.

The framework exposes four kinds of tree nodes:
- Node — common base (abstract)
- Aggregate[ModelT] — the root
- InternalNode[ModelT] — lifecycle-owned child
- ExternalNodeRef[ModelT] — independent-lifecycle external row, looked up

User schemas subclass one of the latter three and bind a Django model via
the generic parameter. Schemas must declare ``natural_key``; the framework
validates this automatically at class-definition time (see L3d). Most
fixtures here use a trivial ``natural_key = ("x",)`` because they're
exercising hierarchy / kwarg behavior, not NK semantics.
"""

from pydantic import BaseModel

from cl.scrapers.mergers.nodes import (
    Aggregate,
    CreateIfMissing,
    ErrorIfMissing,
    InternalNode,
    ExternalNodeRef,
    Node,
    NoopIfMissing,
    bound_django_model,
)
from cl.scrapers.mergers.strategies import (
    DBWins,
    ScrapeClobbers,
    ScrapeWins,
    ScrapeWinsIfPresent,
    Union,
)
from cl.tests.cases import SimpleTestCase as TestCase


# Fake "Django models" for testing.
class _Docket:
    pass


class _DocketEntry:
    pass


class _Party:
    pass


class HierarchyTest(TestCase):
    def test_node_is_basemodel(self) -> None:
        self.assertTrue(issubclass(Node, BaseModel))

    def test_node_subclasses(self) -> None:
        self.assertTrue(issubclass(Aggregate, Node))
        self.assertTrue(issubclass(InternalNode, Node))
        self.assertTrue(issubclass(ExternalNodeRef, Node))

    def test_subclasses_are_distinct(self) -> None:
        self.assertFalse(issubclass(Aggregate, InternalNode))
        self.assertFalse(issubclass(InternalNode, Aggregate))
        self.assertFalse(issubclass(ExternalNodeRef, Aggregate))


class BoundDjangoModelTest(TestCase):
    def test_aggregate_binds_django_model(self) -> None:
        class MyDocket(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int

        self.assertIs(bound_django_model(MyDocket), _Docket)

    def test_internal_node_binds_django_model(self) -> None:
        class MyEntry(InternalNode[_DocketEntry]):
            natural_key = ("x",)
            x: int

        self.assertIs(bound_django_model(MyEntry), _DocketEntry)

    def test_lookup_ref_binds_django_model(self) -> None:
        class MyPartyRef(ExternalNodeRef[_Party]):
            natural_key = ("name",)
            name: str

        self.assertIs(bound_django_model(MyPartyRef), _Party)

    def test_unbound_returns_none(self) -> None:
        """If someone subclasses without binding (rare), return None
        rather than raising — there's no Django model to validate
        against."""

        class Unbound(InternalNode):  # type: ignore[type-arg]
            x: int

        self.assertIsNone(bound_django_model(Unbound))


class AggregateKwargsTest(TestCase):
    def test_default_field_default_is_scrape_wins(self) -> None:
        class A(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int

        self.assertIs(A._mergers_default_field, ScrapeWins)

    def test_default_collection_default_is_scrape_clobbers(self) -> None:
        class A(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int

        self.assertIs(A._mergers_default_collection, ScrapeClobbers)

    def test_lock_for_update_default_is_false(self) -> None:
        class A(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int

        self.assertFalse(A._mergers_lock_for_update)

    def test_override_default_field(self) -> None:
        class A(Aggregate[_Docket], default_field=ScrapeWinsIfPresent):
            natural_key = ("x",)
            x: int

        self.assertIs(A._mergers_default_field, ScrapeWinsIfPresent)

    def test_override_lock_for_update(self) -> None:
        class A(Aggregate[_Docket], lock_for_update=True):
            natural_key = ("x",)
            x: int

        self.assertTrue(A._mergers_lock_for_update)

    def test_all_kwargs_together(self) -> None:
        class A(
            Aggregate[_Docket],
            default_field=ScrapeWinsIfPresent,
            default_collection=Union,
            lock_for_update=True,
        ):
            natural_key = ("x",)
            x: int

        self.assertIs(A._mergers_default_field, ScrapeWinsIfPresent)
        self.assertIs(A._mergers_default_collection, Union)
        self.assertTrue(A._mergers_lock_for_update)


class InternalNodeKwargsTest(TestCase):
    def test_defaults_match_aggregate(self) -> None:
        class N(InternalNode[_DocketEntry]):
            natural_key = ("x",)
            x: int

        self.assertIs(N._mergers_default_field, ScrapeWins)
        self.assertIs(N._mergers_default_collection, ScrapeClobbers)
        self.assertFalse(N._mergers_allow_duplicates)

    def test_allow_duplicates_override(self) -> None:
        class N(InternalNode[_DocketEntry], allow_duplicates=True):
            natural_key = ("x",)
            x: int

        self.assertTrue(N._mergers_allow_duplicates)


class ExternalNodeRefKwargsTest(TestCase):
    def test_defaults_are_dbwins_union_create_if_missing(self) -> None:
        class R(ExternalNodeRef[_Party]):
            natural_key = ("name",)
            name: str

        self.assertIs(R._mergers_default_field, DBWins)
        self.assertIs(R._mergers_default_collection, Union)
        self.assertEqual(R._mergers_absence_policy, CreateIfMissing)
        self.assertFalse(R._mergers_allow_duplicates)

    def test_absence_policy_error_if_missing(self) -> None:
        class R(ExternalNodeRef[_Party], absence_policy=ErrorIfMissing):
            natural_key = ("name",)
            name: str

        self.assertEqual(R._mergers_absence_policy, ErrorIfMissing)

    def test_absence_policy_noop(self) -> None:
        class R(ExternalNodeRef[_Party], absence_policy=NoopIfMissing):
            natural_key = ("name",)
            name: str

        self.assertEqual(R._mergers_absence_policy, NoopIfMissing)

    def test_lookup_ref_default_field_can_be_overridden(self) -> None:
        """AuthoritativeParty pattern: flip default to ScrapeWins."""

        class AuthoritativeParty(ExternalNodeRef[_Party], default_field=ScrapeWins):
            natural_key = ("name",)
            name: str

        self.assertIs(AuthoritativeParty._mergers_default_field, ScrapeWins)


class PydanticIntegrationTest(TestCase):
    """Sanity: Pydantic still constructs and validates instances."""

    def test_instance_construction(self) -> None:
        class A(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            name: str

        a = A(x=1, name="foo")
        self.assertEqual(a.x, 1)
        self.assertEqual(a.name, "foo")

    def test_validation_still_runs(self) -> None:
        from pydantic import ValidationError

        class A(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int

        with self.assertRaises(ValidationError):
            A(x="not-an-int")  # type: ignore[arg-type]


class KwargIsolationTest(TestCase):
    """Sibling subclasses don't share kwarg state — class attrs are
    captured per class."""

    def test_two_subclasses_dont_share_kwargs(self) -> None:
        class A(Aggregate[_Docket], lock_for_update=True):
            natural_key = ("x",)
            x: int

        class B(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int

        self.assertTrue(A._mergers_lock_for_update)
        self.assertFalse(B._mergers_lock_for_update)

    def test_grandchild_inherits_kwarg(self) -> None:
        class Parent(Aggregate[_Docket], lock_for_update=True):
            natural_key = ("x",)
            x: int

        class Child(Parent):
            y: int

        # Child should inherit Parent's setting (no override).
        self.assertTrue(Child._mergers_lock_for_update)

    def test_grandchild_can_override(self) -> None:
        class Parent(Aggregate[_Docket], lock_for_update=True):
            natural_key = ("x",)
            x: int

        class Child(Parent, lock_for_update=False):
            y: int

        self.assertFalse(Child._mergers_lock_for_update)
