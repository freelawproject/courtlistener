"""Tests for L4 root prefetch.

``prefetch_root(scrape_root)`` queries the bound Django model by the
resolved NK and returns the matched DB row (or ``None``).

Resolution rules:
- ``OwnScalar`` element: filter by ``field_name=scrape.field_name``.
- ``SiblingRef`` element: filter by the field's *resolved* value (a
  Django instance or its PK; the ORM accepts either).
- ``ParentPath`` is disallowed on a root (no parent exists).

When the Aggregate declares ``lock_for_update=True``, the query is
issued via ``select_for_update()``. (SQLite ignores row locks but
doesn't error — fine for the unit test.)
"""

from cl.scrapers.mergers.nodes import Aggregate, PreResolvedRef
from cl.scrapers.mergers.prefetch import prefetch_root
from cl.scrapers.mergers.tests.testmodels.models import TCourt, TDocket
from cl.tests.cases import TransactionTestCase


class _DocketSchema(Aggregate[TDocket]):
    """Minimal schema for testing root prefetch."""

    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    case_name: str = ""


class _DocketSchemaLocking(
    Aggregate[TDocket], lock_for_update=True
):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str


class PrefetchRootMatchingTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.cal = TCourt.objects.create(id="cal", name="California")

    def test_returns_matched_row(self) -> None:
        TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100", case_name="Foo"
        )
        scrape = _DocketSchema(court=self.scotus, docket_number_core="22-100")
        result = prefetch_root(scrape)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.case_name, "Foo")

    def test_returns_none_when_no_match(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus, docket_number_core="does-not-exist"
        )
        result = prefetch_root(scrape)
        self.assertIsNone(result)

    def test_distinguishes_by_court(self) -> None:
        """Same docket_number_core in two courts — must return the
        right one."""
        TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100", case_name="SC"
        )
        TDocket.objects.create(
            court=self.cal, docket_number_core="22-100", case_name="CA"
        )

        scrape_scotus = _DocketSchema(
            court=self.scotus, docket_number_core="22-100"
        )
        scrape_cal = _DocketSchema(
            court=self.cal, docket_number_core="22-100"
        )

        r_scotus = prefetch_root(scrape_scotus)
        r_cal = prefetch_root(scrape_cal)

        assert r_scotus is not None
        assert r_cal is not None
        self.assertEqual(r_scotus.case_name, "SC")
        self.assertEqual(r_cal.case_name, "CA")


class PrefetchRootLockTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        TDocket.objects.create(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="LockedRow",
        )

    def test_lock_for_update_runs_without_error(self) -> None:
        """SQLite doesn't honor row locks but accepts the syntax; this
        confirms the lock_for_update kwarg threads through without
        crashing."""
        scrape = _DocketSchemaLocking(
            court=self.scotus, docket_number_core="22-100"
        )
        # select_for_update() requires being inside an atomic block.
        from django.db import transaction

        with transaction.atomic(using="mergers_test"):
            result = prefetch_root(scrape)

        self.assertIsNotNone(result)


class PrefetchRootValidationTest(TransactionTestCase):
    """Edge cases on schema shape."""

    databases = {"mergers_test"}

    def test_parent_path_in_root_nk_raises(self) -> None:
        """Aggregates (roots) have no parent — a parent-path NK element
        is a schema bug."""
        from cl.scrapers.mergers.refs import parent

        # We can't trigger this at class def because validate_schema
        # doesn't yet check it; declare and call prefetch_root to surface
        # the runtime error.
        class BadRoot(Aggregate[TDocket]):
            natural_key = (parent.foo,)
            x: int

        scrape = BadRoot(x=1)
        with self.assertRaises(ValueError):
            prefetch_root(scrape)
