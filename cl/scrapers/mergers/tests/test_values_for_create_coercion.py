"""Tests for ``_values_for_create``'s ``None``-to-default coercion.

Background: Django's idiomatic ``TextField(blank=True)`` is NOT NULL
with an implicit ``""`` default. Schemas that signal "no scrape data"
via ``None`` on a ``str | None`` field would have produced a NULL on
insert before this coercion landed, violating the constraint and
killing the merge.

The fix: ``_values_for_create`` post-processes the scalar-extraction
dict by replacing ``None`` values with the Pydantic field's declared
default *iff* that default is itself non-``None``. Fields that truly
default to ``None`` (e.g. nullable date columns) pass through
unchanged so they still INSERT as NULL.

Two layers of coverage:

- **Unit**: call ``_values_for_create`` directly with constructed
  ``Node`` instances and assert the returned values dict.
- **Hypothesis**: for arbitrary scrape values and schema defaults,
  the three-case invariant holds:
    1. ``value is not None`` → returned as-is.
    2. ``value is None`` and ``default is None`` → returned as None.
    3. ``value is None`` and ``default is not None`` → default returned.
"""

from datetime import date
from typing import Annotated

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cl.scrapers.mergers import (
    Aggregate,
    PreResolvedRef,
    ScrapeWinsIfPresent,
)
from hypothesis.extra.django import TestCase as HypothesisTestCase

from cl.scrapers.mergers.diff import _values_for_create
from cl.scrapers.mergers.tests.testmodels.models import TCourt, TDocket
from cl.tests.cases import TransactionTestCase


# ---------------------------------------------------------------------------
# Schemas — covers the value/default combinations we want to exercise
# ---------------------------------------------------------------------------


class _DocketWithStringDefault(Aggregate[TDocket]):
    """Optional string field with empty-string default — the
    canonical "no scrape data → empty string on insert" pattern."""

    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    case_name: Annotated[str | None, ScrapeWinsIfPresent] = ""


class _DocketWithNoneDefault(Aggregate[TDocket]):
    """Optional date field defaulting to ``None`` — for genuinely
    nullable columns the coercion must not invent a value."""

    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    date_filed: Annotated[date | None, ScrapeWinsIfPresent] = None


class _DocketWithIntegerDefault(Aggregate[TDocket]):
    """Integer field with default ``0``. ``0`` is falsy but non-None,
    so the coercion must keep it (rather than treating it as
    "missing")."""

    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    source: int | None = 0


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class NoneToDefaultUnitTest(TransactionTestCase):
    """Direct-call unit coverage of ``_values_for_create``'s None
    coercion. Uses the ``mergers_test`` sqlite DB so we can build
    real ``TCourt`` instances for the ``PreResolvedRef[TCourt]``
    fields (Pydantic's ``model_validate`` enforces the type)."""

    databases = {"mergers_test"}

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # Created once per class; persists for the whole test class.
        # No teardown needed — the sqlite DB is wiped between classes
        # by Django's test runner.
        cls.court = TCourt.objects.create(
            id="scotus", name="Supreme Court"
        )

    def test_none_replaced_with_string_default(self) -> None:
        scrape = _DocketWithStringDefault(
            court=self.court,
            docket_number_core="22-100",
            case_name=None,
        )
        values = _values_for_create(scrape)
        # ``case_name`` defaulted to ``""`` so coercion fires.
        self.assertEqual(values["case_name"], "")
        # ``docket_number_core`` was set explicitly and isn't None.
        self.assertEqual(values["docket_number_core"], "22-100")

    def test_explicit_value_overrides_default(self) -> None:
        scrape = _DocketWithStringDefault(
            court=self.court,
            docket_number_core="22-100",
            case_name="Hello",
        )
        values = _values_for_create(scrape)
        self.assertEqual(values["case_name"], "Hello")

    def test_none_default_passes_none_through(self) -> None:
        scrape = _DocketWithNoneDefault(
            court=self.court,
            docket_number_core="22-100",
            date_filed=None,
        )
        values = _values_for_create(scrape)
        # Default is ``None`` so no coercion — the column stays
        # nullable and accepts NULL.
        self.assertIsNone(values["date_filed"])

    def test_explicit_date_value_passes_through(self) -> None:
        scrape = _DocketWithNoneDefault(
            court=self.court,
            docket_number_core="22-100",
            date_filed=date(2025, 1, 1),
        )
        values = _values_for_create(scrape)
        self.assertEqual(values["date_filed"], date(2025, 1, 1))

    def test_falsy_non_none_default_preserved(self) -> None:
        """A field defaulting to ``0`` (falsy but non-None) gets
        coerced to ``0`` when the scrape passes None — *not* left as
        None. This is the case where naive ``if not default``
        coercion would misbehave; we test the contract is
        identity-on-``None``."""
        scrape = _DocketWithIntegerDefault(
            court=self.court,
            docket_number_core="22-100",
            source=None,
        )
        values = _values_for_create(scrape)
        self.assertEqual(values["source"], 0)
        # ``0`` is the *default*, not ``None``.
        self.assertIsNotNone(values["source"])

    def test_non_none_overrides_int_default(self) -> None:
        scrape = _DocketWithIntegerDefault(
            court=self.court,
            docket_number_core="22-100",
            source=4,
        )
        values = _values_for_create(scrape)
        self.assertEqual(values["source"], 4)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class NoneToDefaultPropertyTest(HypothesisTestCase):
    """For arbitrary scrape values, the three-case invariant of the
    None-coercion holds.

    Tests the three default-shape variants (string default, None
    default, integer default) separately so Hypothesis can shrink to
    per-class minimal counterexamples.
    """

    databases = {"mergers_test"}

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = TCourt.objects.create(id="scotus", name="Supreme Court")

    @given(value=st.one_of(st.none(), st.text(max_size=20)))
    @settings(
        max_examples=60,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_string_default_coercion_invariant(
        self, value: str | None
    ) -> None:
        scrape = _DocketWithStringDefault(
            court=self.court,
            docket_number_core="22-100",
            case_name=value,
        )
        values = _values_for_create(scrape)
        if value is None:
            # Default for ``case_name`` is ``""`` (non-None) → coerced.
            self.assertEqual(values["case_name"], "")
        else:
            self.assertEqual(values["case_name"], value)

    @given(value=st.one_of(st.none(), st.dates()))
    @settings(
        max_examples=60,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_none_default_coercion_invariant(
        self, value: date | None
    ) -> None:
        scrape = _DocketWithNoneDefault(
            court=self.court,
            docket_number_core="22-100",
            date_filed=value,
        )
        values = _values_for_create(scrape)
        # The default is ``None``, so the value passes through
        # whether it's a real date or None.
        self.assertEqual(values["date_filed"], value)

    @given(value=st.one_of(st.none(), st.integers(min_value=-100, max_value=100)))
    @settings(
        max_examples=60,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_integer_default_coercion_invariant(
        self, value: int | None
    ) -> None:
        scrape = _DocketWithIntegerDefault(
            court=self.court,
            docket_number_core="22-100",
            source=value,
        )
        values = _values_for_create(scrape)
        # Default is ``0``. None → 0; any other int → itself.
        expected = 0 if value is None else value
        self.assertEqual(values["source"], expected)
