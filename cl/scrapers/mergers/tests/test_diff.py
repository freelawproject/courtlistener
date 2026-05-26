"""Tests for L5: reconcile.

``reconcile(paired_root)`` walks a paired tree and produces a diffed
tree. Each node's ``change`` is one of:

- ``CreateOp(values)`` — scrape-only; new row to insert.
- ``UpdateOp(field_changes)`` — both sides; ``field_changes`` dict has
  exactly the fields the per-field strategies decided to write.
- ``DeleteOp`` — db-only; row to remove.
- ``NoOp`` — both sides but no field changes.

If a node class defines ``custom_class_update(self, scraped, db)``, the
framework calls it to obtain a desired Django row state and re-diffs
against the original DB row to populate ``field_changes`` (or
``CreateOp.values`` for the new-row case).

L5 only diffs ``ScalarField`` values; FK-from-ExternalNodeRef resolution
happens in L6 when PKs are available.
"""

from typing import Annotated

from cl.scrapers.mergers.diff import (
    CreateOp,
    DeleteOp,
    DiffedChildren,
    DiffedNode,
    NoOp,
    UpdateOp,
    reconcile,
)
from cl.scrapers.mergers.nodes import (
    Aggregate,
    InternalNode,
    PreResolvedRef,
)
from cl.scrapers.mergers.paired import build_paired_tree
from cl.scrapers.mergers.refs import parent
from cl.scrapers.mergers.strategies import (
    DBWins,
    ScrapeWinsIfPresent,
)
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


class _DocketSchemaWithDBWinsCaseName(Aggregate[TDocket]):
    """Same as above but ``case_name`` is DBWins — never changes."""

    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    case_name: Annotated[str, DBWins] = ""


class _DocketSchemaScrapeIfPresent(Aggregate[TDocket]):
    """``case_name`` is ScrapeWinsIfPresent: ``None`` doesn't overwrite."""

    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    case_name: Annotated[str | None, ScrapeWinsIfPresent] = None


class _DocketSchemaCustomUpdate(Aggregate[TDocket]):
    """Schema overriding ``custom_class_update`` — for the create case
    sets ``case_name`` to a derived value; for the update case OR-bits
    a constant into ``source``."""

    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    case_name: str = ""
    source: int = 0

    def custom_class_update(
        self, scraped: "_DocketSchemaCustomUpdate", db: TDocket | None
    ) -> TDocket:
        if db is None:
            return TDocket(
                court_id=scraped.court.id,
                docket_number_core=scraped.docket_number_core,
                case_name=f"DERIVED: {scraped.case_name}",
                source=1,
            )
        # Update path: keep most fields from db, OR-bits source from scrape.
        db.case_name = scraped.case_name or db.case_name
        db.source = (db.source or 0) | (scraped.source or 0)
        return db


# ---------------------------------------------------------------------------
# No-op and basic diffs
# ---------------------------------------------------------------------------


class NoOpAndBasicTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_no_op_when_scrape_matches_db(self) -> None:
        TDocket.objects.create(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Existing",
        )
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Existing",
        )
        diffed = reconcile(build_paired_tree(scrape))
        self.assertIsInstance(diffed.change, NoOp)

    def test_update_when_field_differs(self) -> None:
        TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100", case_name="Old"
        )
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="New",
        )
        diffed = reconcile(build_paired_tree(scrape))
        self.assertIsInstance(diffed.change, UpdateOp)
        assert isinstance(diffed.change, UpdateOp)
        self.assertEqual(diffed.change.field_changes, {"case_name": "New"})

    def test_create_for_scrape_only(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="brand-new",
            case_name="Fresh",
        )
        diffed = reconcile(build_paired_tree(scrape))
        self.assertIsInstance(diffed.change, CreateOp)
        assert isinstance(diffed.change, CreateOp)
        # Includes the scalar fields with their scrape values.
        self.assertEqual(diffed.change.values["docket_number_core"], "brand-new")
        self.assertEqual(diffed.change.values["case_name"], "Fresh")

    def test_delete_for_db_only_child(self) -> None:
        docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )
        TDocketEntry.objects.create(docket=docket_db, entry_type="motion")

        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[],  # DB has an entry the scrape doesn't
        )
        diffed = reconcile(build_paired_tree(scrape))
        # The root is NoOp (matched).
        self.assertIsInstance(diffed.change, NoOp)
        # The child entry is db-only → DeleteOp.
        entries_field = next(c for c in diffed.children if c.name == "entries")
        self.assertEqual(len(entries_field.paired), 1)
        entry_diff = entries_field.paired[0]
        self.assertIsInstance(entry_diff.change, DeleteOp)


