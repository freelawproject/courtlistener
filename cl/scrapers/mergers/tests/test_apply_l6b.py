"""Tests for L6b: lifecycle hooks + follow-up collection.

After every mutated row the framework calls
``node.on_update(old_db, new_db)`` on the scrape Node. The default
dispatches:
- ``old_db is None`` → ``on_create(new_db)``  (Create case)
- ``new_db is None`` → ``on_delete(old_db)``  (Delete case)
- both set → return ``None``               (Update / NoOp cases)

The framework collects whatever each hook returns (list[Callable] or
``None``) and appends to ``MergeOutcome.follow_ups`` in post-order
(children's hooks fire before their parent's).

For ``old_db`` to carry the *original* values during an Update (rather
than the mutated ones), the framework snapshots the DB instance before
saving.

Limitation: ``on_delete`` only fires when a scrape Node exists for the
deletion. DB-only deletes under ``ScrapeClobbers`` have no scrape Node,
so their ``on_delete`` is *not* auto-fired; callers can detect those
deletions via ``MergeOutcome.deletes``.
"""

from typing import Any, ClassVar

from cl.scrapers.mergers.apply import apply
from cl.scrapers.mergers.diff import reconcile
from cl.scrapers.mergers.follow_up import FollowUp
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


def _pipeline(scrape):
    return apply(reconcile(build_paired_tree(scrape)))


# ---------------------------------------------------------------------------
# Schemas with hooks
# ---------------------------------------------------------------------------


# Class-level call recorder so tests can verify what fired with what args.
_calls: ClassVar[list[tuple[str, Any]]] = []


def _reset_calls() -> None:
    _calls.clear()


class _EntryWithHooks(InternalNode[TDocketEntry]):
    natural_key = (parent.docket, "entry_type")

    entry_type: str
    description: str = ""

    def on_create(self, new_db: Any) -> Any:
        _calls.append(("entry_create", new_db.pk))
        return [FollowUp(name=f"entry-create:{new_db.pk}", fn=lambda: None)]

    def on_update(self, old_db: Any, new_db: Any) -> Any:
        if old_db is not None and new_db is not None:
            _calls.append(
                ("entry_update", old_db.description, new_db.description)
            )
            return [
                FollowUp(
                    name=f"entry-update:{new_db.pk}",
                    fn=lambda: None,
                )
            ]
        # Fall through to default for create/delete dispatch
        return super().on_update(old_db, new_db)


class _DocketWithHooks(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    case_name: str = ""
    entries: list[_EntryWithHooks] = []

    def on_create(self, new_db: Any) -> Any:
        _calls.append(("docket_create", new_db.pk))
        return [FollowUp(name=f"docket-create:{new_db.pk}", fn=lambda: None)]

    def on_update(self, old_db: Any, new_db: Any) -> Any:
        if old_db is not None and new_db is not None:
            _calls.append(
                ("docket_update", old_db.case_name, new_db.case_name)
            )
            return None
        return super().on_update(old_db, new_db)


# ---------------------------------------------------------------------------
# Create / Update / NoOp hooks
# ---------------------------------------------------------------------------


class CreateHookTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        _reset_calls()
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_on_create_fires_with_new_db_pk(self) -> None:
        scrape = _DocketWithHooks(
            court=self.scotus, docket_number_core="22-100"
        )
        outcome = _pipeline(scrape)
        docket = TDocket.objects.get(docket_number_core="22-100")

        self.assertIn(("docket_create", docket.pk), _calls)
        names = [
            f.name if isinstance(f, FollowUp) else None
            for f in outcome.follow_ups
        ]
        self.assertIn(f"docket-create:{docket.pk}", names)

    def test_default_on_update_dispatches_to_on_create(self) -> None:
        """The framework calls ``on_update(None, new_db)`` for Create;
        the default dispatches to ``on_create``."""
        scrape = _DocketWithHooks(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[_EntryWithHooks(entry_type="motion")],
        )
        _pipeline(scrape)
        entry = TDocketEntry.objects.get(entry_type="motion")
        self.assertIn(("entry_create", entry.pk), _calls)


class UpdateHookTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        _reset_calls()
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100", case_name="Old"
        )

    def test_on_update_old_db_has_original_values(self) -> None:
        """The key behavior: ``old_db.case_name`` is the original
        value, not the mutated one."""
        scrape = _DocketWithHooks(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="New",
        )
        _pipeline(scrape)
        self.assertEqual(_calls, [("docket_update", "Old", "New")])

    def test_on_update_for_no_op_passes_same_value(self) -> None:
        scrape = _DocketWithHooks(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Old",
        )
        _pipeline(scrape)
        # NoOp triggers on_update with old/new pointing to the same data.
        self.assertEqual(_calls, [("docket_update", "Old", "Old")])

    def test_entry_update_collects_followup(self) -> None:
        TDocketEntry.objects.create(
            docket=self.docket_db,
            entry_type="motion",
            description="old desc",
        )
        scrape = _DocketWithHooks(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Old",  # NoOp on root
            entries=[
                _EntryWithHooks(
                    entry_type="motion", description="new desc"
                )
            ],
        )
        outcome = _pipeline(scrape)
        # Entry's on_update reads old vs new descriptions
        self.assertIn(("entry_update", "old desc", "new desc"), _calls)
        # Follow-up appears in outcome
        names = [
            f.name if isinstance(f, FollowUp) else None
            for f in outcome.follow_ups
        ]
        self.assertTrue(
            any(n is not None and n.startswith("entry-update:") for n in names)
        )


