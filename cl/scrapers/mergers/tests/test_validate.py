"""Tests for L3d: schema validation.

``validate_schema(cls)`` runs at class-definition time for concrete
subclasses (those that bind a Django model via the generic parameter),
invoked through ``Node.__pydantic_init_subclass__``.

Current checks:
- ``natural_key`` must be declared and resolve cleanly.
- A non-Optional single ``ChildField`` referring to a ``ExternalNodeRef`` with
  ``absence_policy=NoopIfMissing`` raises ``SchemaError``.
"""

from cl.scrapers.mergers.nodes import (
    Aggregate,
    CreateIfMissing,
    ErrorIfMissing,
    InternalNode,
    ExternalNodeRef,
    NoopIfMissing,
)
from cl.scrapers.mergers.validate import SchemaError, validate_schema  # noqa: F401 — validate_schema is used in some explicit tests
from cl.tests.cases import SimpleTestCase as TestCase


class _Docket:
    pass


class _Party:
    pass


class ValidSchemaTest(TestCase):
    def test_minimal_aggregate_with_nk(self) -> None:
        class N(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int

        # Should not raise
        validate_schema(N)


class MissingNKTest(TestCase):
    def test_missing_nk_raises_at_class_def(self) -> None:
        with self.assertRaises(SchemaError):

            class N(Aggregate[_Docket]):  # noqa: F841
                x: int


class NoopIfMissingValidationTest(TestCase):
    def test_noop_missing_on_non_optional_single_ref_raises(self) -> None:
        class MyRef(ExternalNodeRef[_Party], absence_policy=NoopIfMissing):
            natural_key = ("name",)
            name: str

        with self.assertRaises(SchemaError):

            class Parent(Aggregate[_Docket]):  # noqa: F841
                natural_key = ("x",)
                x: int
                ref: MyRef  # non-optional + Noop policy → error

    def test_noop_missing_on_optional_single_ref_ok(self) -> None:
        class MyRef(ExternalNodeRef[_Party], absence_policy=NoopIfMissing):
            natural_key = ("name",)
            name: str

        class Parent(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            ref: MyRef | None = None

        validate_schema(Parent)

    def test_noop_missing_on_list_field_ok(self) -> None:
        """List fields can have NoopIfMissing items — missing items
        just don't appear in the result list."""

        class MyRef(ExternalNodeRef[_Party], absence_policy=NoopIfMissing):
            natural_key = ("name",)
            name: str

        class Parent(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            refs: list[MyRef] = []

        validate_schema(Parent)

    def test_create_if_missing_on_non_optional_ref_ok(self) -> None:
        class MyRef(ExternalNodeRef[_Party], absence_policy=CreateIfMissing):
            natural_key = ("name",)
            name: str

        class Parent(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            ref: MyRef

        validate_schema(Parent)

    def test_error_if_missing_on_non_optional_ref_ok(self) -> None:
        class MyRef(ExternalNodeRef[_Party], absence_policy=ErrorIfMissing):
            natural_key = ("name",)
            name: str

        class Parent(Aggregate[_Docket]):
            natural_key = ("x",)
            x: int
            ref: MyRef

        validate_schema(Parent)


class NKValidationTest(TestCase):
    def test_invalid_nk_raises_at_class_def(self) -> None:
        with self.assertRaises(SchemaError):

            class N(Aggregate[_Docket]):  # noqa: F841
                natural_key = ("nonexistent_field",)
                x: int


class AbstractBasesNotValidatedTest(TestCase):
    """Aggregate/InternalNode/ExternalNodeRef themselves are abstract; they
    shouldn't trigger validation at their own definition. Otherwise
    importing the framework would fail."""

    def test_framework_imports_cleanly(self) -> None:
        # If validation had run for Aggregate itself, the test file
        # couldn't import and we wouldn't reach this point.
        self.assertTrue(True)


