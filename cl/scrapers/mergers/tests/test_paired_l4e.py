"""Tests for L4e: three-level depth + ``allow_duplicates`` on children.

L4e refactored ``_fetch_db_children`` to use the Django related manager
on the parent (``db_docket.entries.all()``) instead of computing FK
kwargs from the child's NK. This:

- Drops the multi-level ParentPath restriction (the NK's parent-path
  elements are already skipped in the pair key, and the parent-scope
  comes from the related manager).
- Enables Django's prefetch_related caching across nested levels —
  ``Docket -> Entry -> Document`` is fetched in O(levels) queries
  rather than O(entries).

This file exercises:
1. Three-level nesting (Docket -> Entry -> Document) recurses correctly.
2. ``allow_duplicates=True`` on a child class pairs items with the same
   NK by minimum-edit-cost assignment.
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
    TCourt,
    TDocket,
    TDocketEntry,
    TDocument,
    TParty,
    TPartyType,
)
from cl.tests.cases import TransactionTestCase


# ---------------------------------------------------------------------------
# Schemas for three-level nesting
# ---------------------------------------------------------------------------


class _DocumentSchema(InternalNode[TDocument]):
    natural_key = (parent.entry, "media_id")

    media_id: str
    description: str = ""


class _EntryWithDocsSchema(InternalNode[TDocketEntry]):
    natural_key = (parent.docket, "entry_type")

    entry_type: str
    description: str = ""
    documents: list[_DocumentSchema] = []


class _DocketWithEntriesAndDocsSchema(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    entries: list[_EntryWithDocsSchema] = []


# ---------------------------------------------------------------------------
# Schemas for allow_duplicates
# ---------------------------------------------------------------------------


class _PartyRef(ExternalNodeRef[TParty]):
    natural_key = ("name",)

    name: str


class _PartyTypeDuplicatesSchema(
    InternalNode[TPartyType], allow_duplicates=True
):
    """Same NK shape as before, but duplicates are allowed — multiple
    items sharing ``(party, role)`` get paired by minimum-edit-cost on
    the non-NK ``extra_info`` field."""

    natural_key = (parent.docket, "party", "role")

    party: _PartyRef
    role: str
    extra_info: str = ""


class _DocketDuplicatesSchema(Aggregate[TDocket]):
    natural_key = ("court", "docket_number_core")

    court: PreResolvedRef[TCourt]
    docket_number_core: str
    party_types: list[_PartyTypeDuplicatesSchema] = []


# ---------------------------------------------------------------------------
# Three-level nesting
# ---------------------------------------------------------------------------


class ThreeLevelNestingTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )
        self.entry_db = TDocketEntry.objects.create(
            docket=self.docket_db, entry_type="motion"
        )
        self.doc_db = TDocument.objects.create(
            entry=self.entry_db, media_id="m-1", description="db doc"
        )

    def test_three_level_pairing(self) -> None:
        """All three levels match exactly — root, entry, document."""
        scrape = _DocketWithEntriesAndDocsSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[
                _EntryWithDocsSchema(
                    entry_type="motion",
                    documents=[
                        _DocumentSchema(media_id="m-1", description="s doc")
                    ],
                )
            ],
        )
        tree = build_paired_tree(scrape)

        # Docket level
        self.assertIsNotNone(tree.db)
        # Entry level
        entries_field = next(
            c for c in tree.children if c.name == "entries"
        )
        self.assertEqual(len(entries_field.paired), 1)
        entry_pn = entries_field.paired[0]
        self.assertIsNotNone(entry_pn.scrape)
        self.assertIsNotNone(entry_pn.db)
        # Document level
        docs_field = next(
            c for c in entry_pn.children if c.name == "documents"
        )
        self.assertEqual(len(docs_field.paired), 1)
        doc_pn = docs_field.paired[0]
        self.assertIsNotNone(doc_pn.scrape)
        self.assertIsNotNone(doc_pn.db)
        assert doc_pn.db is not None
        self.assertEqual(doc_pn.db.media_id, "m-1")

    def test_grandchild_scrape_only(self) -> None:
        """Scrape has a new document on a matched entry → grandchild is
        scrape-only."""
        scrape = _DocketWithEntriesAndDocsSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[
                _EntryWithDocsSchema(
                    entry_type="motion",
                    documents=[
                        _DocumentSchema(media_id="m-1"),
                        _DocumentSchema(media_id="m-2"),  # new
                    ],
                )
            ],
        )
        tree = build_paired_tree(scrape)
        entries_field = next(
            c for c in tree.children if c.name == "entries"
        )
        entry_pn = entries_field.paired[0]
        docs_field = next(
            c for c in entry_pn.children if c.name == "documents"
        )
        self.assertEqual(len(docs_field.paired), 2)
        scrape_only = [d for d in docs_field.paired if d.db is None]
        self.assertEqual(len(scrape_only), 1)
        assert scrape_only[0].scrape is not None
        self.assertEqual(scrape_only[0].scrape.media_id, "m-2")

    def test_grandchild_isolated_by_parent(self) -> None:
        """A document on a *different* entry must not appear in this
        entry's pairing."""
        other_entry = TDocketEntry.objects.create(
            docket=self.docket_db, entry_type="order"
        )
        TDocument.objects.create(
            entry=other_entry, media_id="other", description="other"
        )

        scrape = _DocketWithEntriesAndDocsSchema(
            court=self.scotus,
            docket_number_core="22-100",
            entries=[
                _EntryWithDocsSchema(
                    entry_type="motion",
                    documents=[_DocumentSchema(media_id="m-1")],
                )
            ],
        )
        tree = build_paired_tree(scrape)
        entries_field = next(
            c for c in tree.children if c.name == "entries"
        )
        entry_pn = entries_field.paired[0]  # the "motion" entry
        docs_field = next(
            c for c in entry_pn.children if c.name == "documents"
        )
        # Should NOT include the "other" document — it belongs to a
        # different entry, not the matched one.
        media_ids = [
            d.db.media_id for d in docs_field.paired if d.db is not None
        ]
        self.assertNotIn("other", media_ids)
        self.assertIn("m-1", media_ids)