# ---------------------------------------------------------------------------
# Strategy-specific diffs
# ---------------------------------------------------------------------------


class StrategyDiffTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_dbwins_never_updates(self) -> None:
        TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100", case_name="DB"
        )
        scrape = _DocketSchemaWithDBWinsCaseName(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Scrape",
        )
        diffed = reconcile(build_paired_tree(scrape))
        # case_name has DBWins → no change to case_name.
        self.assertIsInstance(diffed.change, NoOp)

    def test_scrape_wins_if_present_skips_none(self) -> None:
        TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100", case_name="DB"
        )
        scrape = _DocketSchemaScrapeIfPresent(
            court=self.scotus,
            docket_number_core="22-100",
            case_name=None,
        )
        diffed = reconcile(build_paired_tree(scrape))
        self.assertIsInstance(diffed.change, NoOp)

    def test_scrape_wins_if_present_writes_when_value_set(self) -> None:
        TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100", case_name="DB"
        )
        scrape = _DocketSchemaScrapeIfPresent(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Override",
        )
        diffed = reconcile(build_paired_tree(scrape))
        assert isinstance(diffed.change, UpdateOp)
        self.assertEqual(diffed.change.field_changes, {"case_name": "Override"})


# ---------------------------------------------------------------------------
# custom_class_update
# ---------------------------------------------------------------------------


class CustomClassUpdateTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_custom_update_for_create_extracts_from_returned_instance(
        self,
    ) -> None:
        scrape = _DocketSchemaCustomUpdate(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="raw",
            source=0,
        )
        diffed = reconcile(build_paired_tree(scrape))
        # Create. Values come from the desired Django instance returned
        # by custom_class_update (not from raw scrape values).
        assert isinstance(diffed.change, CreateOp)
        self.assertEqual(diffed.change.values["case_name"], "DERIVED: raw")
        self.assertEqual(diffed.change.values["source"], 1)

    def test_custom_update_for_update_rediffs(self) -> None:
        TDocket.objects.create(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="kept",
            source=0b0001,
        )
        scrape = _DocketSchemaCustomUpdate(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="",  # falsy → keep db case_name
            source=0b0100,  # OR-bit into db source
        )
        diffed = reconcile(build_paired_tree(scrape))
        # case_name unchanged; source goes 0001 -> 0001 | 0100 = 0101.
        assert isinstance(diffed.change, UpdateOp)
        self.assertEqual(
            diffed.change.field_changes, {"source": 0b0101}
        )

    def test_custom_update_can_produce_noop(self) -> None:
        """If custom_class_update returns a state equal to the original
        db, the diff is NoOp."""
        TDocket.objects.create(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="kept",
            source=0b0001,
        )
        scrape = _DocketSchemaCustomUpdate(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="",
            source=0b0001,  # same bit as db → OR-bit doesn't add anything
        )
        diffed = reconcile(build_paired_tree(scrape))
        self.assertIsInstance(diffed.change, NoOp)


# ---------------------------------------------------------------------------
# Tree structure preservation
# ---------------------------------------------------------------------------


class TreeStructureTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100", case_name="X"
        )
        TDocketEntry.objects.create(
            docket=self.docket_db,
            entry_type="motion",
            description="old desc",
        )

    def test_mixed_diff_tree(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="X",  # unchanged
            entries=[
                _EntrySchema(
                    entry_type="motion", description="new desc"
                ),  # changed
                _EntrySchema(
                    entry_type="order", description="brand new"
                ),  # create
            ],
        )
        diffed = reconcile(build_paired_tree(scrape))

        # Root NoOp.
        self.assertIsInstance(diffed.change, NoOp)

        # Entries: one Update, one Create.
        entries_field = next(c for c in diffed.children if c.name == "entries")
        changes_by_type = {
            type(e.change).__name__ for e in entries_field.paired
        }
        self.assertSetEqual(changes_by_type, {"UpdateOp", "CreateOp"})

        # The updated entry's field_changes carries new description.
        updated = next(
            e for e in entries_field.paired if isinstance(e.change, UpdateOp)
        )
        assert isinstance(updated.change, UpdateOp)
        self.assertEqual(
            updated.change.field_changes, {"description": "new desc"}
        )

    def test_diffed_node_carries_scrape_and_db(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="X",
        )
        diffed = reconcile(build_paired_tree(scrape))
        self.assertIsInstance(diffed, DiffedNode)
        self.assertIs(diffed.scrape, scrape)
        self.assertIsNotNone(diffed.db)
        # Children list type
        self.assertTrue(
            all(isinstance(c, DiffedChildren) for c in diffed.children)
        )
