"""Tests for :func:`cl.scrapers.mergers.dedup.fold_lookup_refs_in_tree`.

When the same ``ExternalNodeRef`` natural key appears as multiple Python
instances (typically because a driver constructs a fresh ref per
appearance instead of caching by name), the framework folds them by
mutating the scrape tree to point at a single canonical per NK group
and reducing scalar conflicts via each field's declared strategy.

These tests exercise the tree-mutation pass directly via
:func:`fold_lookup_refs_in_tree`, then verify the resulting tree has
the expected canonical references.
"""

from typing import Annotated

from cl.scrapers.mergers import (
    Aggregate,
    CreateIfMissing,
    InternalNode,
    ExternalNodeRef,
    PreResolvedRef,
    ScrapeWins,
    ScrapeWinsIfPresent,
    Union,
    merge_one,
    parent,
)
from cl.scrapers.mergers.dedup import fold_lookup_refs_in_tree
from cl.scrapers.mergers.tests.testmodels.models import (
    TCounsel,
    TCourt,
    TDocket,
    TParty,
    TPartyType,
)
from cl.tests.cases import SimpleTestCase, TransactionTestCase


# ---------------------------------------------------------------------------
# Test schemas
# ---------------------------------------------------------------------------


class _ScrapeWinsPartyRef(
    ExternalNodeRef[TParty],
    absence_policy=CreateIfMissing,
    path_scoped=False,
):
    """Global TParty lookup with ScrapeWins on ``description`` so the
    NK-fold's last-non-equal wins semantic fires."""

    natural_key = ("name",)
    name: str
    description: Annotated[str, ScrapeWins] = ""


class _PartyTypeWithDesc(InternalNode[TPartyType]):
    natural_key = (parent.docket, "party", "role")
    party: _ScrapeWinsPartyRef
    role: str


class _CounselWithDesc(InternalNode[TCounsel]):
    natural_key = (parent.docket, "party")
    party: _ScrapeWinsPartyRef