# ---------------------------------------------------------------------------
# allow_duplicates
# ---------------------------------------------------------------------------


class AllowDuplicatesPairingTest(TransactionTestCase):
    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.scotus = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket_db = TDocket.objects.create(
            court=self.scotus, docket_number_core="22-100"
        )
        self.party_db = TParty.objects.create(name="John Smith")

    def test_two_duplicates_pair_by_min_cost(self) -> None:
        """Two scrape PartyTypes and two DB PartyTypes share the same
        (party, role) NK; pair by minimum edit cost over extra_info."""
        # DB: (extra_info="A"), (extra_info="B")
        TPartyType.objects.create(
            docket=self.docket_db,
            party=self.party_db,
            role="Defendant",
            extra_info="A",
        )
        TPartyType.objects.create(
            docket=self.docket_db,
            party=self.party_db,
            role="Defendant",
            extra_info="B",
        )

        # Scrape: (extra_info="B"), (extra_info="A")  — out of order
        scrape = _DocketDuplicatesSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeDuplicatesSchema(
                    party=_PartyRef(name="John Smith"),
                    role="Defendant",
                    extra_info="B",
                ),
                _PartyTypeDuplicatesSchema(
                    party=_PartyRef(name="John Smith"),
                    role="Defendant",
                    extra_info="A",
                ),
            ],
        )
        tree = build_paired_tree(scrape)

        pt_field = next(
            c for c in tree.children if c.name == "party_types"
        )
        # Optimal pairing: A->A (cost 0), B->B (cost 0); total cost 0.
        # Anti-optimal: A->B + B->A (cost 2).
        self.assertEqual(len(pt_field.paired), 2)
        for pn in pt_field.paired:
            self.assertIsNotNone(pn.scrape)
            self.assertIsNotNone(pn.db)
            assert pn.scrape is not None
            assert pn.db is not None
            self.assertEqual(pn.scrape.extra_info, pn.db.extra_info)

    def test_three_duplicates_unequal_buckets(self) -> None:
        """Three scrape duplicates against two DB duplicates → the
        best-matching two are paired; one scrape becomes scrape-only."""
        TPartyType.objects.create(
            docket=self.docket_db,
            party=self.party_db,
            role="Witness",
            extra_info="X",
        )
        TPartyType.objects.create(
            docket=self.docket_db,
            party=self.party_db,
            role="Witness",
            extra_info="Y",
        )

        scrape = _DocketDuplicatesSchema(
            court=self.scotus,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeDuplicatesSchema(
                    party=_PartyRef(name="John Smith"),
                    role="Witness",
                    extra_info="X",  # exact match
                ),
                _PartyTypeDuplicatesSchema(
                    party=_PartyRef(name="John Smith"),
                    role="Witness",
                    extra_info="Y",  # exact match
                ),
                _PartyTypeDuplicatesSchema(
                    party=_PartyRef(name="John Smith"),
                    role="Witness",
                    extra_info="Z",  # scrape-only
                ),
            ],
        )
        tree = build_paired_tree(scrape)

        pt_field = next(
            c for c in tree.children if c.name == "party_types"
        )
        self.assertEqual(len(pt_field.paired), 3)
        matched = [
            pn for pn in pt_field.paired
            if pn.scrape is not None and pn.db is not None
        ]
        scrape_only = [pn for pn in pt_field.paired if pn.db is None]
        self.assertEqual(len(matched), 2)
        self.assertEqual(len(scrape_only), 1)
        # The unmatched scrape must be the "Z" one.
        assert scrape_only[0].scrape is not None
        self.assertEqual(scrape_only[0].scrape.extra_info, "Z")
        # The two matched pairs have minimum total cost (0).
        for pn in matched:
            assert pn.scrape is not None
            assert pn.db is not None
            self.assertEqual(pn.scrape.extra_info, pn.db.extra_info)
