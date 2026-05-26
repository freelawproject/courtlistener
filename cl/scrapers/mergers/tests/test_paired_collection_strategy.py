"""Integration tests: per-field ``CollectionStrategy`` is actually
honored by ``_pairing_to_paired_nodes``.

Background: the framework historically defined ``apply_collection_strategy``
as a pure function (tested in test_reconcile_collection.py) but the
production pipeline didn't call it — db-only items always became
``DeleteOp``\\ s regardless of whether the field was ``Union`` or
``DBClobbers``. The Texas parity test surfaced this when an empty
party list silently deleted previously-merged party rows.

The fix routes through ``_pairing_to_paired_nodes`` consulting the
field descriptor's ``strategy``:

- ``ScrapeClobbers``: db-only nodes become ``DeleteOp``\\ s.
- ``Union``: db-only nodes drop out of the paired tree entirely
  (preserved on the DB side without a corresponding op).
- ``DBClobbers``: both unmatched buckets drop — only paired rows
  produce ops.

These tests exercise the integration end-to-end: build paired tree →
reconcile → apply, then assert on what shows up in
``MergeOutcome.creates`` / ``.updates`` / ``.deletes``.
"""

from typing import Annotated

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from cl.scrapers.mergers import (
    Aggregate,
    DBClobbers,
    InternalNode,
    PreResolvedRef,
    ScrapeClobbers,
    Union,
    apply,
    build_paired_tree,
    parent,
    reconcile,
)
from cl.scrapers.mergers.tests.testmodels.models import (
    TCourt,
    TDocket,
    TDocketEntry,
)
from cl.tests.cases import TransactionTestCase


# ---------------------------------------------------------------------------
# Schemas — one per strategy variant on the entries list
# ---------------------------------------------------------------------------


class _EntrySchema(InternalNode[TDocketEntry]):
    # ``parent.docket`` in the NK is what triggers parent-FK
    # auto-injection on create; without it the framework can't fill
    # ``TDocketEntry.docket_id`` and the insert fails the NOT NULL
    # constraint.
    natural_key = (parent.docket, "entry_type")

    entry_type: str
    description: str = ""


