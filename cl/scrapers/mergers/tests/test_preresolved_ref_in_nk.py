"""Tests for ``PreResolvedRef``-in-NK support on ``BridgeNode`` /
non-path-scoped ``ExternalNodeRef``.

Background: the SCOTUS/Texas ``CaseTransfer`` schemas declare a
six-tuple NK that includes two ``PreResolvedRef[Court]`` fields
(``origin_court``, ``destination_court``). Before
``_nk_elements_for_lookup`` accepted ``SiblingRef`` with a
``preresolved_model``, those NK elements tripped a
``NotImplementedError`` and the merger fell over on the first
CaseTransfer scrape.

The fix shapes the NK-extraction helpers so:

- ``_nk_elements_for_lookup``: ``OwnScalar`` and ``SiblingRef`` with
  ``preresolved_model != None`` are both accepted; other variants
  still raise (intentional — they need a separate resolution round).
- ``_scrape_nk_value``: returns the Django instance's ``pk`` for the
  preresolved variant so it lines up with…
- ``_db_nk_value``: reads ``<field>_id`` directly (no related fetch).
- ``_orm_field_key``: emits ``<field>_id`` in the ORM filter, accepting
  raw PKs without triggering Django's "you must pass a model
  instance" coercion.

The tests cover the BridgeNode end-to-end path (global lookup +
match + auto-injected parent FK) with a NK that includes a
``PreResolvedRef[TParty]``.
"""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from cl.scrapers.mergers import (
    Aggregate,
    BridgeNode,
    PreResolvedRef,
    apply,
    build_paired_tree,
    merge_one,
    reconcile,
)
from cl.scrapers.mergers.tests.testmodels.models import (
    TCounsel,
    TCourt,
    TDocket,
    TParty,
)
from cl.tests.cases import TransactionTestCase


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class _PartyBridge(BridgeNode[TCounsel]):
    """Global-NK lookup of a ``TCounsel`` by its ``party`` FK. The
    NK is a single ``PreResolvedRef[TParty]`` field, exercising the
    SiblingRef-preresolved code path in ``_nk_elements_for_lookup``.

    The ``docket`` parent FK is auto-injected from the parent's
    ``counsels`` reverse-accessor name (BridgeNode mechanism)."""

    natural_key = ("party",)

    party: PreResolvedRef[TParty]


class _DocketWithPartyBridges(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    # Pydantic field name matches Django's reverse-accessor for
    # ``TCounsel.docket`` (``related_name="counsels"``).
    counsels: list[_PartyBridge] = []


def _pipeline(scrape):
    return apply(reconcile(build_paired_tree(scrape)))


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class PreResolvedRefInNKUnitTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )
        # Three parties to give the global lookup something to
        # disambiguate against.
        self.party_a = TParty.objects.create(name="Party A")
        self.party_b = TParty.objects.create(name="Party B")
        self.party_c = TParty.objects.create(name="Party C")

    def test_global_lookup_matches_by_preresolved_party_fk(self) -> None:
        """Pre-create a TCounsel for party_b on a different docket;
        the BridgeNode's global lookup should find it by party FK
        (not by docket scope)."""
        other_docket = TDocket.objects.create(
            court=self.scotus, docket_number_core="OTHER"
        )
        existing = TCounsel.objects.create(
            docket=other_docket, party=self.party_b
        )

        scrape = _DocketWithPartyBridges(
            court=self.scotus,
            docket_number_core="22-100",
            counsels=[_PartyBridge(party=self.party_b)],
        )
        outcome = _pipeline(scrape)

        # Same row reused (no new TCounsel created).
        self.assertEqual(TCounsel.objects.count(), 1)
        existing.refresh_from_db()
        # The row's ``docket`` FK gets filled by the BridgeNode
        # parent-FK auto-injection.
        self.assertEqual(existing.docket_id, self.docket.pk)
        self.assertIn(existing.pk, outcome.updates.get(TCounsel, set()))

    def test_global_lookup_creates_when_no_party_match(self) -> None:
        """No DB TCounsel with party_a → CreateIfMissing inserts one
        and auto-injects the parent docket FK."""
        scrape = _DocketWithPartyBridges(
            court=self.scotus,
            docket_number_core="22-100",
            counsels=[_PartyBridge(party=self.party_a)],
        )
        outcome = _pipeline(scrape)

        new_row = TCounsel.objects.get(party=self.party_a)
        self.assertEqual(new_row.docket_id, self.docket.pk)
        self.assertIn(new_row.pk, outcome.creates.get(TCounsel, set()))

    def test_global_lookup_disambiguates_by_party_fk(self) -> None:
        """Multiple TCounsels in the DB for different parties: only
        the matching one is paired."""
        TCounsel.objects.create(docket=self.docket, party=self.party_a)
        TCounsel.objects.create(docket=self.docket, party=self.party_b)
        target = TCounsel.objects.create(
            docket=self.docket, party=self.party_c
        )

        scrape = _DocketWithPartyBridges(
            court=self.scotus,
            docket_number_core="22-100",
            counsels=[_PartyBridge(party=self.party_c)],
        )
        _pipeline(scrape)

        # Only party_c's TCounsel was touched.
        target.refresh_from_db()
        self.assertEqual(target.docket_id, self.docket.pk)
        # All three rows still exist (Union semantics on BridgeNode).
        self.assertEqual(TCounsel.objects.count(), 3)


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class PreResolvedRefInNKPropertyTest(HypothesisTestCase):
    """Property: for any set of pre-existing TCounsel rows keyed by
    party, scraping a subset of those parties' refs resolves each
    exactly to its DB row (or creates a new row when the party isn't
    in the DB yet).

    Hypothesis picks a random subset of parties to pre-create and a
    random (possibly overlapping) subset to scrape. The invariant:
    after the merge, every scraped party has exactly one TCounsel
    on the docket.
    """

    databases = {"mergers_test"}

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        # Pre-create a fixed party pool so each example draws from a
        # known set. Five parties give plenty of resolution variety
        # without slowing the test.
        cls.parties = [
            TParty.objects.create(name=f"Party {label}")
            for label in ("A", "B", "C", "D", "E")
        ]

    @given(
        db_indices=st.sets(
            st.integers(min_value=0, max_value=4), max_size=5
        ),
        scrape_indices=st.sets(
            st.integers(min_value=0, max_value=4), max_size=5
        ),
    )
    @settings(
        max_examples=40,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_scrape_parties_resolve_to_distinct_rows(
        self, db_indices: set[int], scrape_indices: set[int]
    ) -> None:
        docket = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )

        # Pre-populate the DB.
        for i in db_indices:
            TCounsel.objects.create(docket=docket, party=self.parties[i])

        # Build the scrape.
        scrape = _DocketWithPartyBridges(
            court=self.scotus,
            docket_number_core="22-100",
            counsels=[
                _PartyBridge(party=self.parties[i])
                for i in sorted(scrape_indices)
            ],
        )
        merge_one(scrape, using="mergers_test")

        # Invariant: every scraped party now has exactly one TCounsel
        # on the docket, with the correct party FK.
        for i in scrape_indices:
            counsels = TCounsel.objects.filter(
                docket=docket, party=self.parties[i]
            )
            self.assertEqual(
                counsels.count(),
                1,
                f"Scraped party {self.parties[i].name} should map to "
                f"exactly one TCounsel on the docket; got "
                f"{counsels.count()}.",
            )
