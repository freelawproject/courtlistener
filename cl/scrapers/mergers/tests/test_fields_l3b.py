"""Tests for L3b: field descriptor extraction.

``extract_fields(cls)`` walks ``cls.model_fields`` (Pydantic v2) and
produces a list of typed descriptors per field. Each descriptor carries
the strategy that applies (from ``Annotated`` metadata or the class's
default). Variants:

- ``ScalarField`` — primitive scalars and PreResolvedRefs treated
  uniformly via ``preresolved_model`` distinguishing them.
- ``ChildField`` — a single child ``Node`` instance, possibly optional
  (treated as a 0-or-1 collection under the collection strategy).
- ``ChildListField`` — ``list[ChildNode]``.

Strategy resolution:
- If ``Annotated[..., Strategy]`` provides a strategy, use it.
- Otherwise use the class's ``_mergers_default_field`` or
  ``_mergers_default_collection``.
- Misapplying a strategy kind (scalar on a list, collection on a
  scalar) raises ``TypeError``.

Fixtures here declare ``natural_key`` even when they're not exercising
NK behavior, because schema validation runs at class-definition time.
"""

from typing import Annotated

from cl.scrapers.mergers.fields import (
    ChildField,
    ChildListField,
    ScalarField,
    extract_fields,
)
from cl.scrapers.mergers.nodes import (
    Aggregate,
    InternalNode,
    ExternalNodeRef,
    PreResolvedRef,
)
from cl.scrapers.mergers.strategies import (
    Custom,
    CustomCollection,
    DBClobbers,
    DBWins,
    ScrapeClobbers,
    ScrapeWins,
    ScrapeWinsIfPresent,
    Union,
)
from cl.tests.cases import SimpleTestCase as TestCase


# Fake Django models.
class _Docket:
    pass


class _Court:
    pass


class _Party:
    pass


# A small reusable child node for tests.
class _MyEntry(InternalNode[_Docket]):
    natural_key = ("note",)
    note: str = ""


