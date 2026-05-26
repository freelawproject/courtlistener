"""Tests for L3c: NK element classification.

``classify_nk(cls)`` walks ``cls.natural_key`` (a tuple of strings and
PathRefs) and classifies each element so phase 2 can compute resolution
order. Variants:

- ``OwnScalar`` — a primitive scalar field on this class. Its value
  contributes literally to the NK lookup.
- ``SiblingRef`` — a sibling ExternalNodeRef or PreResolvedRef field. Its
  resolved PK contributes to the NK lookup.
- ``ParentPath`` — a path into the parent chain (``parent.X.Y...``).

Validation:
- String elements must be fields on ``cls``.
- A string element referencing a ChildListField raises.
- A string element referencing an InternalNode sibling (a node that is
  itself created/found *after* this one) raises.
- ``natural_key`` must be declared.
"""

from cl.scrapers.mergers.nk import (
    OwnScalar,
    ParentPath,
    SiblingRef,
    classify_nk,
)
from cl.scrapers.mergers.nodes import (
    Aggregate,
    InternalNode,
    ExternalNodeRef,
    PreResolvedRef,
)
from cl.scrapers.mergers.refs import parent, path_parts
from cl.tests.cases import SimpleTestCase as TestCase


class _Docket:
    pass


class _Court:
    pass


class _Party:
    pass


class _PartyTypeModel:
    pass


class _PartyRef(ExternalNodeRef[_Party]):
    natural_key = ("name",)
    name: str


class _OtherChild(InternalNode[_Party]):
    natural_key = ("x",)
    x: int


class OwnScalarClassificationTest(TestCase):
    def test_simple_own_fields(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("docket_number", "court_id")
            docket_number: str
            court_id: int

        elements = classify_nk(N)
        self.assertEqual(len(elements), 2)
        self.assertEqual(elements[0], OwnScalar(field_name="docket_number"))
        self.assertEqual(elements[1], OwnScalar(field_name="court_id"))


class ParentPathClassificationTest(TestCase):
    def test_single_parent_path(self) -> None:
        class N(InternalNode[_Docket]):
            natural_key = (parent.docket, "date_filed")
            date_filed: str

        elements = classify_nk(N)
        self.assertEqual(len(elements), 2)
        self.assertIsInstance(elements[0], ParentPath)
        assert isinstance(elements[0], ParentPath)
        self.assertEqual(path_parts(elements[0].path), ("parent", "docket"))
        self.assertEqual(elements[1], OwnScalar(field_name="date_filed"))

    def test_deep_parent_path(self) -> None:
        class N(InternalNode[_Docket]):
            natural_key = (parent.parent.court, "x")
            x: int

        elements = classify_nk(N)
        assert isinstance(elements[0], ParentPath)
        self.assertEqual(
            path_parts(elements[0].path), ("parent", "parent", "court")
        )


class SiblingRefClassificationTest(TestCase):
    def test_sibling_lookup_ref(self) -> None:
        class N(InternalNode[_PartyTypeModel]):
            natural_key = (parent.docket, "party", "name")
            party: _PartyRef
            name: str

        elements = classify_nk(N)
        # parent.docket -> ParentPath
        # "party" -> SiblingRef (ExternalNodeRef sibling)
        # "name" -> OwnScalar
        self.assertIsInstance(elements[0], ParentPath)
        self.assertIsInstance(elements[1], SiblingRef)
        assert isinstance(elements[1], SiblingRef)
        self.assertEqual(elements[1].field_name, "party")
        self.assertIs(elements[1].child_class, _PartyRef)
        self.assertIsNone(elements[1].preresolved_model)
        self.assertEqual(elements[2], OwnScalar(field_name="name"))

    def test_sibling_preresolved_ref(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("court", "docket_number")
            court: PreResolvedRef[_Court]
            docket_number: str

        elements = classify_nk(N)
        # "court" -> SiblingRef (PreResolvedRef)
        # "docket_number" -> OwnScalar
        self.assertIsInstance(elements[0], SiblingRef)
        assert isinstance(elements[0], SiblingRef)
        self.assertEqual(elements[0].field_name, "court")
        self.assertIsNone(elements[0].child_class)
        self.assertIs(elements[0].preresolved_model, _Court)


class ValidationErrorTest(TestCase):
    """These tests exercise ``classify_nk``'s direct error contract.

    They use unbound subclasses (no generic parameter binding a Django
    model) so the framework's automatic schema validation at class-def
    time is skipped, letting ``classify_nk`` be called directly. The
    end-to-end equivalents (which test that ``validate_schema`` /
    automatic validation raise ``SchemaError``) live in test_validate.py.
    """

    def test_missing_natural_key_raises(self) -> None:
        class N(Aggregate):  # type: ignore[type-arg]
            x: int

        with self.assertRaisesRegex(ValueError, "natural_key"):
            classify_nk(N)

    def test_unknown_field_raises(self) -> None:
        class N(Aggregate):  # type: ignore[type-arg]
            natural_key = ("nonexistent",)
            x: int

        with self.assertRaisesRegex(ValueError, "nonexistent"):
            classify_nk(N)

    def test_child_list_field_in_nk_raises(self) -> None:
        class Child(InternalNode[_Docket]):
            natural_key = ("y",)
            y: int

        class N(Aggregate):  # type: ignore[type-arg]
            natural_key = ("children",)
            children: list[Child] = []

        with self.assertRaisesRegex(ValueError, "collection"):
            classify_nk(N)

    def test_internal_node_sibling_in_nk_raises(self) -> None:
        """Internal-node siblings can't appear in an NK because they
        themselves haven't been matched yet."""

        class N(Aggregate):  # type: ignore[type-arg]
            natural_key = ("other",)
            other: _OtherChild | None = None

        with self.assertRaisesRegex(ValueError, "InternalNode"):
            classify_nk(N)

    def test_invalid_nk_element_type_raises(self) -> None:
        class N(Aggregate):  # type: ignore[type-arg]
            natural_key = (42,)  # type: ignore[assignment]
            x: int

        with self.assertRaisesRegex(ValueError, "NK element"):
            classify_nk(N)


class MixedTest(TestCase):
    def test_realistic_internal_node(self) -> None:
        """Matches the theory doc's TexasPartyType-ish shape."""

        class PartyType(InternalNode[_PartyTypeModel]):
            natural_key = (parent.docket, "party", "name")
            party: _PartyRef
            name: str

        elements = classify_nk(PartyType)
        kinds = [type(e).__name__ for e in elements]
        self.assertEqual(kinds, ["ParentPath", "SiblingRef", "OwnScalar"])
