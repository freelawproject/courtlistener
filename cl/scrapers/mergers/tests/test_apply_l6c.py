"""Tests for L6c: ExternalNodeRef materialization + FK injection.

When applying a ``CreateOp`` on a node whose schema has a single
``ChildField`` pointing to a ``ExternalNodeRef``, the framework:

1. Processes the ExternalNodeRef *first* (so its PK is available).
   - ``CreateIfMissing`` (default): if no DB match, create the row.
   - ``ErrorIfMissing``: raise.
   - ``NoopIfMissing``: skip; leave parent FK null.
2. Injects the resolved/created ExternalNodeRef instance into the parent's
   create kwargs as the FK value.

Shared scrape refs (one ``_PartyRef`` instance referenced by multiple
parent rows) are materialized once and reused via an internal cache
keyed by ``id(scrape_ref)``.
"""

from typing import Annotated

from cl.scrapers.mergers.apply import apply
from cl.scrapers.mergers.diff import reconcile
from cl.scrapers.mergers.nodes import (
    Aggregate,
    ErrorIfMissing,
    InternalNode,
    ExternalNodeRef,
    PreResolvedRef,
)
from cl.scrapers.mergers.paired import build_paired_tree
from cl.scrapers.mergers.refs import parent
from cl.scrapers.mergers.strategies import ScrapeWins
from cl.scrapers.mergers.tests.testmodels.models import (
    TCourt,
    TDocket,
    TParty,
    TPartyType,
)
from cl.tests.cases import TransactionTestCase


def _pipeline(scrape):
    return apply(reconcile(build_paired_tree(scrape)))


# ---------------------------------------------------------------------------
# Schemas (CreateIfMissing — the default)
# ---------------------------------------------------------------------------


class _PartyRef(ExternalNodeRef[TParty]):
    natural_key = ("name",)

    name: str


class _PartyTypeSchema(InternalNode[TPartyType]):
    natural_key = (parent.docket, "party", "role")

    party: _PartyRef
    role: str
    extra_info: str = ""


class _DocketSchema(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    party_types: list[_PartyTypeSchema] = []


# ---------------------------------------------------------------------------
# Schemas (ErrorIfMissing)
# ---------------------------------------------------------------------------


class _StrictPartyRef(
    ExternalNodeRef[TParty], absence_policy=ErrorIfMissing
):
    natural_key = ("name",)
    name: str


class _StrictPartyTypeSchema(InternalNode[TPartyType]):
    natural_key = (parent.docket, "party", "role")
    party: _StrictPartyRef
    role: str


class _StrictDocketSchema(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")
    court: PreResolvedRef[TCourt]
    docket_number_core: str
    party_types: list[_StrictPartyTypeSchema] = []


# ---------------------------------------------------------------------------
# CreateIfMissing
# ---------------------------------------------------------------------------


class CreateIfMissingTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_party_created_then_party_type(self) -> None:
        """New Party gets created; PartyType is created with party FK
        set to the new Party."""
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeSchema(
                    party=_PartyRef(name="John Smith"), role="Defendant"
                )
            ],
        )
        outcome = _pipeline(scrape)

        # Party row exists
        party = TParty.objects.get(name="John Smith")
        # PartyType row exists with FK pointing to it
        pt = TPartyType.objects.get(role="Defendant")
        self.assertEqual(pt.party_id, party.pk)
        # Both PKs appear in outcome.creates under their respective models
        self.assertIn(party.pk, outcome.creates.get(TParty, set()))
        self.assertIn(pt.pk, outcome.creates.get(TPartyType, set()))

    def test_existing_party_is_reused_not_recreated(self) -> None:
        """If the DB already has a Party with the scraped name on this
        docket (via another PartyType), reuse it."""
        existing = TParty.objects.create(name="John Smith")
        docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )
        TPartyType.objects.create(
            docket=docket_db, party=existing, role="Witness"
        )

        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeSchema(
                    party=_PartyRef(name="John Smith"), role="Witness"
                ),  # matches existing
                _PartyTypeSchema(
                    party=_PartyRef(name="John Smith"), role="Defendant"
                ),  # same Party, new role
            ],
        )
        outcome = _pipeline(scrape)

        # Still only one Party
        self.assertEqual(TParty.objects.filter(name="John Smith").count(), 1)
        # No new Party row created
        self.assertNotIn(TParty, outcome.creates)
        # One new PartyType created (Defendant); Witness was already there
        self.assertEqual(
            TPartyType.objects.filter(party=existing).count(), 2
        )