class _DocketScrapeClobbersSchema(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    # No explicit collection strategy → inherits Aggregate's default
    # ``ScrapeClobbers``.
    entries: list[_EntrySchema] = []


class _DocketUnionSchema(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    entries: Annotated[list[_EntrySchema], Union] = []


class _DocketDBClobbersSchema(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    entries: Annotated[list[_EntrySchema], DBClobbers] = []


def _pipeline(scrape):
    return apply(reconcile(build_paired_tree(scrape)))


# ---------------------------------------------------------------------------
# Per-strategy unit tests
# ---------------------------------------------------------------------------


class ScrapeClobbersIntegrationTest(TransactionTestCase):
    """``ScrapeClobbers`` (the default) deletes db-only rows and
    creates scrape-only rows. Confirms the baseline behavior — these
    tests would have passed before the framework fix too, but they
    anchor the integration suite."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.court = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket = TDocket.objects.create(
            court=self.court, docket_number_core="22-100"
        )
        self.entry_a = TDocketEntry.objects.create(
            docket=self.docket, entry_type="A", description="db-A"
        )
        self.entry_b = TDocketEntry.objects.create(
            docket=self.docket, entry_type="B", description="db-B"
        )

    def test_db_only_entries_are_deleted(self) -> None:
        """Scrape mentions only A; B is db-only → deleted."""
        scrape = _DocketScrapeClobbersSchema(
            court=self.court,
            docket_number_core="22-100",
            entries=[_EntrySchema(entry_type="A", description="db-A")],
        )
        outcome = _pipeline(scrape)
        self.assertEqual(
            outcome.deletes.get(TDocketEntry, set()), {self.entry_b.pk}
        )
        self.assertNotIn(TDocketEntry, outcome.creates)

    def test_scrape_only_entries_are_created(self) -> None:
        """Scrape adds a new entry C → CreateOp."""
        scrape = _DocketScrapeClobbersSchema(
            court=self.court,
            docket_number_core="22-100",
            entries=[
                _EntrySchema(entry_type="A", description="db-A"),
                _EntrySchema(entry_type="B", description="db-B"),
                _EntrySchema(entry_type="C", description="new-C"),
            ],
        )
        outcome = _pipeline(scrape)
        self.assertNotIn(TDocketEntry, outcome.deletes)
        self.assertEqual(
            len(outcome.creates.get(TDocketEntry, set())), 1
        )


class UnionIntegrationTest(TransactionTestCase):
    """``Union`` preserves db-only rows (no DeleteOps) but still
    creates scrape-only rows."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.court = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket = TDocket.objects.create(
            court=self.court, docket_number_core="22-100"
        )
        self.entry_a = TDocketEntry.objects.create(
            docket=self.docket, entry_type="A", description="db-A"
        )
        self.entry_b = TDocketEntry.objects.create(
            docket=self.docket, entry_type="B", description="db-B"
        )

    def test_db_only_entries_are_preserved(self) -> None:
        """Scrape mentions only A; B is db-only → preserved
        (the regression the Texas parity test caught)."""
        scrape = _DocketUnionSchema(
            court=self.court,
            docket_number_core="22-100",
            entries=[_EntrySchema(entry_type="A", description="db-A")],
        )
        outcome = _pipeline(scrape)
        self.assertNotIn(TDocketEntry, outcome.deletes)
        # B still exists in DB.
        self.assertTrue(
            TDocketEntry.objects.filter(pk=self.entry_b.pk).exists()
        )

    def test_scrape_only_entries_still_create(self) -> None:
        """Union is additive — scrape-only entries still become creates."""
        scrape = _DocketUnionSchema(
            court=self.court,
            docket_number_core="22-100",
            entries=[
                _EntrySchema(entry_type="A", description="db-A"),
                _EntrySchema(entry_type="B", description="db-B"),
                _EntrySchema(entry_type="C", description="new-C"),
            ],
        )
        outcome = _pipeline(scrape)
        self.assertNotIn(TDocketEntry, outcome.deletes)
        self.assertEqual(
            len(outcome.creates.get(TDocketEntry, set())), 1
        )

    def test_empty_scrape_preserves_all_db_entries(self) -> None:
        """Empty scrape list with Union → all db entries preserved.
        This is the exact pattern that broke Texas's
        ``test_empty_parties_preserves_existing``."""
        scrape = _DocketUnionSchema(
            court=self.court,
            docket_number_core="22-100",
            entries=[],
        )
        outcome = _pipeline(scrape)
        self.assertNotIn(TDocketEntry, outcome.deletes)
        self.assertEqual(
            TDocketEntry.objects.filter(docket=self.docket).count(), 2
        )


class DBClobbersIntegrationTest(TransactionTestCase):
    """``DBClobbers`` drops both unmatched buckets — only paired rows
    produce ops."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.court = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket = TDocket.objects.create(
            court=self.court, docket_number_core="22-100"
        )
        self.entry_a = TDocketEntry.objects.create(
            docket=self.docket, entry_type="A", description="db-A"
        )
        self.entry_b = TDocketEntry.objects.create(
            docket=self.docket, entry_type="B", description="db-B"
        )

    def test_scrape_only_entries_dropped(self) -> None:
        """Scrape adds C; under DBClobbers it's *not* created."""
        scrape = _DocketDBClobbersSchema(
            court=self.court,
            docket_number_core="22-100",
            entries=[
                _EntrySchema(entry_type="A", description="db-A"),
                _EntrySchema(entry_type="C", description="ignored"),
            ],
        )
        outcome = _pipeline(scrape)
        self.assertNotIn(TDocketEntry, outcome.creates)
        # B isn't in scrape but db-only also dropped under DBClobbers.
        self.assertNotIn(TDocketEntry, outcome.deletes)

    def test_paired_entries_can_still_update(self) -> None:
        """Matched entries still get updated when scalar fields differ."""
        scrape = _DocketDBClobbersSchema(
            court=self.court,
            docket_number_core="22-100",
            entries=[
                _EntrySchema(entry_type="A", description="updated-A"),
            ],
        )
        outcome = _pipeline(scrape)
        self.assertEqual(
            outcome.updates.get(TDocketEntry, set()), {self.entry_a.pk}
        )


# ---------------------------------------------------------------------------
# Property: pipeline outputs match ``apply_collection_strategy`` semantics
# ---------------------------------------------------------------------------


_ENTRY_TYPES = st.sampled_from(["A", "B", "C", "D", "E"])
_DESCRIPTIONS = st.sampled_from(["x", "y", "z", "w"])


@st.composite
def _entry_dict(draw):
    return {
        "entry_type": draw(_ENTRY_TYPES),
        "description": draw(_DESCRIPTIONS),
    }


def _entries_unique_by_type(items: list[dict]) -> list[dict]:
    """De-dup an entry list by ``entry_type`` keeping the first
    occurrence — the NK is single-field so duplicates would trip
    ``pair_by_nk``."""
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        if item["entry_type"] in seen:
            continue
        seen.add(item["entry_type"])
        out.append(item)
    return out


class PipelineHonorsStrategyPropertyTest(HypothesisTestCase):
    """Property test: for any (db_entries, scrape_entries) the
    pipeline's resulting (creates, updates, deletes) sets match what
    ``apply_collection_strategy`` would produce on the same pairing.

    Concretely:
    - ``ScrapeClobbers``: unmatched scrape → creates; unmatched db → deletes.
    - ``Union``: unmatched scrape → creates; unmatched db → preserved.
    - ``DBClobbers``: unmatched scrape → ignored; unmatched db → preserved.

    Uses ``hypothesis.extra.django.TestCase`` so each example runs in
    its own transaction (and is rolled back at the end), and the
    class-level ``TCourt`` survives across examples.
    """

    databases = {"mergers_test"}

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = TCourt.objects.create(id="scotus", name="Supreme Court")

    def _setup_db_entries(
        self, docket: TDocket, db_entries: list[dict]
    ) -> dict[str, int]:
        """Materialize a list of DB entries on the docket; return
        ``{entry_type: pk}`` so the test can map types to PKs in the
        outcome dicts."""
        out: dict[str, int] = {}
        for item in db_entries:
            entry = TDocketEntry.objects.create(
                docket=docket,
                entry_type=item["entry_type"],
                description=item["description"],
            )
            out[item["entry_type"]] = entry.pk
        return out

    def _run_with_strategy(
        self,
        schema_cls,
        db_entries: list[dict],
        scrape_entries: list[dict],
    ) -> tuple[set[str], set[str], set[str]]:
        """Run the pipeline and return ``(created_types,
        updated_types, deleted_types)`` as sets of ``entry_type``
        strings — equivalence-class identity that doesn't depend on
        which PK happened to be assigned."""
        docket = TDocket.objects.create(
            court=self.court, docket_number_core="22-100"
        )
        db_pks = self._setup_db_entries(docket, db_entries)
        pk_to_type = {pk: et for et, pk in db_pks.items()}

        scrape = schema_cls(
            court=self.court,
            docket_number_core="22-100",
            entries=[_EntrySchema(**e) for e in scrape_entries],
        )
        outcome = _pipeline(scrape)
        created_types = {
            TDocketEntry.objects.get(pk=pk).entry_type
            for pk in outcome.creates.get(TDocketEntry, set())
        }
        updated_types = {
            pk_to_type[pk]
            for pk in outcome.updates.get(TDocketEntry, set())
            if pk in pk_to_type
        }
        deleted_types = {
            pk_to_type[pk]
            for pk in outcome.deletes.get(TDocketEntry, set())
            if pk in pk_to_type
        }
        return created_types, updated_types, deleted_types

    @given(
        db_entries=st.lists(_entry_dict(), max_size=5),
        scrape_entries=st.lists(_entry_dict(), max_size=5),
    )
    @settings(
        max_examples=40,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_scrape_clobbers_creates_and_deletes_unmatched(
        self, db_entries: list[dict], scrape_entries: list[dict]
    ) -> None:
        db_entries = _entries_unique_by_type(db_entries)
        scrape_entries = _entries_unique_by_type(scrape_entries)
        db_types = {e["entry_type"] for e in db_entries}
        scrape_types = {e["entry_type"] for e in scrape_entries}

        created, _, deleted = self._run_with_strategy(
            _DocketScrapeClobbersSchema, db_entries, scrape_entries
        )
        self.assertEqual(created, scrape_types - db_types)
        self.assertEqual(deleted, db_types - scrape_types)

    @given(
        db_entries=st.lists(_entry_dict(), max_size=5),
        scrape_entries=st.lists(_entry_dict(), max_size=5),
    )
    @settings(
        max_examples=40,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_union_creates_unmatched_preserves_db_only(
        self, db_entries: list[dict], scrape_entries: list[dict]
    ) -> None:
        db_entries = _entries_unique_by_type(db_entries)
        scrape_entries = _entries_unique_by_type(scrape_entries)
        db_types = {e["entry_type"] for e in db_entries}
        scrape_types = {e["entry_type"] for e in scrape_entries}

        created, _, deleted = self._run_with_strategy(
            _DocketUnionSchema, db_entries, scrape_entries
        )
        self.assertEqual(created, scrape_types - db_types)
        # Union never deletes.
        self.assertEqual(deleted, set())

    @given(
        db_entries=st.lists(_entry_dict(), max_size=5),
        scrape_entries=st.lists(_entry_dict(), max_size=5),
    )
    @settings(
        max_examples=40,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_dbclobbers_drops_both_unmatched_buckets(
        self, db_entries: list[dict], scrape_entries: list[dict]
    ) -> None:
        db_entries = _entries_unique_by_type(db_entries)
        scrape_entries = _entries_unique_by_type(scrape_entries)

        created, _, deleted = self._run_with_strategy(
            _DocketDBClobbersSchema, db_entries, scrape_entries
        )
        self.assertEqual(created, set())
        self.assertEqual(deleted, set())
