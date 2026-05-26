"""Sanity check for the L4 test-DB infrastructure.

Confirms:
- The ``mergers_test`` database exists and is reachable.
- The test-only Django models live there (routed by
  ``MergersTestRouter``).
- Basic CRUD round-trips through the ORM.
"""

from django.db import connections

from cl.scrapers.mergers.tests.testmodels.models import (
    TCourt,
    TDocket,
    TDocketEntry,
    TParty,
    TPartyType,
)
from cl.tests.cases import TransactionTestCase


class TestModelsSetupTest(TransactionTestCase):
    databases = {"mergers_test"}

    def test_mergers_test_db_exists(self) -> None:
        self.assertIn("mergers_test", connections.databases)

    def test_court_creation_and_round_trip(self) -> None:
        TCourt.objects.create(id="scotus", name="Supreme Court")
        fetched = TCourt.objects.get(pk="scotus")
        self.assertEqual(fetched.name, "Supreme Court")

    def test_router_sends_writes_to_mergers_test(self) -> None:
        court = TCourt.objects.create(id="cal", name="California")
        # _state.db records which DB the instance was written to.
        self.assertEqual(court._state.db, "mergers_test")

    def test_docket_with_court_fk(self) -> None:
        court = TCourt.objects.create(id="scotus", name="Supreme Court")
        d = TDocket.objects.create(
            court=court, docket_number_core="123", case_name="Foo v. Bar"
        )
        self.assertEqual(d.court_id, "scotus")
        self.assertEqual(d.case_name, "Foo v. Bar")

    def test_full_aggregate_round_trip(self) -> None:
        """Exercise the whole shape we'll merge against: docket + entry
        + party + partytype."""
        court = TCourt.objects.create(id="scotus", name="Supreme Court")
        d = TDocket.objects.create(
            court=court, docket_number_core="456", case_name="Smith v. Jones"
        )
        TDocketEntry.objects.create(
            docket=d, entry_type="motion", description="motion to dismiss"
        )
        party = TParty.objects.create(name="John Smith")
        TPartyType.objects.create(
            docket=d, party=party, role="Defendant"
        )

        # Re-fetch and verify relationships
        fetched = TDocket.objects.get(pk=d.pk)
        self.assertEqual(fetched.entries.count(), 1)
        self.assertEqual(fetched.party_types.count(), 1)
        pt = fetched.party_types.first()
        assert pt is not None
        self.assertEqual(pt.party.name, "John Smith")
        self.assertEqual(pt.role, "Defendant")
