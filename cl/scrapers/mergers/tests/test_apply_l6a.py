"""Tests for L6a: basic apply (Create/Update/Delete/NoOp).

``apply(diffed_root)`` walks the diffed tree and:
- Creates new rows from ``CreateOp``s, injecting the parent FK into the
  insert (last segment of the child's NK ParentPath names the FK).
- Updates existing rows from ``UpdateOp``s by setting fields and saving.
- Deletes existing rows from ``DeleteOp``s in post-order (children
  first).
- Leaves ``NoOp`` rows untouched.

The returned ``MergeOutcome`` carries the resolved root, plus per-model
sets of created/updated/deleted PKs.

L6a doesn't yet handle:
- Lifecycle hooks (L6b)
- ExternalNodeRef pre-resolution / FK injection (L6c)
"""

from cl.scrapers.mergers.apply import apply
from cl.scrapers.mergers.diff import reconcile
from cl.scrapers.mergers.nodes import (
    Aggregate,
    InternalNode,
    PreResolvedRef,
)
from cl.scrapers.mergers.paired import build_paired_tree
from cl.scrapers.mergers.refs import parent
from cl.scrapers.mergers.tests.testmodels.models import (
    TCourt,
    TDocket,
    TDocketEntry,
)
from cl.tests.cases import TransactionTestCase


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class _EntrySchema(InternalNode[TDocketEntry]):
    natural_key = (parent.docket, "entry_type")

    entry_type: str
    description: str = ""


class _DocketSchema(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    case_name: str = ""
    entries: list[_EntrySchema] = []


def _pipeline(scrape):
    """Glue: paired -> diffed -> apply. Returns the outcome."""
    return apply(reconcile(build_paired_tree(scrape)))


# ---------------------------------------------------------------------------
# Root-only Create / Update / NoOp
# ---------------------------------------------------------------------------


class RootCreateTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_create_inserts_new_row(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Fresh",
        )
        outcome = _pipeline(scrape)

        # Row exists in DB
        d = TDocket.objects.get(court=self.scotus, docket_number_core="22-100")
        self.assertEqual(d.case_name, "Fresh")

        # Outcome tracks it
        self.assertEqual(outcome.creates.get(TDocket), {d.pk})
        self.assertEqual(outcome.updates, {})
        self.assertEqual(outcome.deletes, {})
        self.assertIsNotNone(outcome.root)
        assert outcome.root is not None
        self.assertEqual(outcome.root.pk, d.pk)


class RootUpdateTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100", case_name="Old"
        )

    def test_update_writes_changed_field(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="New",
        )
        outcome = _pipeline(scrape)
        self.docket_db.refresh_from_db()
        self.assertEqual(self.docket_db.case_name, "New")
        self.assertEqual(outcome.updates.get(TDocket), {self.docket_db.pk})
        self.assertEqual(outcome.creates, {})
        self.assertEqual(outcome.deletes, {})


class RootNoOpTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100", case_name="X"
        )

    def test_no_op_makes_no_changes(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus, docket_number_core="22-100", case_name="X"
        )
        outcome = _pipeline(scrape)
        # No creates/updates/deletes.
        self.assertEqual(outcome.creates, {})
        self.assertEqual(outcome.updates, {})
        self.assertEqual(outcome.deletes, {})
        # Root is still set to the matched row.
        assert outcome.root is not None
        self.assertEqual(outcome.root.pk, self.docket_db.pk)


# ---------------------------------------------------------------------------
# Children: Create / Update / Delete
# ---------------------------------------------------------------------------


class ChildrenCreateTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_new_root_with_new_entries(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[
                _EntrySchema(entry_type="motion"),
                _EntrySchema(entry_type="order"),
            ],
        )
        outcome = _pipeline(scrape)
        docket = TDocket.objects.get(docket_number_core="22-100")
        entries = list(docket.entries.all().order_by("entry_type"))
        self.assertEqual(len(entries), 2)
        self.assertEqual([e.entry_type for e in entries], ["motion", "order"])

        # Outcome: 1 docket + 2 entries created.
        self.assertEqual(outcome.creates.get(TDocket), {docket.pk})
        self.assertEqual(
            outcome.creates.get(TDocketEntry), {e.pk for e in entries}
        )

    def test_existing_root_with_one_new_child(self) -> None:
        docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[_EntrySchema(entry_type="motion")],
        )
        _pipeline(scrape)
        entries = list(docket_db.entries.all())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].entry_type, "motion")


class ChildrenUpdateTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )
        self.entry_db = TDocketEntry.objects.create(
            docket=self.docket_db,
            entry_type="motion",
            description="old desc",
        )

    def test_child_field_change(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[
                _EntrySchema(entry_type="motion", description="new desc")
            ],
        )
        outcome = _pipeline(scrape)
        self.entry_db.refresh_from_db()
        self.assertEqual(self.entry_db.description, "new desc")
        self.assertEqual(
            outcome.updates.get(TDocketEntry), {self.entry_db.pk}
        )


class ChildrenDeleteTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )
        self.entry_db = TDocketEntry.objects.create(
            docket=self.docket_db, entry_type="motion"
        )

    def test_db_only_child_deleted_under_scrape_clobbers(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[],  # nothing scraped → existing entry should be deleted
        )
        pk = self.entry_db.pk
        outcome = _pipeline(scrape)
        self.assertFalse(TDocketEntry.objects.filter(pk=pk).exists())
        self.assertEqual(outcome.deletes.get(TDocketEntry), {pk})


# ---------------------------------------------------------------------------
# Mixed (a more realistic scenario)
# ---------------------------------------------------------------------------


class MixedTreeTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100", case_name="X"
        )
        self.motion_db = TDocketEntry.objects.create(
            docket=self.docket_db,
            entry_type="motion",
            description="old",
        )
        self.order_db = TDocketEntry.objects.create(
            docket=self.docket_db, entry_type="order"
        )

    def test_create_update_delete_in_one_apply(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="X",  # NoOp on root
            entries=[
                _EntrySchema(
                    entry_type="motion", description="updated"
                ),  # Update
                _EntrySchema(entry_type="notice"),  # Create
                # "order" not in scrape → Delete
            ],
        )
        outcome = _pipeline(scrape)

        # Root unchanged
        self.docket_db.refresh_from_db()
        self.assertEqual(self.docket_db.case_name, "X")
        self.assertNotIn(TDocket, outcome.creates)
        self.assertNotIn(TDocket, outcome.updates)

        # Motion updated
        self.motion_db.refresh_from_db()
        self.assertEqual(self.motion_db.description, "updated")
        self.assertIn(self.motion_db.pk, outcome.updates.get(TDocketEntry, set()))

        # Notice created
        notice = TDocketEntry.objects.get(
            docket=self.docket_db, entry_type="notice"
        )
        self.assertIn(notice.pk, outcome.creates.get(TDocketEntry, set()))

        # Order deleted
        self.assertFalse(
            TDocketEntry.objects.filter(pk=self.order_db.pk).exists()
        )
        self.assertIn(self.order_db.pk, outcome.deletes.get(TDocketEntry, set()))
