"""Tests for L4d: ExternalNodeRef pairing + SiblingRef in InternalNode NKs.

This sub-cycle covers:
- A ``ChildField`` pointing to a ``ExternalNodeRef``: the ExternalNodeRef is paired
  against the DB by its own NK. Unmatched scrape refs are recorded as
  ``PairedNode(scrape=ref, db=None)`` — phase 4 will create them under
  ``CreateIfMissing``.
- ``SiblingRef`` elements in an ``InternalNode``'s NK: the framework
  pre-resolves the referenced ExternalNodeRef so the resolved DB PK can be
  used as part of the pairing key.

Strategy: one batched query per ExternalNodeRef class collected from the
scrape tree (no N+1).
"""

from cl.scrapers.mergers.nodes import (
    Aggregate,
    InternalNode,
    ExternalNodeRef,
    PreResolvedRef,
)
from cl.scrapers.mergers.paired import build_paired_tree
from cl.scrapers.mergers.refs import parent
from cl.scrapers.mergers.tests.testmodels.models import (
    TCounsel,
    TCourt,
    TDocket,
    TParty,
    TPartyType,
)
from cl.tests.cases import TransactionTestCase


# ---------------------------------------------------------------------------
# Test schemas
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
# ExternalNodeRef pairing (CreateIfMissing semantics)
# ---------------------------------------------------------------------------


class ExternalNodeRefPairingTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )

    def test_ExternalNodeRef_matches_existing_party(self) -> None:
        existing_party = TParty.objects.create(name="John Smith")
        TPartyType.objects.create(
            docket=self.docket_db, party=existing_party, role="Defendant"
        )

        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeSchema(
                    party=_PartyRef(name="John Smith"), role="Defendant"
                )
            ],
        )
        tree = build_paired_tree(scrape)

        # The party_types child has one matched pair
        pt_field = next(
            cn for cn in tree.children if cn.name == "party_types"
        )
        self.assertEqual(len(pt_field.paired), 1)
        pt = pt_field.paired[0]
        self.assertIsNotNone(pt.scrape)
        self.assertIsNotNone(pt.db)

        # The party_types matched node has a 'party' child showing the
        # resolved ExternalNodeRef
        party_field = next(
            cn for cn in pt.children if cn.name == "party"
        )
        self.assertEqual(len(party_field.paired), 1)
        party_pn = party_field.paired[0]
        self.assertIsNotNone(party_pn.scrape)
        self.assertIsNotNone(party_pn.db)
        assert party_pn.db is not None
        self.assertEqual(party_pn.db.pk, existing_party.pk)

    def test_ExternalNodeRef_no_db_match_is_create_candidate(self) -> None:
        """Scrape party 'New Person' doesn't exist in DB → PairedNode
        has scrape set, db None."""
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeSchema(
                    party=_PartyRef(name="New Person"), role="Defendant"
                )
            ],
        )
        tree = build_paired_tree(scrape)

        pt_field = next(
            cn for cn in tree.children if cn.name == "party_types"
        )
        # PartyType itself is scrape-only (no matching DB row)
        self.assertEqual(len(pt_field.paired), 1)
        pt = pt_field.paired[0]
        self.assertIsNotNone(pt.scrape)
        self.assertIsNone(pt.db)

        # The party ExternalNodeRef under it is also scrape-only
        party_field = next(
            cn for cn in pt.children if cn.name == "party"
        )
        self.assertEqual(len(party_field.paired), 1)
        party_pn = party_field.paired[0]
        self.assertIsNotNone(party_pn.scrape)
        self.assertIsNone(party_pn.db)