class _AggWithDesc(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")
    court: PreResolvedRef[TCourt]
    docket_number_core: str
    party_types: Annotated[list[_PartyTypeWithDesc], Union] = []
    counsels: Annotated[list[_CounselWithDesc], Union] = []


# ---------------------------------------------------------------------------
# Direct tree-mutation tests (no Django round-trip)
# ---------------------------------------------------------------------------


class FoldExternalNodeRefsInTreeTest(SimpleTestCase):
    """Unit-level: call ``fold_lookup_refs_in_tree`` directly and
    verify the tree's parent fields are rewritten to canonicals."""

    def test_no_duplicates_returns_empty_remap(self) -> None:
        """No NK collisions → empty remap, tree untouched."""
        ref_a = _ScrapeWinsPartyRef(name="A")
        ref_b = _ScrapeWinsPartyRef(name="B")
        agg = _AggWithDesc.model_construct(
            court=None,
            docket_number_core="X",
            party_types=[
                _PartyTypeWithDesc.model_construct(party=ref_a, role="Plaintiff"),
                _PartyTypeWithDesc.model_construct(party=ref_b, role="Defendant"),
            ],
        )
        remap = fold_lookup_refs_in_tree(agg)
        self.assertEqual(remap, {})
        # References unchanged.
        self.assertIs(agg.party_types[0].party, ref_a)
        self.assertIs(agg.party_types[1].party, ref_b)

    def test_two_instances_same_nk_collapse_to_canonical(self) -> None:
        """Two distinct refs with same name fold to one canonical;
        non-canonical's slot in the tree gets rewritten."""
        ref_first = _ScrapeWinsPartyRef(name="A", description="first")
        ref_second = _ScrapeWinsPartyRef(name="A", description="second")
        agg = _AggWithDesc.model_construct(
            court=None,
            docket_number_core="X",
            party_types=[
                _PartyTypeWithDesc.model_construct(party=ref_first, role="Plaintiff"),
                _PartyTypeWithDesc.model_construct(party=ref_second, role="Amicus"),
            ],
        )
        remap = fold_lookup_refs_in_tree(agg)
        # Second was folded into first.
        self.assertEqual(remap, {id(ref_second): ref_first})
        # Both parent fields now point at ``ref_first``.
        self.assertIs(agg.party_types[0].party, ref_first)
        self.assertIs(agg.party_types[1].party, ref_first)
        # Canonical's description picked the later value (ScrapeWins).
        self.assertEqual(ref_first.description, "second")

    def test_three_instances_fold_left_to_right(self) -> None:
        """N > 2 instances reduce sequentially; all parent fields
        rewritten to point at the first instance."""
        r1 = _ScrapeWinsPartyRef(name="A", description="d1")
        r2 = _ScrapeWinsPartyRef(name="A", description="d2")
        r3 = _ScrapeWinsPartyRef(name="A", description="d3")
        agg = _AggWithDesc.model_construct(
            court=None,
            docket_number_core="X",
            party_types=[
                _PartyTypeWithDesc.model_construct(party=r1, role="P"),
                _PartyTypeWithDesc.model_construct(party=r2, role="D"),
            ],
            counsels=[_CounselWithDesc.model_construct(party=r3)],
        )
        fold_lookup_refs_in_tree(agg)
        self.assertIs(agg.party_types[0].party, r1)
        self.assertIs(agg.party_types[1].party, r1)
        self.assertIs(agg.counsels[0].party, r1)
        # ScrapeWins fold: last value wins.
        self.assertEqual(r1.description, "d3")

    def test_scrape_wins_if_present_skips_none(self) -> None:
        """When a later ref has None for an SWIP-annotated field, the
        canonical keeps the earlier non-None value."""

        class _SWIPPartyRef(
            ExternalNodeRef[TParty],
            absence_policy=CreateIfMissing,
            path_scoped=False,
        ):
            natural_key = ("name",)
            name: str
            description: Annotated[str | None, ScrapeWinsIfPresent] = None

        class _PT(InternalNode[TPartyType]):
            natural_key = (parent.docket, "party", "role")
            party: _SWIPPartyRef
            role: str

        class _Agg(Aggregate[TDocket]):
            natural_key = ("court", "docket_number_core")
            court: PreResolvedRef[TCourt]
            docket_number_core: str
            party_types: Annotated[list[_PT], Union] = []

        ref_first = _SWIPPartyRef(name="A", description="kept")
        ref_second = _SWIPPartyRef(name="A", description=None)
        agg = _Agg.model_construct(
            court=None,
            docket_number_core="X",
            party_types=[
                _PT.model_construct(party=ref_first, role="P"),
                _PT.model_construct(party=ref_second, role="D"),
            ],
        )
        fold_lookup_refs_in_tree(agg)
        self.assertEqual(ref_first.description, "kept")


# ---------------------------------------------------------------------------
# End-to-end integration: merge_one with duplicate-NK ExternalNodeRefs
# ---------------------------------------------------------------------------


class ExternalNodeRefFoldEndToEndTest(TransactionTestCase):
    """Full pipeline: a scrape with duplicate-NK ExternalNodeRef instances
    merges cleanly without creating duplicate DB rows, and the
    canonical's folded scalars land on the single DB row."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.court = TCourt.objects.create(
            id="scotus", name="Supreme Court"
        )

    def test_two_party_refs_same_name_produce_one_db_row(self) -> None:
        """Two fresh ``_ScrapeWinsPartyRef(name='Acme', ...)`` instances
        under different parent fields collapse to a single TParty row,
        with description from the LATER scrape appearance."""
        scrape = _AggWithDesc(
            court=self.court,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeWithDesc(
                    party=_ScrapeWinsPartyRef(name="Acme", description="early"),
                    role="Plaintiff",
                ),
            ],
            counsels=[
                _CounselWithDesc(
                    party=_ScrapeWinsPartyRef(name="Acme", description="late"),
                ),
            ],
        )
        merge_one(scrape, using="mergers_test")

        # Exactly one TParty for "Acme" — fold worked.
        self.assertEqual(TParty.objects.filter(name="Acme").count(), 1)
        party = TParty.objects.get(name="Acme")
        # ScrapeWins on description: later wins.
        self.assertEqual(party.description, "late")
        # Both PartyType + Counsel rows attached to the same Party.
        pt = TPartyType.objects.get()
        counsel = TCounsel.objects.get()
        self.assertEqual(pt.party_id, party.pk)
        self.assertEqual(counsel.party_id, party.pk)
