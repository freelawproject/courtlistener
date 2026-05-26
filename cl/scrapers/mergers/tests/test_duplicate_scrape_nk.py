"""Minimal reproduction: a scrape with two ``InternalNode`` children
whose natural keys (parent_pk + ExternalNodeRef.nk) collide currently raises
``ValueError: duplicate scrape natural key`` from
:func:`pair_by_nk`.

Surfaced in the wild by the SCOTUS parity Hypothesis test, where the
same attorney appears under two different parties on one docket. The
driver emits one ``ScotusAttorneyOrgAssociationSchema`` per
party-attorney pair; when both rows have the same ``(attorney_name,
attorney_organization_lookup_key)`` the natural keys collide.

The framework error is independent of how many ExternalNodeRef fields the NK
contains — this test uses a single-ExternalNodeRef join (TCounsel) for the
minimal shape. The same code path
(:func:`cl.scrapers.mergers.reconcile.pair_by_nk`) handles the
multi-ExternalNodeRef SCOTUS case.

This test asserts the *desired* behavior: two scrape rows with
identical natural keys collapse to a single create (idempotent —
emitting the same row twice should be equivalent to emitting it
once). With the current framework, the test fails because
``pair_by_nk`` raises before reaching apply.
"""

from cl.scrapers.mergers import (
    Aggregate,
    CreateIfMissing,
    InternalNode,
    ExternalNodeRef,
    PreResolvedRef,
    Union,
    merge_one,
    parent,
)
from cl.scrapers.mergers.tests.testmodels.models import (
    TCounsel,
    TCourt,
    TDocket,
    TParty,
)
from cl.tests.cases import TransactionTestCase
from typing import Annotated


# ---------------------------------------------------------------------------
# Test schemas
# ---------------------------------------------------------------------------


class _PartyRef(
    ExternalNodeRef[TParty],
    absence_policy=CreateIfMissing,
    path_scoped=False,
):
    """Global ``TParty`` lookup by name."""

    natural_key = ("name",)

    name: str


class _CounselSchema(InternalNode[TCounsel]):
    """A join row keyed by ``(parent.docket, party)``. The party
    component is a ExternalNodeRef whose unresolved NK is part of the join's
    NK — so two ``_CounselSchema`` instances referencing the same
    ``TParty`` name share an identical natural-key tuple.
    """

    natural_key = (parent.docket, "party")

    party: _PartyRef


class _DocketSchema(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    # ``Union`` so the collection strategy is well-defined for the
    # collide-on-NK case (no DB-only deletions to worry about).
    counsels: Annotated[list[_CounselSchema], Union] = []


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class DuplicateScrapeNKTest(TransactionTestCase):
    """Two scrape rows with the same NK should resolve to a single
    create — currently the framework raises instead."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.court = TCourt.objects.create(
            id="scotus", name="Supreme Court"
        )

    def test_duplicate_scrape_nk_collapses_to_single_row(self) -> None:
        """Two ``_CounselSchema`` instances with the same resolved
        ``(docket, party)`` should produce exactly one ``TCounsel``
        row, not raise.

        Currently fails with::

            ValueError: duplicate scrape natural key:
              (None, ('__unresolved__', 'Acme'))
        """
        # Build a scrape with two counsels that share a party. The
        # framework will see two _CounselSchema rows both keying off
        # the same (parent.docket, TParty(name='Acme')) tuple.
        scrape = _DocketSchema(
            court=self.court,
            docket_number_core="22-100",
            counsels=[
                _CounselSchema(party=_PartyRef(name="Acme")),
                _CounselSchema(party=_PartyRef(name="Acme")),
            ],
        )

        outcome = merge_one(scrape, using="mergers_test")

        # Exactly one TCounsel created (the duplicate scrape row is
        # idempotent — same logical row emitted twice).
        self.assertEqual(TCounsel.objects.count(), 1)
        # The single row points at the party that was scraped.
        only = TCounsel.objects.get()
        self.assertEqual(only.party.name, "Acme")
        self.assertIn(
            only.pk, outcome.creates.get(TCounsel, set())
        )