class ScalarFieldTest(TestCase):
    def test_bare_int_uses_class_default(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int

        fields = extract_fields(N)
        self.assertEqual(len(fields), 1)
        f = fields[0]
        self.assertIsInstance(f, ScalarField)
        assert isinstance(f, ScalarField)
        self.assertEqual(f.name, "x")
        self.assertIs(f.strategy, ScrapeWins)
        self.assertFalse(f.is_optional)
        self.assertIsNone(f.preresolved_model)

    def test_explicit_scrape_wins_if_present(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: Annotated[int, ScrapeWinsIfPresent]

        f = extract_fields(N)[0]
        self.assertIsInstance(f, ScalarField)
        assert isinstance(f, ScalarField)
        self.assertIs(f.strategy, ScrapeWinsIfPresent)

    def test_custom_scalar_strategy(self) -> None:
        custom = Custom(lambda s, d: s)

        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: Annotated[int, custom]

        f = extract_fields(N)[0]
        assert isinstance(f, ScalarField)
        self.assertIs(f.strategy, custom)

    def test_optional_scalar(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int | None = None

        f = extract_fields(N)[0]
        assert isinstance(f, ScalarField)
        self.assertTrue(f.is_optional)

    def test_class_default_changes_via_kwarg(self) -> None:
        class N(Aggregate[_Docket], default_field=DBWins):
            natural_key = ("x",)
            x: int = 0  # default needed since DBWins doesn't write

        f = extract_fields(N)[0]
        assert isinstance(f, ScalarField)
        self.assertIs(f.strategy, DBWins)

    def test_lookup_ref_defaults_to_dbwins(self) -> None:
        class R(ExternalNodeRef[_Party]):
            natural_key = ("name",)
            name: str

        f = extract_fields(R)[0]
        assert isinstance(f, ScalarField)
        self.assertIs(f.strategy, DBWins)


class PreResolvedRefFieldTest(TestCase):
    def test_preresolved_ref(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("court",)
            court: PreResolvedRef[_Court]

        f = extract_fields(N)[0]
        self.assertIsInstance(f, ScalarField)
        assert isinstance(f, ScalarField)
        self.assertEqual(f.name, "court")
        self.assertIs(f.preresolved_model, _Court)
        self.assertFalse(f.is_optional)

    def test_optional_preresolved_ref(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("court",)
            court: PreResolvedRef[_Court] | None = None

        f = extract_fields(N)[0]
        assert isinstance(f, ScalarField)
        self.assertIs(f.preresolved_model, _Court)
        self.assertTrue(f.is_optional)

    def test_preresolved_ref_with_strategy_override(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("court",)
            court: Annotated[PreResolvedRef[_Court] | None, ScrapeWinsIfPresent] = (
                None
            )

        f = extract_fields(N)[0]
        assert isinstance(f, ScalarField)
        self.assertIs(f.preresolved_model, _Court)
        self.assertIs(f.strategy, ScrapeWinsIfPresent)


class ChildFieldTest(TestCase):
    def test_single_child(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            entry: _MyEntry | None = None  # use Optional to avoid mandatory init

        f = next(f for f in extract_fields(N) if f.name == "entry")
        self.assertIsInstance(f, ChildField)
        assert isinstance(f, ChildField)
        self.assertEqual(f.name, "entry")
        self.assertIs(f.child_class, _MyEntry)
        self.assertTrue(f.is_optional)
        self.assertIs(f.strategy, ScrapeClobbers)  # class default

    def test_required_single_child(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            entry: _MyEntry

        f = next(f for f in extract_fields(N) if f.name == "entry")
        assert isinstance(f, ChildField)
        self.assertFalse(f.is_optional)

    def test_optional_child(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            entry: _MyEntry | None = None

        f = next(f for f in extract_fields(N) if f.name == "entry")
        assert isinstance(f, ChildField)
        self.assertTrue(f.is_optional)

    def test_child_with_explicit_strategy(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            entry: Annotated[_MyEntry | None, Union] = None

        f = next(f for f in extract_fields(N) if f.name == "entry")
        assert isinstance(f, ChildField)
        self.assertIs(f.strategy, Union)


class ChildListFieldTest(TestCase):
    def test_list_of_children(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            entries: list[_MyEntry] = []

        f = next(f for f in extract_fields(N) if f.name == "entries")
        self.assertIsInstance(f, ChildListField)
        assert isinstance(f, ChildListField)
        self.assertEqual(f.name, "entries")
        self.assertIs(f.child_class, _MyEntry)
        self.assertIs(f.strategy, ScrapeClobbers)  # default

    def test_list_with_explicit_strategy(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            entries: Annotated[list[_MyEntry], Union] = []

        f = next(f for f in extract_fields(N) if f.name == "entries")
        assert isinstance(f, ChildListField)
        self.assertIs(f.strategy, Union)

    def test_list_with_custom_collection(self) -> None:
        cc = CustomCollection(lambda p, s, d: [])

        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            entries: Annotated[list[_MyEntry], cc] = []

        f = next(f for f in extract_fields(N) if f.name == "entries")
        assert isinstance(f, ChildListField)
        self.assertIs(f.strategy, cc)

    def test_lookup_ref_list_uses_parent_default(self) -> None:
        class MyRef(ExternalNodeRef[_Party]):
            natural_key = ("name",)
            name: str

        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            refs: list[MyRef] = []

        # The parent (Aggregate) declares the collection default. So the
        # field's strategy is the parent's default — ScrapeClobbers.
        f = next(f for f in extract_fields(N) if f.name == "refs")
        assert isinstance(f, ChildListField)
        self.assertIs(f.strategy, ScrapeClobbers)


class MisapplicationTest(TestCase):
    def test_collection_strategy_on_scalar_raises(self) -> None:
        with self.assertRaises(TypeError):

            class N(Aggregate[_Docket]):  # noqa: F841
                natural_key = ("x",)
                x: Annotated[int, ScrapeClobbers]

            extract_fields(N)

    def test_scalar_strategy_on_list_raises(self) -> None:
        with self.assertRaises(TypeError):

            class N(Aggregate[_Docket]):  # noqa: F841
                natural_key = ("x",)
                x: int
                entries: Annotated[list[_MyEntry], ScrapeWins] = []

            extract_fields(N)

    def test_multiple_strategies_in_metadata_raises(self) -> None:
        with self.assertRaises(TypeError):

            class N(Aggregate[_Docket]):  # noqa: F841
                natural_key = ("x",)
                x: Annotated[int, ScrapeWins, DBWins]

            extract_fields(N)


class MultipleFieldsTest(TestCase):
    def test_mixed_fields_extracted_in_declaration_order(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("name",)
            name: str
            count: Annotated[int, ScrapeWinsIfPresent] = 0
            entry: _MyEntry | None = None
            entries: list[_MyEntry] = []

        fields = extract_fields(N)
        self.assertEqual([f.name for f in fields], ["name", "count", "entry", "entries"])
        self.assertIsInstance(fields[0], ScalarField)
        self.assertIsInstance(fields[1], ScalarField)
        self.assertIsInstance(fields[2], ChildField)
        self.assertIsInstance(fields[3], ChildListField)


class InternalNodeAndExternalNodeRefDefaultsTest(TestCase):
    def test_internal_node_uses_scrape_wins(self) -> None:
        class N(InternalNode[_Docket]):
            natural_key = ("x",)
            x: int

        f = extract_fields(N)[0]
        assert isinstance(f, ScalarField)
        self.assertIs(f.strategy, ScrapeWins)

    def test_lookup_ref_uses_dbwins_for_scalar(self) -> None:
        class R(ExternalNodeRef[_Party]):
            natural_key = ("name",)
            name: str

        f = extract_fields(R)[0]
        assert isinstance(f, ScalarField)
        self.assertIs(f.strategy, DBWins)

    def test_lookup_ref_uses_union_for_child_collection(self) -> None:
        """When a ExternalNodeRef has its own child collection field, the
        default collection strategy is Union (not ScrapeClobbers)."""

        class R(ExternalNodeRef[_Party]):
            natural_key = ("name",)
            name: str
            sub_entries: list[_MyEntry] = []

        fields = extract_fields(R)
        sub = next(f for f in fields if f.name == "sub_entries")
        assert isinstance(sub, ChildListField)
        self.assertIs(sub.strategy, Union)
