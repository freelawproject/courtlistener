"""Tests for the ``OwnedChild`` node type.

``OwnedChild[ModelT]`` covers OneToOne relationships where the FK lives
on the *parent* row (e.g., ``Docket.originating_court_information``
pointing at an ``OriginatingCourtInformation``):

- During phase 4 the framework processes ``OwnedChild`` siblings before
  self (so the parent's FK is settable) via a recursive ``_apply_node``
  call. The owned row receives its own scalar updates, children, and
  lifecycle hooks.
- The returned DB instance is injected as the parent's FK kwarg.
- For matched-but-unchanged OwnedChild rows, no FK write happens on the
  parent (no-op optimization in ``_apply_update``).
- For ``OwnedChild`` that appears or disappears under an existing
  parent, the framework upgrades a ``NoOp`` parent to an Update so the
  parent's FK column gets written.

Default ``natural_key`` for ``OwnedChild`` is ``()`` because the
matching is trivially "the single row reachable via the parent's
forward FK."
"""

from cl.scrapers.mergers import (
    Aggregate,
    OwnedChild,
    PreResolvedRef,
    apply,
    build_paired_tree,
    merge_one,
    reconcile,
)
from cl.scrapers.mergers.tests.testmodels.models import (
    TCourt,
    TDocket,
    TDocketHeader,
)
from cl.tests.cases import TransactionTestCase


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class _HeaderSchema(OwnedChild[TDocketHeader]):
    """An owned 1:1 child whose FK is on the parent."""

    title: str = ""
    note: str = ""


class _DocketWithHeaderSchema(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    case_name: str = ""

    header: _HeaderSchema | None = None


def _pipeline(scrape):
    return apply(reconcile(build_paired_tree(scrape)))


# ---------------------------------------------------------------------------
# Create path
# ---------------------------------------------------------------------------


class OwnedChildCreateTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_create_parent_with_owned_child(self) -> None:
        """New docket + new header: header created first, then docket
        with header_id pointing at it."""
        scrape = _DocketWithHeaderSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Foo",
            header=_HeaderSchema(title="Banner", note="N1"),
        )
        outcome = _pipeline(scrape)

        # Both rows exist
        header = TDocketHeader.objects.get(title="Banner")
        docket = TDocket.objects.get(docket_number_core="22-100")
        self.assertEqual(docket.header_id, header.pk)

        # Both in outcome.creates
        self.assertIn(header.pk, outcome.creates.get(TDocketHeader, set()))
        self.assertIn(docket.pk, outcome.creates.get(TDocket, set()))

    def test_create_parent_without_owned_child(self) -> None:
        """Optional ``OwnedChild`` left unset → parent row created with
        header_id NULL."""
        scrape = _DocketWithHeaderSchema(
            court=self.scotus, docket_number_core="22-100", header=None
        )
        outcome = _pipeline(scrape)
        docket = TDocket.objects.get(docket_number_core="22-100")
        self.assertIsNone(docket.header_id)
        self.assertNotIn(TDocketHeader, outcome.creates)


# ---------------------------------------------------------------------------
# Update path with matched OwnedChild
# ---------------------------------------------------------------------------


class OwnedChildMatchedUpdateTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.header_db = TDocketHeader.objects.create(
            title="Old Banner", note="Old"
        )
        self.docket_db = TDocket.objects.create(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="X",
            header=self.header_db,
        )

    def test_owned_child_field_change(self) -> None:
        """Scrape updates header fields → the header row gets updated,
        parent FK stays put."""
        scrape = _DocketWithHeaderSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="X",
            header=_HeaderSchema(title="New Banner", note="Old"),
        )
        outcome = _pipeline(scrape)

        self.header_db.refresh_from_db()
        self.assertEqual(self.header_db.title, "New Banner")

        # Outcome carries the header update, not a re-create
        self.assertNotIn(TDocketHeader, outcome.creates)
        self.assertEqual(
            outcome.updates.get(TDocketHeader), {self.header_db.pk}
        )

        # Parent FK didn't change, so the Docket itself isn't in updates
        # (NoOp on the docket fields + no FK change == no parent write).
        self.docket_db.refresh_from_db()
        self.assertEqual(self.docket_db.header_id, self.header_db.pk)
        self.assertNotIn(TDocket, outcome.updates)

    def test_matched_unchanged_owned_child_is_noop(self) -> None:
        """Scrape matches DB exactly → no writes."""
        scrape = _DocketWithHeaderSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="X",
            header=_HeaderSchema(title="Old Banner", note="Old"),
        )
        outcome = _pipeline(scrape)
        self.assertEqual(outcome.creates, {})
        self.assertEqual(outcome.updates, {})
        self.assertEqual(outcome.deletes, {})


# ---------------------------------------------------------------------------
# Update path: OwnedChild appears or disappears
# ---------------------------------------------------------------------------


class OwnedChildAppearsTest(TransactionTestCase):
    """Existing parent gains an OwnedChild (parent.header_id was NULL,
    scrape provides one)."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="X",
            header=None,
        )

    def test_existing_parent_gains_owned_child(self) -> None:
        scrape = _DocketWithHeaderSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="X",
            header=_HeaderSchema(title="New", note="N"),
        )
        outcome = _pipeline(scrape)

        # Header created
        header = TDocketHeader.objects.get(title="New")
        self.assertIn(header.pk, outcome.creates.get(TDocketHeader, set()))

        # Parent's header_id was None, must now point at the new header
        self.docket_db.refresh_from_db()
        self.assertEqual(self.docket_db.header_id, header.pk)
        # Parent FK changed, so the docket appears in updates even though
        # its scalar fields didn't change.
        self.assertIn(self.docket_db.pk, outcome.updates.get(TDocket, set()))


class OwnedChildDisappearsTest(TransactionTestCase):
    """Existing parent loses its OwnedChild (DB has one, scrape says
    None)."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.header_db = TDocketHeader.objects.create(title="Doomed")
        self.docket_db = TDocket.objects.create(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="X",
            header=self.header_db,
        )

    def test_existing_parent_loses_owned_child(self) -> None:
        header_pk = self.header_db.pk
        scrape = _DocketWithHeaderSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="X",
            header=None,
        )
        outcome = _pipeline(scrape)

        # Header deleted under ScrapeClobbers semantics (OwnedChild's
        # default collection strategy).
        self.assertFalse(TDocketHeader.objects.filter(pk=header_pk).exists())
        self.assertIn(header_pk, outcome.deletes.get(TDocketHeader, set()))

        # Parent's header_id must be cleared.
        self.docket_db.refresh_from_db()
        self.assertIsNone(self.docket_db.header_id)
        self.assertIn(self.docket_db.pk, outcome.updates.get(TDocket, set()))


# ---------------------------------------------------------------------------
# merge_one integration
# ---------------------------------------------------------------------------


class OwnedChildViaMergeOneTest(TransactionTestCase):
    """End-to-end via the orchestrator."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_merge_one_creates_with_owned_child(self) -> None:
        scrape = _DocketWithHeaderSchema(
            court=self.scotus,
            docket_number_core="22-100",
            header=_HeaderSchema(title="Hi"),
        )
        outcome = merge_one(scrape, using="mergers_test")
        d = TDocket.objects.get(docket_number_core="22-100")
        h = TDocketHeader.objects.get(title="Hi")
        self.assertEqual(d.header_id, h.pk)
        assert outcome.root is not None
        self.assertEqual(outcome.root.pk, d.pk)