# ---------------------------------------------------------------------------
# Ordering: children before parent
# ---------------------------------------------------------------------------


class PostOrderTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        _reset_calls()
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_children_hooks_fire_before_parent(self) -> None:
        """Children's on_update fires before parent's on_update."""
        scrape = _DocketWithHooks(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Fresh",
            entries=[_EntryWithHooks(entry_type="motion")],
        )
        _pipeline(scrape)

        # Both ``docket_create`` and ``entry_create`` should fire; the
        # entry's must come before the docket's (children → parent).
        docket_idx = next(
            i for i, (name, _) in enumerate(_calls) if name == "docket_create"
        )
        entry_idx = next(
            i for i, (name, _) in enumerate(_calls) if name == "entry_create"
        )
        self.assertLess(entry_idx, docket_idx)


# ---------------------------------------------------------------------------
# DB-only deletes: limitation
# ---------------------------------------------------------------------------


class _EntryWithDeleteHook(InternalNode[TDocketEntry]):
    """Schema with an explicit on_delete to exercise db-only deletes."""

    natural_key = (parent.docket, "entry_type")

    entry_type: str
    description: str = ""

    def on_delete(self, old_db: Any) -> Any:
        _calls.append(("entry_delete", old_db.pk, old_db.entry_type))
        return [
            FollowUp(name=f"entry-delete:{old_db.pk}", fn=lambda: None)
        ]


class _DocketWithDeleteHookEntries(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    case_name: str = ""
    entries: list[_EntryWithDeleteHook] = []


class DBOnlyDeleteHookTest(TransactionTestCase):
    """DB-only deletes (under ``ScrapeClobbers``) fire ``on_delete``.

    Implementation note: the scrape Node for a db-only delete doesn't
    exist; the framework synthesizes one via ``cls.model_construct()``
    so the hook can be invoked. The hook should rely on its ``old_db``
    argument for data — ``self``'s field values are unset.
    """

    databases = {"mergers_test"}

    def setUp(self) -> None:
        _reset_calls()
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100", case_name="X"
        )
        self.entry_db = TDocketEntry.objects.create(
            docket=self.docket_db, entry_type="motion"
        )

    def test_db_only_delete_fires_on_delete_with_old_db(self) -> None:
        scrape = _DocketWithDeleteHookEntries(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="X",
            entries=[],  # entry is db-only and gets deleted
        )
        outcome = _pipeline(scrape)
        # Deletion happens
        self.assertEqual(outcome.deletes.get(TDocketEntry), {self.entry_db.pk})
        # on_delete fired with old_db carrying the original values
        self.assertIn(
            ("entry_delete", self.entry_db.pk, "motion"), _calls
        )
        # Follow-up collected
        names = [
            f.name if isinstance(f, FollowUp) else None
            for f in outcome.follow_ups
        ]
        self.assertIn(f"entry-delete:{self.entry_db.pk}", names)

    def test_default_on_delete_returns_none_no_followup(self) -> None:
        """Schema with no on_delete override still has the hook
        invoked, but the default returns ``None`` so no follow-up is
        added."""
        scrape = _DocketWithHooks(  # uses _EntryWithHooks (no on_delete override)
            court=self.scotus,
            docket_number_core="22-100",
            case_name="X",
            entries=[],  # the existing entry is db-only and gets deleted
        )
        outcome = _pipeline(scrape)
        self.assertEqual(
            outcome.deletes.get(TDocketEntry), {self.entry_db.pk}
        )
        # No "entry_delete" call because _EntryWithHooks doesn't define one
        # and the default returns None.
        self.assertFalse(
            any(name == "entry_delete" for name, *_ in _calls)
        )


# ---------------------------------------------------------------------------
# Multiple hooks accumulate
# ---------------------------------------------------------------------------


class MultiHookAccumulationTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        _reset_calls()
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_many_creates_accumulate_followups(self) -> None:
        scrape = _DocketWithHooks(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[
                _EntryWithHooks(entry_type="motion"),
                _EntryWithHooks(entry_type="order"),
                _EntryWithHooks(entry_type="notice"),
            ],
        )
        outcome = _pipeline(scrape)

        # 3 entries created + 1 docket created → 4 follow-ups.
        followup_names = [
            f.name if isinstance(f, FollowUp) else "<bare>"
            for f in outcome.follow_ups
        ]
        self.assertEqual(len(followup_names), 4)
        entry_followups = [
            n for n in followup_names if n.startswith("entry-create:")
        ]
        docket_followups = [
            n for n in followup_names if n.startswith("docket-create:")
        ]
        self.assertEqual(len(entry_followups), 3)
        self.assertEqual(len(docket_followups), 1)
