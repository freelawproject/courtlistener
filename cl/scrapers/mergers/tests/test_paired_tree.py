"""Tests for L4c: paired-tree builder.

``build_paired_tree(scrape_root)`` walks a scrape tree, queries the DB
for matching children at each level, and produces a parallel paired
tree.

Scope of this sub-cycle:
- Root + InternalNode children, one level deep.
- Child NK is ``(parent.X, *own_scalars)`` — parent FK + own scalars.
- No ExternalNodeRef siblings in NK (deferred to L4d).
- ``ScrapeClobbers``-style strategies for collection fields.

The ``parent.X`` semantic: the last element of the PathRef names the FK
column on the child model. So ``parent.docket`` in
``TDocketEntry.natural_key`` means "filter by ``docket=<parent_db>``".
"""

from cl.scrapers.mergers.nodes import Aggregate, InternalNode, PreResolvedRef
from cl.scrapers.mergers.paired import (
    ChildNodes,
    PairedNode,
    build_paired_tree,
)
from cl.scrapers.mergers.refs import parent
from cl.scrapers.mergers.tests.testmodels.models import (
    TCourt,
    TDocket,
    TDocketEntry,
)
from cl.tests.cases import TransactionTestCase


# ---------------------------------------------------------------------------
# Test schemas
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


# ---------------------------------------------------------------------------
# Root-only tests
# ---------------------------------------------------------------------------


class RootOnlyPairingTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_root_with_no_children_and_db_match(self) -> None:
        TDocket.objects.create(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Found",
        )
        scrape = _DocketSchema(
            court=self.scotus, docket_number_core="22-100"
        )
        tree = build_paired_tree(scrape)

        self.assertIsInstance(tree, PairedNode)
        self.assertIs(tree.scrape, scrape)
        assert tree.db is not None
        self.assertEqual(tree.db.case_name, "Found")
        # The "entries" field exists but has no items.
        self.assertEqual(len(tree.children), 1)
        self.assertEqual(tree.children[0].name, "entries")
        self.assertEqual(tree.children[0].paired, [])

    def test_root_with_no_db_match(self) -> None:
        scrape = _DocketSchema(
            court=self.scotus, docket_number_core="new-docket"
        )
        tree = build_paired_tree(scrape)

        self.assertIs(tree.scrape, scrape)
        self.assertIsNone(tree.db)
        # No DB parent, so no DB children fetched. scrape.entries is empty
        # too, so the entries field has no items.
        self.assertEqual(tree.children[0].paired, [])


# ---------------------------------------------------------------------------
# Children pairing tests
# ---------------------------------------------------------------------------


class ChildPairingTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus,
            docket_number_core="22-100",
            case_name="Existing",
        )

    def test_all_children_matched(self) -> None:
        TDocketEntry.objects.create(
            docket=self.docket_db, entry_type="motion", description="db-m"
        )
        TDocketEntry.objects.create(
            docket=self.docket_db, entry_type="order", description="db-o"
        )

        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[
                _EntrySchema(entry_type="motion"),
                _EntrySchema(entry_type="order"),
            ],
        )
        tree = build_paired_tree(scrape)

        entries_field = tree.children[0]
        self.assertEqual(entries_field.name, "entries")
        self.assertEqual(len(entries_field.paired), 2)
        for pn in entries_field.paired:
            self.assertIsNotNone(pn.scrape)
            self.assertIsNotNone(pn.db)
        # Verify the (motion -> db-m, order -> db-o) pairing
        by_type = {pn.scrape.entry_type: pn.db for pn in entries_field.paired}
        self.assertEqual(by_type["motion"].description, "db-m")
        self.assertEqual(by_type["order"].description, "db-o")

    def test_scrape_only_child(self) -> None:
        """Scrape has an entry not in DB → PairedNode(scrape=X, db=None)."""
        TDocketEntry.objects.create(
            docket=self.docket_db, entry_type="motion", description="db-m"
        )
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[
                _EntrySchema(entry_type="motion"),
                _EntrySchema(entry_type="order"),  # scrape only
            ],
        )
        tree = build_paired_tree(scrape)
        entries_field = tree.children[0]
        scrape_only = [
            pn for pn in entries_field.paired if pn.db is None
        ]
        self.assertEqual(len(scrape_only), 1)
        assert scrape_only[0].scrape is not None
        self.assertEqual(scrape_only[0].scrape.entry_type, "order")

    def test_db_only_child(self) -> None:
        """DB has an entry the scrape doesn't → PairedNode(scrape=None, db=Y)."""
        TDocketEntry.objects.create(
            docket=self.docket_db, entry_type="motion", description="db-m"
        )
        TDocketEntry.objects.create(
            docket=self.docket_db, entry_type="order", description="db-o"
        )
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[
                _EntrySchema(entry_type="motion"),
                # "order" not in scrape — DB-only
            ],
        )
        tree = build_paired_tree(scrape)
        entries_field = tree.children[0]
        db_only = [pn for pn in entries_field.paired if pn.scrape is None]
        self.assertEqual(len(db_only), 1)
        assert db_only[0].db is not None
        self.assertEqual(db_only[0].db.entry_type, "order")

    def test_mixed_pair_scrape_only_db_only(self) -> None:
        TDocketEntry.objects.create(
            docket=self.docket_db, entry_type="motion", description="db-m"
        )
        TDocketEntry.objects.create(
            docket=self.docket_db, entry_type="order", description="db-o"
        )
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[
                _EntrySchema(entry_type="motion"),  # matched
                _EntrySchema(entry_type="notice"),  # scrape-only
                # "order" not in scrape — DB-only
            ],
        )
        tree = build_paired_tree(scrape)
        entries_field = tree.children[0]

        matched = [
            pn for pn in entries_field.paired
            if pn.scrape is not None and pn.db is not None
        ]
        scrape_only = [pn for pn in entries_field.paired if pn.db is None]
        db_only = [pn for pn in entries_field.paired if pn.scrape is None]

        self.assertEqual(len(matched), 1)
        self.assertEqual(len(scrape_only), 1)
        self.assertEqual(len(db_only), 1)
        assert matched[0].scrape is not None
        self.assertEqual(matched[0].scrape.entry_type, "motion")

    def test_new_root_no_db_children(self) -> None:
        """When the root has no DB match, child queries are skipped and
        all scrape children become scrape-only."""
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="new",
            entries=[
                _EntrySchema(entry_type="motion"),
                _EntrySchema(entry_type="order"),
            ],
        )
        tree = build_paired_tree(scrape)
        self.assertIsNone(tree.db)
        entries_field = tree.children[0]
        self.assertEqual(len(entries_field.paired), 2)
        for pn in entries_field.paired:
            self.assertIsNone(pn.db)
            self.assertIsNotNone(pn.scrape)

    def test_isolates_children_by_parent_fk(self) -> None:
        """A different docket's entries must NOT appear in the pairing."""
        other_docket = TDocket.objects.create(
            court=self.scotus, docket_number_core="other"
        )
        TDocketEntry.objects.create(
            docket=other_docket, entry_type="motion", description="OTHER"
        )
        # Our docket has no entries.

        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[_EntrySchema(entry_type="motion")],
        )
        tree = build_paired_tree(scrape)
        entries_field = tree.children[0]
        # One scrape-only entry; the OTHER docket's row must NOT be in db_only.
        self.assertEqual(len(entries_field.paired), 1)
        pn = entries_field.paired[0]
        self.assertIsNotNone(pn.scrape)
        self.assertIsNone(pn.db)


# ---------------------------------------------------------------------------
# Data-structure tests
# ---------------------------------------------------------------------------


class PairedNodeShapeTest(TransactionTestCase):
    """Smoke tests for PairedNode / ChildNodes construction."""

    databases = {"mergers_test"}

    def test_paired_node_fields_present(self) -> None:
        pn = PairedNode(scrape=None, db=None, children=[])
        self.assertIsNone(pn.scrape)
        self.assertIsNone(pn.db)
        self.assertEqual(pn.children, [])

    def test_child_nodes_construction(self) -> None:
        cn = ChildNodes(name="foo", paired=[])
        self.assertEqual(cn.name, "foo")
        self.assertEqual(cn.paired, [])
