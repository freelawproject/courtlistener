"""Tests for L7: the orchestrator.

``merge_one(scrape, using=...)`` wraps all four phases in
``transaction.atomic()`` and returns the ``MergeOutcome``. Any
exception from any phase rolls the entire merge back.

Also tests that the individual phase functions remain usable for batch
callers who want to span multiple merges in one transaction.
"""

from cl.scrapers.mergers import (
    Aggregate,
    InternalNode,
    ExternalNodeRef,
    PreResolvedRef,
    apply,
    build_paired_tree,
    merge_one,
    reconcile,
)
from cl.scrapers.mergers.follow_up import FollowUp
from cl.scrapers.mergers.nodes import ErrorIfMissing
from cl.scrapers.mergers.refs import parent
from cl.scrapers.mergers.tests.testmodels.models import (
    TCourt,
    TDocket,
    TDocketEntry,
    TParty,
    TPartyType,
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


class _PartyRefStrict(ExternalNodeRef[TParty], absence_policy=ErrorIfMissing):
    natural_key = ("name",)
    name: str


class _PartyTypeStrict(InternalNode[TPartyType]):
    natural_key = (parent.docket, "party", "role")
    party: _PartyRefStrict
    role: str


class _DocketStrict(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")
    court: PreResolvedRef[TCourt]
    docket_number_core: str
    party_types: list[_PartyTypeStrict] = []


class _DocketWithCreateHook(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    case_name: str = ""

    def on_create(self, new_db):
        return [
            FollowUp(name=f"created:{new_db.pk}", fn=lambda: None)
        ]


# ---------------------------------------------------------------------------
# merge_one basics
# ---------------------------------------------------------------------------


class MergeOneCreateTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_create_root_and_children_end_to_end(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Test Case",
            entries=[
                _EntrySchema(entry_type="motion"),
                _EntrySchema(entry_type="order"),
            ],
        )
        outcome = merge_one(scrape, using="mergers_test")

        # DB rows exist
        d = TDocket.objects.get(docket_number_core="22-100")
        self.assertEqual(d.case_name, "Test Case")
        self.assertEqual(d.entries.count(), 2)

        # Outcome
        self.assertEqual(outcome.creates.get(TDocket), {d.pk})
        self.assertEqual(
            outcome.creates.get(TDocketEntry),
            {e.pk for e in d.entries.all()},
        )
        assert outcome.root is not None
        self.assertEqual(outcome.root.pk, d.pk)


class MergeOneUpdateTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Old",
        )

    def test_update_writes_field(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="New",
        )
        outcome = merge_one(scrape, using="mergers_test")
        self.docket_db.refresh_from_db()
        self.assertEqual(self.docket_db.case_name, "New")
        self.assertEqual(outcome.updates.get(TDocket), {self.docket_db.pk})


# ---------------------------------------------------------------------------
# Rollback on failure
# ---------------------------------------------------------------------------


class MergeOneRollbackTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_apply_failure_rolls_back_all_writes(self) -> None:
        """``ErrorIfMissing`` ExternalNodeRef raises during apply — the whole
        merge (including any rows it had already created) must roll
        back."""
        scrape = _DocketStrict(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeStrict(
                    party=_PartyRefStrict(name="Nonexistent"),
                    role="Defendant",
                )
            ],
        )

        with self.assertRaises(ValueError):
            merge_one(scrape, using="mergers_test")

        # The Docket would have been created before the PartyType's
        # ExternalNodeRef raises; the transaction must have rolled that back.
        self.assertFalse(
            TDocket.objects.filter(docket_number_core="22-100").exists()
        )
        self.assertFalse(TPartyType.objects.exists())


# ---------------------------------------------------------------------------
# Follow-ups
# ---------------------------------------------------------------------------


class MergeOneFollowUpTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_follow_ups_present_in_outcome(self) -> None:
        scrape = _DocketWithCreateHook(
            court=self.scotus,
            docket_number_core="22-100",
        )
        outcome = merge_one(scrape, using="mergers_test")
        names = [
            f.name if isinstance(f, FollowUp) else None
            for f in outcome.follow_ups
        ]
        self.assertTrue(
            any(n is not None and n.startswith("created:") for n in names)
        )


# ---------------------------------------------------------------------------
# Phase reuse for batch callers
# ---------------------------------------------------------------------------


class PhaseReuseTest(TransactionTestCase):
    """Confirm the phase functions remain callable separately so a
    batch caller can span multiple merges in one transaction (or
    interleave with other DB work)."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_individual_phases_compose(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Z",
        )
        paired = build_paired_tree(scrape)
        diffed = reconcile(paired)
        outcome = apply(diffed)

        d = TDocket.objects.get(docket_number_core="22-100")
        self.assertEqual(d.case_name, "Z")
        self.assertEqual(outcome.creates.get(TDocket), {d.pk})

    def test_batch_of_two_in_one_transaction(self) -> None:
        """Two merges in one outer atomic — emulates the
        ``CaseTransfer`` cross-aggregate case."""
        from django.db import transaction

        scrape_a = _DocketSchema(
            court=self.scotus, docket_number_core="A"
        )
        scrape_b = _DocketSchema(
            court=self.scotus, docket_number_core="B"
        )
        with transaction.atomic(using="mergers_test"):
            out_a = merge_one(scrape_a, using="mergers_test")
            out_b = merge_one(scrape_b, using="mergers_test")

        self.assertTrue(
            TDocket.objects.filter(docket_number_core="A").exists()
        )
        self.assertTrue(
            TDocket.objects.filter(docket_number_core="B").exists()
        )
        assert out_a.root is not None
        assert out_b.root is not None
        self.assertNotEqual(out_a.root.pk, out_b.root.pk)