class GlobalExternalNodeRefTest(TransactionTestCase):
    """``ExternalNodeRef`` declared with ``path_scoped=False`` resolves via a
    batched global query, *not* a prefetch walk from the root. Used for
    rows with globally-unique NKs (e.g.,
    ``AttorneyOrganization.lookup_key``) or that span aggregates
    (``CaseTransfer``)."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )

    def test_global_lookup_finds_row_unreachable_from_root(self) -> None:
        """A TParty exists in the DB but is NOT reachable from this
        docket via any prefetch path (no PartyType, no Counsel). A
        path-scoped ExternalNodeRef would miss it; ``path_scoped=False``
        finds it via a global query."""

        class _GlobalPartyRef(
            ExternalNodeRef[TParty], path_scoped=False
        ):
            natural_key = ("name",)
            name: str

        class _PartyTypeWithGlobalRef(InternalNode[TPartyType]):
            natural_key = (parent.docket, "party", "role")
            party: _GlobalPartyRef
            role: str

        class _DocketWithGlobalRef(Aggregate[TDocket]):
            natural_key = ("court", "docket_number_core")
            court: PreResolvedRef[TCourt]
            docket_number_core: str
            party_types: list[_PartyTypeWithGlobalRef] = []

        # Party exists in DB but has no relation to this docket.
        unrelated_party = TParty.objects.create(name="Standalone")

        scrape = _DocketWithGlobalRef(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeWithGlobalRef(
                    party=_GlobalPartyRef(name="Standalone"),
                    role="Defendant",
                ),
            ],
        )
        tree = build_paired_tree(scrape)

        pt_field = next(
            cn for cn in tree.children if cn.name == "party_types"
        )
        party_field = next(
            cn for cn in pt_field.paired[0].children if cn.name == "party"
        )
        # Global lookup finds the unrelated party.
        assert party_field.paired[0].db is not None
        self.assertEqual(party_field.paired[0].db.pk, unrelated_party.pk)


class SiblingRefKeyingTest(TransactionTestCase):
    """The interesting case: PartyType's NK is (parent.docket, "party",
    "role"). For pairing, we need the resolved party PK. Verify the
    pairing uses it correctly."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )

    def test_same_party_different_roles_keys_distinct(self) -> None:
        """Two PartyTypes for the same party with different roles must
        be distinct keys (no collision)."""
        party_db = TParty.objects.create(name="John Smith")
        TPartyType.objects.create(
            docket=self.docket_db, party=party_db, role="Defendant"
        )
        TPartyType.objects.create(
            docket=self.docket_db, party=party_db, role="Witness"
        )

        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeSchema(
                    party=_PartyRef(name="John Smith"), role="Defendant"
                ),
                _PartyTypeSchema(
                    party=_PartyRef(name="John Smith"), role="Witness"
                ),
            ],
        )
        tree = build_paired_tree(scrape)

        pt_field = next(
            cn for cn in tree.children if cn.name == "party_types"
        )
        self.assertEqual(len(pt_field.paired), 2)
        # Both should be matched (scrape + db both set)
        for pn in pt_field.paired:
            self.assertIsNotNone(pn.scrape)
            self.assertIsNotNone(pn.db)

    def test_different_parties_same_role_keys_distinct(self) -> None:
        """Two PartyTypes with same role but different parties must
        pair correctly to their respective DB rows."""
        party_a = TParty.objects.create(name="A")
        party_b = TParty.objects.create(name="B")
        pt_a_db = TPartyType.objects.create(
            docket=self.docket_db, party=party_a, role="Defendant"
        )
        pt_b_db = TPartyType.objects.create(
            docket=self.docket_db, party=party_b, role="Defendant"
        )

        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeSchema(
                    party=_PartyRef(name="A"), role="Defendant"
                ),
                _PartyTypeSchema(
                    party=_PartyRef(name="B"), role="Defendant"
                ),
            ],
        )
        tree = build_paired_tree(scrape)

        pt_field = next(
            cn for cn in tree.children if cn.name == "party_types"
        )
        self.assertEqual(len(pt_field.paired), 2)

        # Match by Party name to verify the right DB row was paired
        by_name = {pn.scrape.party.name: pn.db for pn in pt_field.paired}
        self.assertEqual(by_name["A"].pk, pt_a_db.pk)
        self.assertEqual(by_name["B"].pk, pt_b_db.pk)

    def test_scrape_party_missing_in_db_does_not_match_other_partytype(
        self,
    ) -> None:
        """When the scrape party doesn't exist in DB, the scrape
        PartyType is scrape-only and the DB PartyType is db-only —
        they must not falsely pair."""
        existing_party = TParty.objects.create(name="Existing")
        TPartyType.objects.create(
            docket=self.docket_db, party=existing_party, role="Defendant"
        )

        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeSchema(
                    party=_PartyRef(name="New"), role="Defendant"
                ),
            ],
        )
        tree = build_paired_tree(scrape)

        pt_field = next(
            cn for cn in tree.children if cn.name == "party_types"
        )
        self.assertEqual(len(pt_field.paired), 2)
        scrape_only = [pn for pn in pt_field.paired if pn.db is None]
        db_only = [pn for pn in pt_field.paired if pn.scrape is None]
        self.assertEqual(len(scrape_only), 1)
        self.assertEqual(len(db_only), 1)

    def test_party_in_other_docket_is_not_matched(self) -> None:
        """A Party that exists in the DB but is only related to a
        *different* docket must NOT be matched for this docket's
        scrape — ExternalNodeRef resolution is scoped via the path from
        root."""
        other_docket = TDocket.objects.create(
            court=self.scotus, docket_number_core="OTHER"
        )
        other_party = TParty.objects.create(name="John Smith")
        TPartyType.objects.create(
            docket=other_docket, party=other_party, role="Defendant"
        )
        # This docket has no PartyTypes (so no related parties).

        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeSchema(
                    party=_PartyRef(name="John Smith"), role="Defendant"
                )
            ],
        )
        tree = build_paired_tree(scrape)

        pt_field = next(
            cn for cn in tree.children if cn.name == "party_types"
        )
        # Scrape PartyType is scrape-only (no matching DB row on THIS docket).
        self.assertEqual(len(pt_field.paired), 1)
        pt = pt_field.paired[0]
        self.assertIsNotNone(pt.scrape)
        self.assertIsNone(pt.db)

        # The Party ref is also unresolved — even though a Party named
        # "John Smith" exists, it's not related to this docket.
        party_field = next(
            cn for cn in pt.children if cn.name == "party"
        )
        party_pn = party_field.paired[0]
        self.assertIsNotNone(party_pn.scrape)
        self.assertIsNone(party_pn.db)

    def test_ExternalNodeRef_class_reachable_via_two_paths(self) -> None:
        """Same ExternalNodeRef class reachable from the root via *two*
        distinct paths (here: ``party_types__party`` and
        ``counsels__party``) must resolve via either path, not just
        the last one schema-walking happens to register. This
        exercises the fix for the path-overwrite framework gap."""

        class _CounselSchema(InternalNode[TCounsel]):
            natural_key = (parent.docket, "party")

            party: _PartyRef

        class _DocketWithCounselsSchema(Aggregate[TDocket]):
            natural_key = ("court", "docket_number_core")

            court: PreResolvedRef[TCourt]
            docket_number_core: str
            party_types: list[_PartyTypeSchema] = []
            counsels: list[_CounselSchema] = []

        # Two parties exist in DB on this docket. Crucially, each is
        # reachable from the docket via *only one* of the two paths:
        # ``via_pt`` is in party_types but not counsels; ``via_counsel``
        # is in counsels but not party_types.
        via_pt = TParty.objects.create(name="From PartyTypes")
        via_counsel = TParty.objects.create(name="From Counsels")
        TPartyType.objects.create(
            docket=self.docket_db, party=via_pt, role="Plaintiff"
        )
        TCounsel.objects.create(docket=self.docket_db, party=via_counsel)

        scrape = _DocketWithCounselsSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeSchema(
                    party=_PartyRef(name="From PartyTypes"), role="Plaintiff"
                ),
            ],
            counsels=[
                _CounselSchema(party=_PartyRef(name="From Counsels")),
            ],
        )
        tree = build_paired_tree(scrape)

        # PartyTypes side: the scrape ref must resolve to the DB row
        # reachable via the party_types path.
        pt_field = next(
            cn for cn in tree.children if cn.name == "party_types"
        )
        pt_party = next(
            cn for cn in pt_field.paired[0].children if cn.name == "party"
        )
        assert pt_party.paired[0].db is not None
        self.assertEqual(pt_party.paired[0].db.pk, via_pt.pk)

        # Counsels side: the scrape ref must resolve to the DB row
        # reachable via the counsels path. Before the fix this would be
        # None because the path-by-class dict had been overwritten.
        counsels_field = next(
            cn for cn in tree.children if cn.name == "counsels"
        )
        c_party = next(
            cn
            for cn in counsels_field.paired[0].children
            if cn.name == "party"
        )
        assert c_party.paired[0].db is not None
        self.assertEqual(c_party.paired[0].db.pk, via_counsel.pk)

    def test_shared_ExternalNodeRef_resolved_once(self) -> None:
        """When the same Party is referenced by multiple PartyTypes,
        both should resolve to the same DB row."""
        party_db = TParty.objects.create(name="John")
        TPartyType.objects.create(
            docket=self.docket_db, party=party_db, role="Plaintiff"
        )
        TPartyType.objects.create(
            docket=self.docket_db, party=party_db, role="Counsel"
        )

        shared_ref = _PartyRef(name="John")
        scrape = _DocketSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeSchema(party=shared_ref, role="Plaintiff"),
                _PartyTypeSchema(party=shared_ref, role="Counsel"),
            ],
        )
        tree = build_paired_tree(scrape)

        pt_field = next(
            cn for cn in tree.children if cn.name == "party_types"
        )
        # Both should be matched
        for pn in pt_field.paired:
            self.assertIsNotNone(pn.scrape)
            self.assertIsNotNone(pn.db)
            # The party child of each should point to the same DB row
            party_field = next(
                cn for cn in pn.children if cn.name == "party"
            )
            party_pn = party_field.paired[0]
            assert party_pn.db is not None
            self.assertEqual(party_pn.db.pk, party_db.pk)
