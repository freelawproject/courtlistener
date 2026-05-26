"""Texas docket-merger driver tests, targeting real PostgreSQL.

These tests exercise the new driver
(:mod:`cl.scrapers.mergers.state.texas.driver`) plus the merger
framework against the production CL schema (``Docket``, ``CaseTransfer``,
``OriginatingCourtInformation``, etc.) rather than the in-memory sqlite
test models used by the framework's own unit tests.

What we keep from the legacy ``TexasMergerTest`` (in
``cl.corpus_importer.tests``) and what we drop:

- **Kept**: end-to-end docket-merge behaviors, CaseTransfer routing
  decisions, OCI / TrialCourtData / appeal_from resolution, party-and-
  attorney creation, the entries-with-appellate-brief pairing
  integration, and the ``download_attachments=False`` knob.
- **Dropped**: tests of legacy helpers that no longer exist
  (``normalize_texas_parties``, ``merge_texas_document``,
  ``merge_texas_docket_entry``). The new merger doesn't expose
  single-row entry points and the NK/edit-cost pairing that subsumes
  the legacy "match by sequence number" branch is covered by
  ``cl.scrapers.mergers.tests`` against the test models.

The legacy tests asserted on a ``MergeResult`` keyed by *string* model
names; the new framework returns ``MergeOutcome`` keyed by *Model
classes*. Most ports translate ``result.creates["Docket"]`` →
``outcome.creates.get(Docket, set())``.
"""

from datetime import date
from typing import Any

from juriscraper.state.texas.common import CourtID, CourtType

from cl.lib.model_helpers import make_texas_docket_number_core
from cl.people_db.factories import PersonFactory, PositionFactory
from cl.people_db.models import Attorney, Party, PartyType, Person, Role
from cl.scrapers.mergers.state.texas.driver import merge_texas_docket
from cl.search.factories import (
    CaseTransferFactory,
    CourtFactory,
    DocketFactory,
)
from cl.search.models import (
    CaseTransfer,
    Docket,
    OriginatingCourtInformation,
    TrialCourtData,
)
from cl.search.state.texas.factories import (
    TexasAppellateBriefDictFactory,
    TexasAppellateCourtInfoDictFactory,
    TexasAppellateTransferDictFactory,
    TexasCaseDocumentDictFactory,
    TexasCaseEventDictFactory,
    TexasCasePartyDictFactory,
    TexasCourtOfAppealsDocketDictFactory,
    TexasFinalCourtDocketDictFactory,
    TexasOriginatingCourtDictFactory,
    TexasOriginatingDistrictCourtDictFactory,
    TexasSupremeCourtAppellateBriefDictFactory,
    TexasSupremeCourtCaseEventDictFactory,
)
from cl.search.state.texas.models import TexasDocketEntry
from cl.tests.cases import TestCase
from cl.tests.providers import fake


_FOLLOWUP_DOWNLOAD = "texas-document-download-and-extract"


def _empty_originating() -> dict[str, Any]:
    """An originating-court block with UNKNOWN court_type so OCI,
    TrialCourtData, and CaseTransfer all short-circuit to "nothing to
    do" — useful for tests that want to isolate one part of the flow.
    """
    return TexasOriginatingCourtDictFactory(
        court_type=CourtType.UNKNOWN.value,
        case="",
    )


