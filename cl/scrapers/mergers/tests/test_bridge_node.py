"""Tests for the ``BridgeNode`` node type.

``BridgeNode[ModelT]`` covers rows that straddle two aggregates: a
``CaseTransfer`` row connecting two ``Docket`` rows is the canonical
example. From either parent's perspective the bridge is a reverse-FK
child (the FK column lives on the bridge), but the row's identity is
*global* by NK so two separate merges of the two paired aggregates
converge on the same row.

What this exercises:

- **Phase 2 pairing**: scrape refs resolve via a single batched
  ``Model.objects.filter(...)`` keyed by NK, ignoring path-scoping.
- **Phase 4 create**: parent FK is auto-injected on insert from the
  parent Pydantic field's reverse-relation descriptor (e.g.,
  ``origin_bridges`` → ``origin_docket``).
- **Phase 4 update (cross-merge fill-in)**: a half-filled bridge row
  inserted by the *other* aggregate's prior merge is matched
  globally; the previously-NULL parent-FK column on this side gets
  written.

A ``BridgeNode`` is never deleted by an aggregate disappearing from
scrape (default-collection is ``Union``).
"""

from cl.scrapers.mergers import (
    Aggregate,
    BridgeNode,
    PreResolvedRef,
    apply,
    build_paired_tree,
    reconcile,
)
from cl.scrapers.mergers.tests.testmodels.models import (
    TBridge,
    TCourt,
    TDocket,
)
from cl.tests.cases import TransactionTestCase


# ---------------------------------------------------------------------------
# Schemas: two BridgeNode subclasses, one for each side of the bridge
# ---------------------------------------------------------------------------


class _OriginBridge(BridgeNode[TBridge]):
    """Used when the docket being merged is the *origin* side. The
    framework auto-injects ``origin_docket`` from the parent's
    ``origin_bridges`` reverse-FK descriptor."""

    natural_key = ("label",)

    label: str
    note: str = ""


class _DestinationBridge(BridgeNode[TBridge]):
    """Mirror of ``_OriginBridge`` for the destination side."""

    natural_key = ("label",)

    label: str
    note: str = ""


class _DocketWithBridges(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str

    # Pydantic field names match Django's reverse accessors —
    # ``TBridge.origin_docket`` has related_name="origin_bridges".
    origin_bridges: list[_OriginBridge] = []
    destination_bridges: list[_DestinationBridge] = []


def _pipeline(scrape):
    return apply(reconcile(build_paired_tree(scrape)))


# ---------------------------------------------------------------------------
# Create path: parent FK auto-injection on insert
# ---------------------------------------------------------------------------


class BridgeNodeCreateTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )

    def test_create_inserts_bridge_with_parent_fk(self) -> None:
        """Brand-new bridge row → framework inserts it with the parent
        FK (``origin_docket``) auto-injected from the
        ``origin_bridges`` reverse accessor."""
        scrape = _DocketWithBridges(
            court=self.scotus,
            docket_number_core="22-100",
            origin_bridges=[_OriginBridge(label="B1", note="hello")],
        )
        outcome = _pipeline(scrape)

        bridge = TBridge.objects.get(label="B1")
        self.assertEqual(bridge.origin_docket_id, self.docket_db.pk)
        self.assertIsNone(bridge.destination_docket_id)
        self.assertEqual(bridge.note, "hello")
        self.assertIn(bridge.pk, outcome.creates.get(TBridge, set()))


# ---------------------------------------------------------------------------
# Cross-merge fill-in: matched bridge row's NULL side gets written
# ---------------------------------------------------------------------------


class BridgeNodeCrossMergeTest(TransactionTestCase):
    """Simulate two paired aggregates merging in sequence and
    converging on the same bridge row."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.origin_docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )
        self.destination_docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-200"
        )

    def test_second_merge_fills_in_null_side(self) -> None:
        # First merge: origin docket inserts the bridge with
        # destination_docket=NULL.
        first = _DocketWithBridges(
            court=self.scotus,
            docket_number_core="22-100",
            origin_bridges=[_OriginBridge(label="B1")],
        )
        _pipeline(first)

        bridge = TBridge.objects.get(label="B1")
        self.assertEqual(bridge.origin_docket_id, self.origin_docket_db.pk)
        self.assertIsNone(bridge.destination_docket_id)

        # Second merge: destination docket finds the same bridge via
        # global NK lookup; the previously-NULL ``destination_docket``
        # FK gets written via the BridgeNode field-update path.
        second = _DocketWithBridges(
            court=self.scotus,
            docket_number_core="22-200",
            destination_bridges=[_DestinationBridge(label="B1")],
        )
        outcome = _pipeline(second)

        bridge.refresh_from_db()
        self.assertEqual(bridge.origin_docket_id, self.origin_docket_db.pk)
        self.assertEqual(
            bridge.destination_docket_id, self.destination_docket_db.pk
        )
        # The bridge row was updated, not re-created.
        self.assertNotIn(TBridge, outcome.creates)
        self.assertIn(bridge.pk, outcome.updates.get(TBridge, set()))

    def test_rematch_no_change_is_noop(self) -> None:
        """Re-merging the same side after a row is fully populated
        produces no writes."""
        # Pre-populate fully.
        TBridge.objects.create(
            label="B1",
            origin_docket=self.origin_docket_db,
            destination_docket=self.destination_docket_db,
        )
        scrape = _DocketWithBridges(
            court=self.scotus,
            docket_number_core="22-100",
            origin_bridges=[_OriginBridge(label="B1")],
        )
        outcome = _pipeline(scrape)
        self.assertEqual(outcome.creates, {})
        self.assertEqual(outcome.updates, {})


# ---------------------------------------------------------------------------
# Union semantics: a DB-only bridge stays put
# ---------------------------------------------------------------------------


class BridgeNodeUnionTest(TransactionTestCase):
    """A bridge row reachable from this docket but absent from scrape
    must not be touched — ``BridgeNode`` default-collection is
    ``Union``."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )

    def test_db_only_bridge_is_preserved(self) -> None:
        existing = TBridge.objects.create(
            label="kept", origin_docket=self.docket_db
        )
        scrape = _DocketWithBridges(
            court=self.scotus,
            docket_number_core="22-100",
            origin_bridges=[],  # scrape says no bridges
        )
        outcome = _pipeline(scrape)

        self.assertTrue(TBridge.objects.filter(pk=existing.pk).exists())
        self.assertNotIn(TBridge, outcome.deletes)