class SharedScrapeRefTest(TransactionTestCase):
    """One ``_PartyRef`` instance referenced by multiple PartyTypes →
    we create the Party once and use it for both."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_shared_lookup_ref_creates_party_once(self) -> None:
        shared = _PartyRef(name="John Smith")
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeSchema(party=shared, role="Plaintiff"),
                _PartyTypeSchema(party=shared, role="Witness"),
            ],
        )
        outcome = _pipeline(scrape)

        # Exactly one Party row
        parties = TParty.objects.filter(name="John Smith")
        self.assertEqual(parties.count(), 1)
        only_party = parties.first()
        assert only_party is not None

        # Both PartyTypes point to it
        pts = TPartyType.objects.filter(party=only_party)
        self.assertEqual(pts.count(), 2)
        self.assertSetEqual(
            {pt.role for pt in pts}, {"Plaintiff", "Witness"}
        )

        # outcome.creates[TParty] has exactly that one PK
        self.assertEqual(outcome.creates.get(TParty), {only_party.pk})


# ---------------------------------------------------------------------------
# ExternalNodeRef field-update on matched rows
# ---------------------------------------------------------------------------


class _UpdatingPartyRef(ExternalNodeRef[TParty]):
    """ExternalNodeRef whose non-NK ``description`` field is explicitly
    ``ScrapeWins`` so a matched row picks up the new value on re-merge.

    ``ExternalNodeRef``'s class default is ``DBWins`` (existing rows keep
    their values), so we need an explicit per-field override to
    exercise the update path.
    """

    natural_key = ("name",)

    name: str
    description: Annotated[str, ScrapeWins] = ""


class _UpdatingPartyTypeSchema(InternalNode[TPartyType]):
    natural_key = (parent.docket, "party", "role")

    party: _UpdatingPartyRef
    role: str


class _UpdatingDocketSchema(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    party_types: list[_UpdatingPartyTypeSchema] = []


class MatchedExternalNodeRefFieldUpdateTest(TransactionTestCase):
    """A matched ExternalNodeRef whose non-NK field has ``ScrapeWins``
    semantics must actually get its row updated. Pre-fix, the framework
    early-returned the matched DB row from
    ``_materialize_one_lookup_ref`` without ever applying the diff's
    field changes."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )
        self.party_db = TParty.objects.create(
            name="John Smith", description="stale"
        )
        TPartyType.objects.create(
            docket=self.docket_db, party=self.party_db, role="Defendant"
        )

    def test_matched_ExternalNodeRef_writes_scrape_wins_field(self) -> None:
        scrape = _UpdatingDocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _UpdatingPartyTypeSchema(
                    party=_UpdatingPartyRef(
                        name="John Smith", description="fresh"
                    ),
                    role="Defendant",
                ),
            ],
        )
        outcome = _pipeline(scrape)

        self.party_db.refresh_from_db()
        self.assertEqual(self.party_db.description, "fresh")
        self.assertIn(self.party_db.pk, outcome.updates.get(TParty, set()))

    def test_matched_ExternalNodeRef_no_change_is_noop(self) -> None:
        """When scrape matches DB exactly, no update is recorded."""
        scrape = _UpdatingDocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _UpdatingPartyTypeSchema(
                    party=_UpdatingPartyRef(
                        name="John Smith", description="stale"
                    ),
                    role="Defendant",
                ),
            ],
        )
        outcome = _pipeline(scrape)
        self.assertNotIn(TParty, outcome.updates)


# ---------------------------------------------------------------------------
# ErrorIfMissing
# ---------------------------------------------------------------------------


class ErrorIfMissingTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")

    def test_raises_when_party_not_in_db(self) -> None:
        scrape = _StrictDocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _StrictPartyTypeSchema(
                    party=_StrictPartyRef(name="Nonexistent"),
                    role="Defendant",
                ),
            ],
        )
        with self.assertRaises(ValueError):
            _pipeline(scrape)

    def test_succeeds_when_party_exists(self) -> None:
        existing = TParty.objects.create(name="Existing")
        docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )
        # Need an existing PartyType linking Existing to this docket so
        # the path-scoped ExternalNodeRef resolution in L4 finds it.
        TPartyType.objects.create(
            docket=docket_db, party=existing, role="Witness"
        )

        scrape = _StrictDocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _StrictPartyTypeSchema(
                    party=_StrictPartyRef(name="Existing"),
                    role="Defendant",  # new role, not yet in DB
                ),
            ],
        )
        outcome = _pipeline(scrape)
        # Defendant PartyType is new; Party itself is reused.
        self.assertNotIn(TParty, outcome.creates)
        pt = TPartyType.objects.get(party=existing, role="Defendant")
        self.assertIn(pt.pk, outcome.creates.get(TPartyType, set()))