class TexasDriverTest(TestCase):
    """Driver tests against the real PG database.

    Setup mirrors the legacy ``TexasMergerTest``: a handful of Texas
    courts pre-created via ``CourtFactory`` and one existing
    ``Docket`` row on the first court of appeals so update-path tests
    can pin against a known PK.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.texas_sc = CourtFactory.create(id="tex")
        cls.texas_cca = CourtFactory.create(id="texcrimapp")
        cls.texas_coa1 = CourtFactory.create(id="txctapp1")
        cls.texas_dc100 = CourtFactory.create(id="texdistct101")
        cls.docket_number_coa1 = "01-25-00011-CV"
        cls.docket_coa1 = DocketFactory.create(
            court=cls.texas_coa1,
            docket_number=cls.docket_number_coa1,
            docket_number_core=make_texas_docket_number_core(
                cls.docket_number_coa1
            ),
        )

    # ---------------------------------------------------------------------
    # Section A: Top-level docket merge & appeal_from resolution
    # ---------------------------------------------------------------------

    def test_creates_new_docket_with_all_scalar_fields(self) -> None:
        """Ported from ``test_merge_texas_docket_populates_all_fields`` —
        a brand-new appellate docket gets every Docket scalar field
        populated from ``docket_data``."""
        texas_district = CourtFactory.create(id="texdistct6")
        originating_court = TexasOriginatingDistrictCourtDictFactory(
            district=5,
        )
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            originating_court=originating_court,
            parties=[],
            transfer_from=None,
        )
        # Don't collide with the pre-existing docket_coa1 NK.
        docket_data["docket_number"] = "04-26-99999-CV"

        outcome = merge_texas_docket(docket_data, download_attachments=False)
        assert outcome is not None

        created_pks = outcome.creates.get(Docket, set())
        self.assertEqual(len(created_pks), 1)
        docket = Docket.objects.get(pk=next(iter(created_pks)))
        self.assertTrue(docket.source & Docket.SCRAPER)
        self.assertEqual(docket.court_id, "txctapp1")
        self.assertEqual(docket.docket_number, docket_data["docket_number"])
        self.assertEqual(
            docket.docket_number_core,
            make_texas_docket_number_core(docket_data["docket_number"]),
        )
        self.assertEqual(
            docket.docket_number_raw, docket_data["docket_number"]
        )
        self.assertEqual(docket.case_name, docket_data["case_name"])
        self.assertEqual(docket.case_name_full, docket_data["case_name_full"])
        self.assertEqual(docket.date_filed, docket_data["date_filed"])
        self.assertEqual(docket.cause, docket_data["case_type"])
        self.assertEqual(docket.appeal_from_id, "texdistct6")
        self.assertEqual(docket.appeal_from_str, texas_district.full_name)

    def test_existing_docket_recorded_as_update_not_create(self) -> None:
        """Ported from ``test_merge_texas_docket_existing_docket_marked_as_update``.
        A re-merge against an existing docket reports updates, not
        creates."""
        CourtFactory.create(id="texdistct6")
        originating_court = TexasOriginatingDistrictCourtDictFactory(
            district=5,
        )
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=originating_court,
            parties=[],
            transfer_from=None,
        )

        outcome = merge_texas_docket(docket_data, download_attachments=False)
        assert outcome is not None

        self.assertNotIn(
            self.docket_coa1.pk, outcome.creates.get(Docket, set())
        )
        self.assertIn(self.docket_coa1.pk, outcome.updates.get(Docket, set()))

    def test_appellate_sets_appeal_from_from_trial_court(self) -> None:
        """Ported from ``test_merge_texas_docket_appellate_sets_appeal_from``.
        An appellate docket whose originating court resolves to a known
        district court sets ``appeal_from`` + ``appeal_from_str``."""
        texas_district = CourtFactory.create(id="texdistct6")
        originating_court = TexasOriginatingDistrictCourtDictFactory(
            district=5,
        )
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=originating_court,
            parties=[],
            transfer_from=None,
        )

        outcome = merge_texas_docket(docket_data, download_attachments=False)
        assert outcome is not None
        self.assertIn(self.docket_coa1.pk, outcome.updates.get(Docket, set()))

        self.docket_coa1.refresh_from_db()
        self.assertEqual(self.docket_coa1.appeal_from_id, "texdistct6")
        self.assertEqual(
            self.docket_coa1.appeal_from_str, texas_district.full_name
        )

    def test_final_court_sets_appeal_from_from_appellate_court(self) -> None:
        """Ported from ``test_merge_texas_docket_final_court_sets_appeal_from``.
        SC dockets whose appellate court resolves get appeal_from to
        that appellate court."""
        sc_dn = "25-1066"
        docket_sc = DocketFactory.create(
            court=self.texas_sc,
            docket_number=sc_dn,
            docket_number_core=make_texas_docket_number_core(sc_dn),
        )
        appeals_court = TexasAppellateCourtInfoDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
        )
        docket_data = TexasFinalCourtDocketDictFactory(
            court_id=CourtID.SUPREME_COURT.value,
            docket_number=docket_sc.docket_number,
            appeals_court=appeals_court,
            originating_court=TexasOriginatingDistrictCourtDictFactory(
                district=100
            ),
            parties=[],
            is_direct_appeal=False,
        )

        outcome = merge_texas_docket(docket_data, download_attachments=False)
        assert outcome is not None
        self.assertIn(docket_sc.pk, outcome.updates.get(Docket, set()))

        docket_sc.refresh_from_db()
        self.assertEqual(docket_sc.appeal_from_id, "txctapp1")
        self.assertEqual(docket_sc.appeal_from_str, self.texas_coa1.full_name)

    def test_appeal_from_missing_court_uses_string_fallback(self) -> None:
        """Ported from ``test_merge_texas_docket_appeal_from_missing_court``.
        When the appellate court id doesn't resolve to a known Court,
        ``appeal_from`` stays NULL but ``appeal_from_str`` carries the
        Juriscraper-provided district name."""
        docket_data = TexasFinalCourtDocketDictFactory.create(
            is_direct_appeal=False,
            parties=[],
            appeals_court=TexasAppellateCourtInfoDictFactory(
                court_id="texas_coa17", district="Not Real Court of Appeals"
            ),
        )

        outcome = merge_texas_docket(docket_data, download_attachments=False)
        assert outcome is not None

        created_pks = outcome.creates.get(Docket, set())
        self.assertEqual(len(created_pks), 1)
        docket = Docket.objects.get(pk=next(iter(created_pks)))
        self.assertEqual(
            docket.appeal_from_str, docket_data["appeals_court"]["district"]
        )
        self.assertIsNone(docket.appeal_from)

    # ---------------------------------------------------------------------
    # Section B: OriginatingCourtInformation
    # ---------------------------------------------------------------------

    def test_oci_created_for_appellate_docket(self) -> None:
        """Ported from ``test_merge_texas_docket_originating_court_creates_new``."""
        self.docket_coa1.originating_court_information = None
        self.docket_coa1.save()

        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=TexasOriginatingDistrictCourtDictFactory(
                district=5,
            ),
            parties=[],
            transfer_from=None,
        )

        outcome = merge_texas_docket(docket_data, download_attachments=False)
        assert outcome is not None
        self.assertIn(
            OriginatingCourtInformation,
            outcome.creates,
            "Expected an OCI row to be created.",
        )

        self.docket_coa1.refresh_from_db()
        oci = self.docket_coa1.originating_court_information
        assert oci is not None
        self.assertEqual(
            oci.docket_number, docket_data["originating_court"]["case"]
        )
        self.assertEqual(
            oci.docket_number_raw, docket_data["originating_court"]["case"]
        )
        self.assertEqual(
            oci.court_reporter, docket_data["originating_court"]["reporter"]
        )
        self.assertEqual(
            oci.assigned_to_str, docket_data["originating_court"]["judge"]
        )

    def test_oci_updated_for_existing_docket(self) -> None:
        """Ported from ``test_merge_texas_docket_originating_court_updates_existing``."""
        existing_oci = OriginatingCourtInformation.objects.create(
            docket_number_raw="OLD-123",
            docket_number="OLD-123",
            court_reporter="Old Reporter",
            assigned_to_str="Old Judge",
        )
        self.docket_coa1.originating_court_information = existing_oci
        self.docket_coa1.save()

        originating_court = TexasOriginatingDistrictCourtDictFactory(
            district=5,
        )
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=originating_court,
            parties=[],
            transfer_from=None,
        )

        outcome = merge_texas_docket(docket_data, download_attachments=False)
        assert outcome is not None
        self.assertIn(
            existing_oci.pk,
            outcome.updates.get(OriginatingCourtInformation, set()),
        )
        self.assertNotIn(OriginatingCourtInformation, outcome.creates)

        existing_oci.refresh_from_db()
        self.assertEqual(existing_oci.docket_number, originating_court["case"])
        self.assertEqual(
            existing_oci.docket_number_raw, originating_court["case"]
        )
        self.assertEqual(
            existing_oci.court_reporter, originating_court["reporter"]
        )
        self.assertEqual(
            existing_oci.assigned_to_str, originating_court["judge"]
        )

    # ---------------------------------------------------------------------
    # Section C: TrialCourtData (SC / CCA only)
    # ---------------------------------------------------------------------

    def test_trial_court_data_create_noop_then_update(self) -> None:
        """Ported from ``test_merge_trial_court_data``. SC docket with a
        district-court originating court gets a TrialCourtData row;
        re-merging the same data is a no-op; mutating the originating
        case number produces an update."""
        texas_district = CourtFactory.create(id="texdistct6")
        originating_court = TexasOriginatingDistrictCourtDictFactory(
            district=5,
        )
        sc_dn = "25-2200"
        docket_sc = DocketFactory.create(
            court=self.texas_sc,
            docket_number=sc_dn,
            docket_number_core=make_texas_docket_number_core(sc_dn),
        )

        docket_data = TexasFinalCourtDocketDictFactory(
            court_id=CourtID.SUPREME_COURT.value,
            docket_number=sc_dn,
            originating_court=originating_court,
            parties=[],
            is_direct_appeal=True,  # avoid appeals-court branch
        )

        # First merge: creates TCD.
        outcome1 = merge_texas_docket(
            docket_data, download_attachments=False
        )
        assert outcome1 is not None
        created_tcd = outcome1.creates.get(TrialCourtData, set())
        self.assertEqual(len(created_tcd), 1)
        tcd = TrialCourtData.objects.get(pk=next(iter(created_tcd)))
        self.assertEqual(tcd.docket_id, docket_sc.pk)
        self.assertEqual(
            tcd.docket_number_trial, originating_court["case"]
        )
        self.assertEqual(
            tcd.docket_number_raw_trial, originating_court["case"]
        )
        self.assertEqual(tcd.judge_str, originating_court["judge"])
        self.assertEqual(tcd.reporter, originating_court["reporter"])
        self.assertEqual(tcd.punishment, originating_court["punishment"])
        self.assertEqual(tcd.county, originating_court["county"])
        self.assertEqual(tcd.court, texas_district)
        self.assertEqual(tcd.court_name, texas_district.full_name)

        # Second merge with the same data: no TCD writes.
        outcome2 = merge_texas_docket(
            docket_data, download_attachments=False
        )
        assert outcome2 is not None
        self.assertNotIn(TrialCourtData, outcome2.creates)
        self.assertNotIn(TrialCourtData, outcome2.updates)

        # Mutate the originating case number and re-merge → update.
        new_dn = originating_court["case"] + "Different"
        originating_court["case"] = new_dn
        outcome3 = merge_texas_docket(
            docket_data, download_attachments=False
        )
        assert outcome3 is not None
        self.assertIn(tcd.pk, outcome3.updates.get(TrialCourtData, set()))
        tcd.refresh_from_db()
        self.assertEqual(tcd.docket_number_trial, new_dn)
        self.assertEqual(
            TrialCourtData.objects.filter(docket=docket_sc).count(), 1
        )

    def test_judge_lookup_idempotent_across_repeated_merges(self) -> None:
        """Re-merging the same docket must not duplicate the
        ``Person`` row attached to ``TrialCourtData.judge``.

        ``lookup_judge_by_full_name`` only resolves existing rows
        (never creates), and the schema passes the result through as
        a ``PreResolvedRef[Person]`` — so the second merge should
        re-find the same Person and the framework should rewrite the
        FK to the existing row instead of inserting a new one. This
        guards against regressions where either layer accidentally
        creates a sibling Person on the repeat pass.
        """
        texas_district = CourtFactory.create(id="texdistct6")
        judge = PersonFactory.create(
            name_first="Hannibal",
            name_middle="",
            name_last="Smith",
            name_suffix="",
        )
        PositionFactory.create(person=judge, court=texas_district)

        sc_dn = "25-3300"
        docket_sc = DocketFactory.create(
            court=self.texas_sc,
            docket_number=sc_dn,
            docket_number_core=make_texas_docket_number_core(sc_dn),
        )
        originating_court = TexasOriginatingDistrictCourtDictFactory(
            district=5,
            judge="Hannibal Smith",
        )
        docket_data = TexasFinalCourtDocketDictFactory(
            court_id=CourtID.SUPREME_COURT.value,
            docket_number=sc_dn,
            originating_court=originating_court,
            parties=[],
            is_direct_appeal=True,
        )

        # First driver invocation: creates TCD, attaches the looked-up
        # judge via PreResolvedRef.
        outcome1 = merge_texas_docket(docket_data, download_attachments=False)
        assert outcome1 is not None
        tcd_pks = outcome1.creates.get(TrialCourtData, set())
        self.assertEqual(len(tcd_pks), 1)
        tcd = TrialCourtData.objects.get(pk=next(iter(tcd_pks)))
        self.assertEqual(
            tcd.judge_id,
            judge.pk,
            "First merge should resolve the existing Person as judge.",
        )

        # Second driver invocation: same data, fresh entry through the
        # public function. Re-runs court lookup, judge lookup, and the
        # 4-phase merge from scratch.
        outcome2 = merge_texas_docket(docket_data, download_attachments=False)
        assert outcome2 is not None

        self.assertEqual(
            Person.objects.filter(
                name_first="Hannibal", name_last="Smith"
            ).count(),
            1,
            "Repeated merges must not create a duplicate judge Person.",
        )
        tcd.refresh_from_db()
        self.assertEqual(
            tcd.judge_id,
            judge.pk,
            "Second merge should still point at the original Person.",
        )
        self.assertEqual(
            TrialCourtData.objects.filter(docket=docket_sc).count(),
            1,
            "Repeated merges must not create a duplicate TCD row.",
        )

    # ---------------------------------------------------------------------
    # Section D: Parties, attorneys, roles
    # ---------------------------------------------------------------------

    def test_single_party_with_attorney(self) -> None:
        """Ported from ``test_merge_single_party_with_attorney``."""
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=_empty_originating(),
            parties=[
                TexasCasePartyDictFactory(
                    name="Test Party",
                    type="Appellant",
                    representatives=["Test Attorney"],
                )
            ],
            transfer_from=None,
        )

        merge_texas_docket(docket_data, download_attachments=False)

        party = Party.objects.get(name="Test Party")
        self.assertTrue(
            PartyType.objects.filter(
                docket=self.docket_coa1, party=party, name="Appellant"
            ).exists()
        )
        self.assertTrue(Attorney.objects.filter(name="Test Attorney").exists())
        self.assertTrue(
            Role.objects.filter(
                docket=self.docket_coa1,
                party=party,
                attorney__name="Test Attorney",
            ).exists()
        )

    def test_multiple_parties_and_attorneys(self) -> None:
        """Ported from ``test_merge_multiple_parties``."""
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=_empty_originating(),
            parties=[
                TexasCasePartyDictFactory(
                    name="Appellant Party",
                    type="Appellant",
                    representatives=["Appellant Attorney"],
                ),
                TexasCasePartyDictFactory(
                    name="Appellee Party",
                    type="Appellee",
                    representatives=[
                        "Appellee Attorney One",
                        "Appellee Attorney Two",
                    ],
                ),
            ],
            transfer_from=None,
        )

        merge_texas_docket(docket_data, download_attachments=False)

        self.assertTrue(Party.objects.filter(name="Appellant Party").exists())
        self.assertTrue(Party.objects.filter(name="Appellee Party").exists())
        self.assertTrue(
            Attorney.objects.filter(name="Appellant Attorney").exists()
        )
        self.assertTrue(
            Attorney.objects.filter(name="Appellee Attorney One").exists()
        )
        self.assertTrue(
            Attorney.objects.filter(name="Appellee Attorney Two").exists()
        )
        self.assertEqual(
            Role.objects.filter(docket=self.docket_coa1).count(), 3
        )

    def test_party_without_representatives(self) -> None:
        """Ported from ``test_merge_party_without_representatives``."""
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=_empty_originating(),
            parties=[
                TexasCasePartyDictFactory(
                    name="Pro Se Party",
                    type="Appellant",
                    representatives=[],
                )
            ],
            transfer_from=None,
        )

        merge_texas_docket(docket_data, download_attachments=False)

        party = Party.objects.get(name="Pro Se Party")
        self.assertTrue(
            PartyType.objects.filter(
                docket=self.docket_coa1, party=party, name="Appellant"
            ).exists()
        )
        self.assertEqual(
            Role.objects.filter(
                docket=self.docket_coa1, party=party
            ).count(),
            0,
        )

    def test_empty_parties_preserves_existing(self) -> None:
        """Ported from ``test_merge_empty_parties_preserves_existing``.

        ``party_types`` uses ``Union`` strategy on ``TexasDocket``, so a
        re-merge with ``parties=[]`` must not delete existing PartyType
        rows.
        """
        first_docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=_empty_originating(),
            parties=[
                TexasCasePartyDictFactory(
                    name="Existing Party",
                    type="Appellant",
                    representatives=["Existing Attorney"],
                )
            ],
            transfer_from=None,
        )
        merge_texas_docket(first_docket_data, download_attachments=False)
        initial_party_count = self.docket_coa1.parties.count()

        empty_docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=_empty_originating(),
            parties=[],
            transfer_from=None,
        )
        merge_texas_docket(empty_docket_data, download_attachments=False)

        self.assertEqual(self.docket_coa1.parties.count(), initial_party_count)

    # ---------------------------------------------------------------------
    # Section E: Docket entries + documents
    # ---------------------------------------------------------------------

    def test_entries_with_appellate_brief_pairing_integration(self) -> None:
        """Ported from ``test_merge_docket_entries_integration``. Builds
        a random SC docket with N case events and a random subset of
        matching appellate briefs; verifies each entry's per-field state
        plus the appellate_brief flag matches the input."""
        n_events = fake.random_int(min=0, max=30)
        case_events = sorted(
            [TexasSupremeCourtCaseEventDictFactory() for _ in range(n_events)],
            key=lambda ce: ce["date"],
        )

        if not case_events:
            appellate_brief_indices: list[int] = []
        else:
            appellate_brief_indices = sorted(
                fake.random_elements(range(len(case_events)), unique=True)
            )

        appellate_briefs = [
            TexasSupremeCourtAppellateBriefDictFactory(
                date=case_events[i]["date"],
                type=case_events[i]["type"],
                attachments=case_events[i]["attachments"],
                remarks=case_events[i]["remarks"],
            )
            for i in appellate_brief_indices
        ]
        actual_flags = [
            i in appellate_brief_indices for i in range(len(case_events))
        ]

        docket_data = TexasFinalCourtDocketDictFactory(
            court_id=CourtID.SUPREME_COURT.value,
            case_events=case_events,
            appellate_briefs=appellate_briefs,
            originating_court=_empty_originating(),
            parties=[],
            is_direct_appeal=True,
        )

        original_entry_pks = list(
            TexasDocketEntry.objects.values_list("pk", flat=True)
        )

        merge_texas_docket(docket_data, download_attachments=False)

        new_entries = list(
            TexasDocketEntry.objects.exclude(
                pk__in=original_entry_pks
            ).order_by("sequence_number")
        )
        self.assertEqual(
            len(new_entries),
            len(case_events),
            f"Generated {len(new_entries)} entries from {len(case_events)} case events",
        )

        ab_index = 0
        for i, entry in enumerate(new_entries):
            self.assertEqual(
                entry.appellate_brief,
                actual_flags[i],
                f"Entry {i} appellate_brief flag mismatch",
            )
            self.assertEqual(entry.remarks, case_events[i]["remarks"])
            self.assertEqual(
                entry.disposition, case_events[i]["disposition"]
            )
            if actual_flags[i]:
                self.assertEqual(
                    entry.description,
                    appellate_briefs[ab_index]["description"],
                )
                ab_index += 1
            else:
                self.assertEqual(entry.description, "")

    def test_download_attachments_false_filters_followups(self) -> None:
        """Ported (re-framed) from
        ``test_merge_texas_document_skips_download_when_disabled``. With
        ``download_attachments=False``, the driver strips
        ``texas-document-download-and-extract`` follow-ups out of the
        returned outcome — the caller won't dispatch any downloads."""
        case_event = TexasCaseEventDictFactory(
            attachments=[TexasCaseDocumentDictFactory()],
            date=date(2025, 1, 2),
            type="Brief",
        )
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=_empty_originating(),
            parties=[],
            case_events=[case_event],
            appellate_briefs=[],
            transfer_from=None,
        )

        outcome_off = merge_texas_docket(
            docket_data, download_attachments=False
        )
        assert outcome_off is not None
        download_followups = [
            fu
            for fu in outcome_off.follow_ups
            if getattr(fu, "name", None) == _FOLLOWUP_DOWNLOAD
        ]
        self.assertEqual(download_followups, [])

    def test_download_attachments_true_keeps_followups(self) -> None:
        """The default ``download_attachments=True`` path leaves
        download follow-ups in the outcome so callers can dispatch
        them. This is the positive companion to the previous test."""
        # New docket so we don't pick up state from prior tests.
        case_event = TexasCaseEventDictFactory(
            attachments=[TexasCaseDocumentDictFactory()],
            date=date(2025, 1, 2),
            type="Brief",
        )
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number="11-26-77777-CV",
            originating_court=_empty_originating(),
            parties=[],
            case_events=[case_event],
            appellate_briefs=[],
            transfer_from=None,
        )

        outcome = merge_texas_docket(docket_data, download_attachments=True)
        assert outcome is not None
        download_followups = [
            fu
            for fu in outcome.follow_ups
            if getattr(fu, "name", None) == _FOLLOWUP_DOWNLOAD
        ]
        self.assertEqual(len(download_followups), 1)

    # ---------------------------------------------------------------------
    # Section F: CaseTransfer routing
    # ---------------------------------------------------------------------

    def test_case_transfer_appellate_court_from_trial(self) -> None:
        """Ported from
        ``test_merge_texas_case_transfers_appellate_court_from_trial``.
        A COA docket whose originating court is a known district court
        produces one APPEAL transfer with this docket as destination."""
        texas_district = CourtFactory.create(id="texdistct6")
        originating_court = TexasOriginatingDistrictCourtDictFactory(
            district=5,
        )
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=originating_court,
            parties=[],
            transfer_from=None,
        )

        merge_texas_docket(docket_data, download_attachments=False)

        transfers = CaseTransfer.objects.all()
        self.assertEqual(transfers.count(), 1)
        transfer = transfers.first()
        assert transfer is not None
        self.assertEqual(transfer.destination_court, self.texas_coa1)
        self.assertEqual(
            transfer.destination_docket_number, self.docket_number_coa1
        )
        self.assertEqual(transfer.destination_docket, self.docket_coa1)
        self.assertEqual(transfer.origin_court, texas_district)
        self.assertEqual(
            transfer.origin_docket_number, originating_court["case"]
        )
        self.assertEqual(transfer.transfer_type, CaseTransfer.APPEAL)
        self.assertEqual(transfer.transfer_date, docket_data["date_filed"])

    def test_case_transfer_appellate_with_workload_transfer(self) -> None:
        """Ported from
        ``test_merge_texas_case_transfers_appellate_with_workload_transfer``."""
        texas_district = CourtFactory.create(id="texdistct6")
        texas_coa2 = CourtFactory.create(id="txctapp2")
        originating_court = TexasOriginatingDistrictCourtDictFactory(
            district=5,
        )
        transfer_from = TexasAppellateTransferDictFactory(
            court_id=CourtID.SECOND_COURT_OF_APPEALS.value,
        )
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=originating_court,
            parties=[],
            transfer_from=transfer_from,
        )

        merge_texas_docket(docket_data, download_attachments=False)

        transfers = CaseTransfer.objects.all()
        self.assertEqual(transfers.count(), 2)

        appeal = transfers.get(transfer_type=CaseTransfer.APPEAL)
        self.assertEqual(appeal.origin_court, texas_district)
        self.assertEqual(appeal.origin_docket_number, originating_court["case"])
        self.assertEqual(appeal.destination_docket, self.docket_coa1)

        workload = transfers.get(transfer_type=CaseTransfer.WORKLOAD)
        self.assertEqual(workload.origin_court, texas_coa2)
        self.assertEqual(
            workload.origin_docket_number, transfer_from["origin_docket"]
        )
        self.assertEqual(workload.destination_docket, self.docket_coa1)

    def test_case_transfer_supreme_court_from_appellate(self) -> None:
        """Ported from ``test_merge_texas_case_transfers_supreme_court``."""
        sc_dn = "25-3333"
        docket_sc = DocketFactory.create(
            court=self.texas_sc,
            docket_number=sc_dn,
            docket_number_core=make_texas_docket_number_core(sc_dn),
        )
        appeals_court = TexasAppellateCourtInfoDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            _n_cases=1,
            case_number=[self.docket_number_coa1],
        )
        docket_data = TexasFinalCourtDocketDictFactory(
            court_id=CourtID.SUPREME_COURT.value,
            docket_number=sc_dn,
            appeals_court=appeals_court,
            originating_court=_empty_originating(),
            parties=[],
            is_direct_appeal=False,
        )

        merge_texas_docket(docket_data, download_attachments=False)

        transfers = CaseTransfer.objects.all()
        self.assertEqual(transfers.count(), 1)
        transfer = transfers.first()
        assert transfer is not None
        self.assertEqual(transfer.destination_court, self.texas_sc)
        self.assertEqual(transfer.destination_docket, docket_sc)
        self.assertEqual(transfer.destination_docket_number, sc_dn)
        self.assertEqual(transfer.origin_court, self.texas_coa1)
        self.assertEqual(
            transfer.origin_docket_number, self.docket_number_coa1
        )
        self.assertEqual(transfer.transfer_type, CaseTransfer.APPEAL)

    def test_case_transfer_cca_from_appellate(self) -> None:
        """Ported from ``test_merge_texas_case_transfers_cca_from_appellate``."""
        cca_dn = "PD-25-4444"
        docket_cca = DocketFactory.create(
            court=self.texas_cca,
            docket_number=cca_dn,
            docket_number_core=make_texas_docket_number_core(cca_dn),
        )
        appeals_court = TexasAppellateCourtInfoDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            _n_cases=1,
            case_number=[self.docket_number_coa1],
        )
        docket_data = TexasFinalCourtDocketDictFactory(
            court_id=CourtID.COURT_OF_CRIMINAL_APPEALS.value,
            docket_number=cca_dn,
            appeals_court=appeals_court,
            originating_court=_empty_originating(),
            parties=[],
            is_direct_appeal=False,
        )

        merge_texas_docket(docket_data, download_attachments=False)

        transfers = CaseTransfer.objects.all()
        self.assertEqual(transfers.count(), 1)
        transfer = transfers.first()
        assert transfer is not None
        self.assertEqual(transfer.destination_court, self.texas_cca)
        self.assertEqual(transfer.destination_docket, docket_cca)
        self.assertEqual(transfer.origin_court, self.texas_coa1)
        self.assertEqual(
            transfer.origin_docket_number, self.docket_number_coa1
        )
        self.assertEqual(transfer.transfer_type, CaseTransfer.APPEAL)

    def test_case_transfer_cca_death_penalty_direct_appeal(self) -> None:
        """Ported from
        ``test_merge_texas_case_transfers_cca_death_penalty_direct_appeal``.
        CCA + ``is_direct_appeal=True`` (which sets ac_id=UNKNOWN)
        falls back to trial court as origin."""
        texas_district = CourtFactory.create(id="texdistct6")
        cca_dn = "WR-25-9999"
        docket_cca = DocketFactory.create(
            court=self.texas_cca,
            docket_number=cca_dn,
            docket_number_core=make_texas_docket_number_core(cca_dn),
        )
        originating_court = TexasOriginatingDistrictCourtDictFactory(
            district=5,
        )
        docket_data = TexasFinalCourtDocketDictFactory(
            court_id=CourtID.COURT_OF_CRIMINAL_APPEALS.value,
            docket_number=cca_dn,
            originating_court=originating_court,
            parties=[],
            is_direct_appeal=True,
        )

        merge_texas_docket(docket_data, download_attachments=False)

        transfers = CaseTransfer.objects.all()
        self.assertEqual(transfers.count(), 1)
        transfer = transfers.first()
        assert transfer is not None
        self.assertEqual(transfer.destination_court, self.texas_cca)
        self.assertEqual(transfer.destination_docket, docket_cca)
        self.assertEqual(transfer.origin_court, texas_district)
        self.assertEqual(
            transfer.origin_docket_number, originating_court["case"]
        )
        self.assertEqual(transfer.transfer_type, CaseTransfer.APPEAL)

    def test_case_transfer_no_trial_court_info_returns_empty(self) -> None:
        """Ported from
        ``test_merge_texas_case_transfers_no_trial_court_info``. An
        appellate docket whose originating court is UNKNOWN and that
        has no ``transfer_from`` produces no transfers."""
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=_empty_originating(),
            parties=[],
            transfer_from=None,
        )

        merge_texas_docket(docket_data, download_attachments=False)

        self.assertEqual(CaseTransfer.objects.count(), 0)

    def test_case_transfer_duplicate_handling(self) -> None:
        """Ported from
        ``test_merge_texas_case_transfers_duplicate_handling``. A
        pre-existing fully-matching CaseTransfer row is not duplicated;
        the framework's global NK lookup finds it."""
        texas_district = CourtFactory.create(id="texdistct6")
        originating_court = TexasOriginatingDistrictCourtDictFactory(
            district=5,
        )
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=originating_court,
            parties=[],
            transfer_from=None,
        )

        CaseTransferFactory.create(
            origin_court=texas_district,
            origin_docket=None,
            origin_docket_number=originating_court["case"],
            destination_court=self.texas_coa1,
            destination_docket_number=self.docket_number_coa1,
            destination_docket=self.docket_coa1,
            transfer_date=docket_data["date_filed"],
            transfer_type=CaseTransfer.APPEAL,
        )

        merge_texas_docket(docket_data, download_attachments=False)

        # Still exactly one row — the framework matched and reused.
        self.assertEqual(CaseTransfer.objects.count(), 1)

    def test_case_transfer_multiple_appellate(self) -> None:
        """Ported from ``test_merge_texas_case_transfers_multiple``. SC
        docket with multiple appellate-court case_numbers produces one
        APPEAL transfer per number."""
        aci = TexasAppellateCourtInfoDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value, _n_cases=3
        )
        sc_dn = "25-9876"
        DocketFactory.create(
            court=self.texas_sc,
            docket_number=sc_dn,
            docket_number_core=make_texas_docket_number_core(sc_dn),
        )
        docket_data = TexasFinalCourtDocketDictFactory(
            court_id=CourtID.SUPREME_COURT.value,
            docket_number=sc_dn,
            appeals_court=aci,
            originating_court=_empty_originating(),
            parties=[],
            is_direct_appeal=False,
        )

        merge_texas_docket(docket_data, download_attachments=False)

        transfers = CaseTransfer.objects.all()
        self.assertEqual(transfers.count(), 3)
        self.assertEqual(
            {t.origin_docket_number for t in transfers},
            set(aci["case_number"]),
        )

    def test_case_transfer_unknown_workload_court_skipped(self) -> None:
        """Ported from
        ``test_merge_texas_case_transfers_appellate_with_unknown_workload_transfer_court``.
        A ``transfer_from`` with UNKNOWN court_id is logged and skipped;
        the APPEAL transfer still gets created."""
        texas_district = CourtFactory.create(id="texdistct6")
        originating_court = TexasOriginatingDistrictCourtDictFactory(
            district=5,
        )
        transfer_from = TexasAppellateTransferDictFactory(
            court_id=CourtID.UNKNOWN.value,
        )
        docket_data = TexasCourtOfAppealsDocketDictFactory(
            court_id=CourtID.FIRST_COURT_OF_APPEALS.value,
            docket_number=self.docket_number_coa1,
            originating_court=originating_court,
            parties=[],
            transfer_from=transfer_from,
        )

        merge_texas_docket(docket_data, download_attachments=False)

        transfers = CaseTransfer.objects.all()
        self.assertEqual(transfers.count(), 1)
        transfer = transfers.first()
        assert transfer is not None
        self.assertEqual(transfer.transfer_type, CaseTransfer.APPEAL)
        self.assertEqual(transfer.origin_court, texas_district)
