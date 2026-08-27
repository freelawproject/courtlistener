"""Tests for Florida docket and originating-court-information merger."""

from datetime import date, datetime
from tempfile import NamedTemporaryFile
from unittest import mock

import httpx
from juriscraper.state.docket import (
    DocketEntryType as ScrapeDocketEntryType,
)
from juriscraper.state.docket import DocketTransfer
from juriscraper.state.docket import PartyType as ScrapePartyType
from juriscraper.state.docket import (
    TransferDirection as ScrapeTransferDirection,
)
from juriscraper.state.docket import TransferReason as ScrapeTransferReason
from juriscraper.state.florida.cases import FloridaCase
from juriscraper.state.florida.courts import FloridaCourtID

from cl.corpus_importer.state.florida.factories import (
    FloridaCaseActorFactory,
    FloridaCaseFactory,
    FloridaCasePartyFactory,
    FloridaDocketEntryFactory,
    FloridaDocketTransferFactory,
    FloridaDocumentFactory,
    FloridaOriginatingCaseFactory,
    FloridaRepresentativeFactory,
)
from cl.corpus_importer.state.florida.mergers import (
    FloridaDocketEntryMerger,
    FloridaDocketMerger,
)
from cl.corpus_importer.state.florida.utils import make_docket_number_core
from cl.corpus_importer.state.merger import RelatedParams
from cl.corpus_importer.state.tests import merger_test
from cl.corpus_importer.state.utils import MergeResult
from cl.corpus_importer.tasks import (
    download_fl_document,
    fl_ingest_docket_task,
)
from cl.people_db.factories import (
    AttorneyFactory,
    PartyFactory,
    PartyTypeFactory,
)
from cl.people_db.models import Attorney, Party, PartyType, Role
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import CaseTransfer, Docket, OriginatingCourtInformation
from cl.search.state.florida.factories import (
    FloridaDocumentFactory as FloridaDocumentModelFactory,
)
from cl.search.state.florida.models import (
    FloridaDocketEntry,
    FloridaDocument,
)
from cl.search.state.shared import DocketEntryType, ProcessingError
from cl.tests.cases import TestCase


class FloridaUtilsTest(TestCase):
    def test_docket_number_core(self) -> None:
        """Can we correctly normalize Florida docket numbers?"""
        self.assertEqual(make_docket_number_core("SC1983-2014"), "sc19832014")
        self.assertEqual(
            make_docket_number_core("SC1983-2014", court_id="fla"),
            "sc19832014",
        )
        self.assertEqual(
            make_docket_number_core("3D2001-20145", court_id="fla"),
            "",
        )
        self.assertEqual(
            make_docket_number_core("Meowdy, partner", court_id="tx"),
            "",
        )
        self.assertEqual(
            make_docket_number_core("3D2001-20145", court_id="fladistctapp2"),
            "3d200120145",
        )
        self.assertEqual(
            make_docket_number_core("SC1983-2014", court_id="fladistctapp2"),
            "",
        )
        self.assertEqual(make_docket_number_core("WR-70,849-04"), "")

        self.assertEqual(
            make_docket_number_core("Case Number: SC1983-2014"),
            "sc19832014",
        )

        self.assertEqual(
            make_docket_number_core(
                "Case Number: 6D2011-1337; 3D2001-20145",
                court_id="fladistctapp5",
            ),
            "3d200120145",
        )

        self.assertEqual(make_docket_number_core("garbage text"), "")


class FloridaMergerTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.flsc = CourtFactory.create(id="fla")
        cls.flca01 = CourtFactory.create(id="fladistctapp1")
        cls.flca02 = CourtFactory.create(id="fladistctapp2")
        cls.flagg = CourtFactory.create(id="fladistctapp")
        cls.docket_number_sc = "SC2025-1234"
        cls.docket_sc = DocketFactory.create(
            court=cls.flsc,
            docket_number=cls.docket_number_sc,
            docket_number_raw=cls.docket_number_sc,
            docket_number_core="",
            pacer_case_id=None,
            source=Docket.SCRAPER,
        )
        cls.docket_number_coa1 = "1D2025-0099"
        cls.docket_coa1 = DocketFactory.create(
            court=cls.flca01,
            docket_number=cls.docket_number_coa1,
            docket_number_raw=cls.docket_number_coa1,
            docket_number_core="",
            pacer_case_id=None,
            source=Docket.SCRAPER,
        )

    @mock.patch(
        "cl.corpus_importer.state.florida.mergers.FloridaOriginatingCourtInformationMerger.merge",
        return_value=("failure", {"OriginatingCourtInformation": [1]}),
    )
    @merger_test(expected_query_count=16)
    def test_merge_skips_non_sc_oci(self, mock_merge: mock.Mock):
        """Does merge skip OCI merging for non-supreme-court dockets?"""
        docket_data = FloridaCaseFactory.create(
            court_id=FloridaCourtID.FIRST_COA.value,
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        mock_merge.assert_not_called()
        assert result.success is True

    @merger_test(expected_query_count=15)
    def test_merge_creates_new_oci(self):
        """Does merge create a new OCI when none exists?"""
        self.docket_sc.originating_court_information = None
        self.docket_sc.save()

        originating = FloridaOriginatingCaseFactory.build(
            case_number="ORIG-001",
        )
        docket_data = FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            originating_cases=[originating],
        )

        result = FloridaDocketMerger(
            docket_data, existing=self.docket_sc, params=None
        ).merge()

        self.assertTrue(result.success)
        self.assertTrue(result.create)
        self.assertIn("OriginatingCourtInformation", result.creates)
        oci_pk = next(iter(result.creates["OriginatingCourtInformation"]))
        oci = OriginatingCourtInformation.objects.get(pk=oci_pk)
        self.assertEqual(oci.docket_number, "ORIG-001")
        self.assertEqual(oci.docket_number_raw, "ORIG-001")
        self.docket_sc.refresh_from_db()
        self.assertEqual(
            self.docket_sc.originating_court_information_id, oci_pk
        )

    @merger_test(expected_query_count=15)
    def test_merge_updates_existing_oci(self):
        """Does merge update an existing OCI when one is already linked?"""
        existing_oci = OriginatingCourtInformation.objects.create(
            docket_number="OLD-NUMBER",
            docket_number_raw="OLD-NUMBER",
        )
        self.docket_sc.originating_court_information = existing_oci
        self.docket_sc.save()

        originating = FloridaOriginatingCaseFactory.build(
            case_number="UPDATED-001",
        )
        docket_data = FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            originating_cases=[originating],
        )

        result = FloridaDocketMerger(
            docket_data, existing=self.docket_sc, params=None
        ).merge()

        assert result.success is True
        assert result.update is True
        assert "OriginatingCourtInformation" not in result.creates
        assert existing_oci.pk in result.updates["OriginatingCourtInformation"]
        existing_oci.refresh_from_db()
        assert existing_oci.docket_number == "UPDATED-001"
        assert existing_oci.docket_number_raw == "UPDATED-001"

    @merger_test(expected_query_count=14)
    def test_merge_no_originating_cases_skips_oci(self):
        """Does merge skip OCI merging when there are no originating cases?"""
        self.docket_sc.originating_court_information = None
        self.docket_sc.save()

        docket_data = FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            originating_cases=[],
        )

        result = FloridaDocketMerger(
            docket_data, existing=self.docket_sc, params=None
        ).merge()

        assert result.success is True
        assert "OriginatingCourtInformation" not in result.creates
        assert "OriginatingCourtInformation" not in result.updates

    @merger_test(expected_query_count=15)
    def test_merge_multiple_originating_cases_uses_first(self):
        """Does merge pick the first originating case when several exist?"""
        self.docket_sc.originating_court_information = None
        self.docket_sc.save()

        first = FloridaOriginatingCaseFactory(case_number="FIRST-001")
        second = FloridaOriginatingCaseFactory(case_number="SECOND-002")
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            originating_cases=[first, second],
        )

        result = FloridaDocketMerger(
            docket_data, existing=self.docket_sc, params=None
        ).merge()

        assert result.success is True
        oci_pk = next(iter(result.creates["OriginatingCourtInformation"]))
        oci = OriginatingCourtInformation.objects.get(pk=oci_pk)
        assert oci.docket_number == "FIRST-001"

    @merger_test(expected_query_count=0)
    def test_merge_docket_unknown_court_fails(self):
        """Does merge_docket fail when the court id is unknown?"""
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.CIRCUIT.value,
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        self.assertEqual(result.success, False)
        self.assertIn("Docket", result.failures)
        self.assertEqual(result.failures["Docket"], [None])

    @merger_test(expected_query_count=16)
    def test_merge_docket_supreme_court_creates_new(self):
        """Does merge_docket create a new supreme-court docket?"""
        original_pks = set(Docket.objects.values_list("pk", flat=True))
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            docket_number="SC2025-9999",
            entries=[],
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        new_pks = (
            set(Docket.objects.values_list("pk", flat=True)) - original_pks
        )
        assert len(new_pks) == 1
        new_pk = new_pks.pop()
        assert new_pk in result.creates["Docket"]
        new_docket = Docket.objects.get(pk=new_pk)
        assert new_docket.court_id == "fla"
        assert new_docket.docket_number == "SC2025-9999"
        assert new_docket.docket_number_raw == "SC2025-9999"
        assert new_docket.case_name == docket_data.case_name
        assert new_docket.case_name_full == docket_data.case_name_full
        assert new_docket.case_name_short == docket_data.case_name_short
        assert new_docket.date_filed == docket_data.date_filed

    @merger_test(expected_query_count=15)
    def test_merge_docket_existing_supreme_court_is_update(self):
        """Does merge_docket update an existing supreme-court docket in place?"""
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            docket_number=self.docket_number_sc,
            entries=[],
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert "Docket" in result.updates
        assert self.docket_sc.pk in result.updates["Docket"]
        assert self.docket_sc.pk not in result.creates.get("Docket", set())
        self.docket_sc.refresh_from_db()
        assert self.docket_sc.case_name == docket_data.case_name

    @merger_test(expected_query_count=19)
    def test_merge_docket_appellate_disaggregates_existing(self):
        """Does merge_docket move a matching docket from the aggregate court
        into its specific district court?"""
        agg_dn = "1D2025-1234"
        agg_docket = DocketFactory.create(
            court=self.flagg,
            docket_number=agg_dn,
            docket_number_raw=agg_dn,
            docket_number_core=make_docket_number_core(agg_dn),
            pacer_case_id=None,
            source=Docket.SCRAPER,
        )
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.FIRST_COA.value,
            docket_number=agg_dn,
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert "Docket" in result.updates
        assert agg_docket.pk in result.updates["Docket"]
        agg_docket.refresh_from_db()
        assert agg_docket.court_id == "fladistctapp1"

    @merger_test(expected_query_count=14)
    def test_merge_docket_appellate_creates_new(self):
        """Does merge_docket create a new docket in the specific appellate
        court when no existing docket matches?"""
        original_pks = set(Docket.objects.values_list("pk", flat=True))
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.SECOND_COA.value,
            docket_number="2D2025-BRAND-NEW",
            entries=[],
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        new_pks = (
            set(Docket.objects.values_list("pk", flat=True)) - original_pks
        )
        assert len(new_pks) == 1
        new_docket = Docket.objects.get(pk=new_pks.pop())
        assert new_docket.court_id == "fladistctapp2"
        assert new_docket.docket_number == "2D2025-BRAND-NEW"

    @merger_test(expected_query_count=19)
    def test_merge_docket_uses_latest_entry_for_date_last_filing(self):
        """Does merge_docket pick the latest entry date for date_last_filing?"""
        entries = [
            FloridaDocketEntryFactory(date_filed=d)
            for d in (
                date(2025, 1, 5),
                date(2025, 3, 10),
                date(2025, 2, 12),
            )
        ]
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            docket_number=self.docket_number_sc,
            entries=entries,
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        self.docket_sc.refresh_from_db()
        assert self.docket_sc.date_last_filing == date(2025, 3, 10)

    @merger_test(expected_query_count=15)
    def test_merge_docket_no_entries_falls_back_to_date_filed(self):
        """When there are no entries, does date_last_filing fall back to
        date_filed?"""
        filed = datetime(2024, 6, 15, 12, 0, 0)
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            docket_number=self.docket_number_sc,
            datetime_filed=filed,
            entries=[],
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        self.docket_sc.refresh_from_db()
        assert self.docket_sc.date_filed == filed.date()
        assert self.docket_sc.date_last_filing == filed.date()

    @merger_test(expected_query_count=16)
    def test_uuid_matches(self):
        """Does case_uuid correctly map as a lookup to pacer_case_id?"""
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            docket_number="SC2026-1337",
        )
        docket = DocketFactory.create(
            court=CourtFactory.create(id="fla"),
            docket_number=docket_data.docket_number,
            docket_number_core=make_docket_number_core(
                docket_data.docket_number
            ),
            pacer_case_id=str(docket_data.case_uuid),
            # A random RECAP source makes Docket.save query the court table,
            # making the query count above flaky.
            source=Docket.SCRAPER,
        )
        result = FloridaDocketMerger(docket_data, params=None).merge()

        self.assertTrue(result.success)
        self.assertTrue(result.update)
        self.assertIn("Docket", result.updates)
        self.assertIn(docket.pk, result.updates["Docket"])


class FloridaPartyMergerTest(TestCase):
    """Tests for merging parties, attorneys, and attorney roles from Florida
    cases."""

    @classmethod
    def setUpTestData(cls):
        cls.flsc = CourtFactory.create(id="fla")

    @staticmethod
    def _make_case(*parties) -> FloridaCase:
        return FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            parties=list(parties),
        )

    @staticmethod
    def _merged_docket(result: MergeResult) -> Docket:
        return Docket.objects.get(pk=next(iter(result.creates["Docket"])))

    @merger_test(expected_query_count=11)
    def test_merge_creates_party_with_type(self):
        """Does merging create the scrape's party and link it to the docket
        with the correct party type?"""
        scrape_party = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[],
        )
        docket_data = self._make_case(scrape_party)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert "Party" in result.creates
        docket = self._merged_docket(result)
        party = docket.parties.get()
        assert party.name == "Acme Corp"
        party_type = PartyType.objects.get(docket=docket)
        assert party_type.party_id == party.pk
        assert party_type.name == "Appellant"

    @merger_test(expected_query_count=14)
    def test_merge_creates_all_parties(self):
        """Are multiple parties in a scrape merged as separate objects, each
        with its own party type?"""
        appellant = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[],
            pro_se_flag=False,
        )
        appellee = FloridaCasePartyFactory.create(
            name="Bob Smith",
            party_type=ScrapePartyType.APPELLEE,
            representatives=[],
            pro_se_flag=True,
        )
        docket_data = self._make_case(appellant, appellee)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        docket = self._merged_docket(result)
        assert set(docket.parties.values_list("name", flat=True)) == {
            "Acme Corp",
            "Bob Smith",
        }
        assert set(
            PartyType.objects.filter(docket=docket).values_list(
                "party__name", "name", "pro_se"
            )
        ) == {
            ("Acme Corp", "Appellant", PartyType.PRO_SE_NO),
            ("Bob Smith", "Appellee", PartyType.PRO_SE_YES),
        }

    @merger_test(expected_query_count=16)
    def test_merge_primary_representative_is_lead_attorney(self):
        """Is a primary representative merged as a lead attorney for the
        party on the merged docket?"""
        rep = FloridaRepresentativeFactory.create(
            name="Jane Lawyer", primary_flag=True
        )
        scrape_party = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[rep],
        )
        docket_data = self._make_case(scrape_party)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        docket = self._merged_docket(result)
        party = docket.parties.get()
        attorney = party.attorneys.get()
        role = Role.objects.get(party=party, attorney=attorney)
        assert role.docket_id == docket.pk
        assert role.role == Role.ATTORNEY_LEAD

    @merger_test(expected_query_count=16)
    def test_merge_non_primary_representative_role_unknown(self):
        """Is a non-primary representative given the unknown role?"""
        rep = FloridaRepresentativeFactory.create(
            name="Jane Lawyer", primary_flag=False
        )
        scrape_party = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[rep],
        )
        docket_data = self._make_case(scrape_party)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        docket = self._merged_docket(result)
        party = docket.parties.get()
        role = Role.objects.get(party=party)
        assert role.role == Role.UNKNOWN

    @merger_test(expected_query_count=16)
    def test_merge_sets_attorney_name(self):
        """Does the merged attorney carry the representative's name?"""
        rep = FloridaRepresentativeFactory.create(
            name="Jane Lawyer", primary_flag=True
        )
        scrape_party = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[rep],
        )
        docket_data = self._make_case(scrape_party)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        docket = self._merged_docket(result)
        attorney = docket.parties.get().attorneys.get()
        assert attorney.name == "Jane Lawyer"

    @merger_test(expected_query_count=19)
    def test_merge_party_with_multiple_representatives(self):
        """Are all of a party's representatives merged as separate attorneys
        with their own roles?"""
        lead = FloridaRepresentativeFactory.create(
            name="Jane Lawyer", primary_flag=True
        )
        second_chair = FloridaRepresentativeFactory.create(
            name="John Counsel", primary_flag=False
        )
        scrape_party = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[lead, second_chair],
        )
        docket_data = self._make_case(scrape_party)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        docket = self._merged_docket(result)
        party = docket.parties.get()
        assert party.attorneys.count() == 2
        assert set(
            Role.objects.filter(party=party).values_list("role", flat=True)
        ) == {Role.ATTORNEY_LEAD, Role.UNKNOWN}

    @merger_test(expected_query_count=27)
    def test_remerge_is_idempotent(self):
        """Does merging the same case twice avoid duplicating parties,
        attorneys, and their links?"""
        rep = FloridaRepresentativeFactory.create(
            name="Jane Lawyer", primary_flag=True
        )
        scrape_party = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[rep],
        )
        docket_data = self._make_case(scrape_party)

        first_merger = FloridaDocketMerger(docket_data, params=None)
        first = first_merger.merge()
        first_db = first_merger.out
        second_merger = FloridaDocketMerger(docket_data, params=None)
        second = second_merger.merge()
        second_db = second_merger.out

        self.assertEqual(first_db, second_db)
        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertFalse(second.create)
        self.assertFalse(second.update)
        self.assertEqual(Party.objects.count(), 1)
        self.assertEqual(Attorney.objects.count(), 1)
        self.assertEqual(Role.objects.count(), 1)
        self.assertEqual(PartyType.objects.count(), 1)

    @merger_test(expected_query_count=11)
    def test_merge_does_not_modify_unrelated_parties(self):
        """Does merging create a new party rather than renaming an existing
        party from another docket?"""
        other_docket = DocketFactory.create(court=self.flsc)
        other_party = PartyFactory.create(
            name="Unrelated Party",
            docket=other_docket,
            attorneys=[AttorneyFactory.create(docket=other_docket)],
        )
        PartyTypeFactory.create(
            docket=other_docket, party=other_party, name="plaintiff"
        )

        scrape_party = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[],
        )
        docket_data = self._make_case(scrape_party)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        other_party.refresh_from_db()
        assert other_party.name == "Unrelated Party"
        docket = self._merged_docket(result)
        assert list(docket.parties.values_list("name", flat=True)) == [
            "Acme Corp"
        ]

    @merger_test(expected_query_count=16)
    def test_merge_preserves_unrelated_party_types_and_roles(self):
        """Does merging one docket leave party and attorney links on other
        dockets in place?"""
        other_docket = DocketFactory.create(court=self.flsc)
        other_attorney = AttorneyFactory.create(docket=other_docket)
        other_party = PartyFactory.create(
            name="Unrelated Party",
            docket=other_docket,
            attorneys=[other_attorney],
        )
        other_party_type = PartyTypeFactory.create(
            docket=other_docket, party=other_party, name="plaintiff"
        )
        other_role = Role.objects.get(party=other_party)

        rep = FloridaRepresentativeFactory.create(
            name="Jane Lawyer", primary_flag=True
        )
        scrape_party = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[rep],
        )
        docket_data = self._make_case(scrape_party)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert PartyType.objects.filter(pk=other_party_type.pk).exists()
        assert Role.objects.filter(pk=other_role.pk).exists()
        other_role.refresh_from_db()
        assert other_role.docket_id == other_docket.pk

    @merger_test(expected_query_count=19)
    def test_party_type_change_renames_in_place(self):
        """When a party's type changes between scrapes, is the single
        PartyType row renamed rather than duplicated?"""
        scrape_party = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[],
        )
        docket_data = self._make_case(scrape_party)
        first = FloridaDocketMerger(docket_data, params=None).merge()
        assert first.success is True
        docket = self._merged_docket(first)

        scrape_party.party_type = ScrapePartyType.APPELLEE
        second = FloridaDocketMerger(docket_data, params=None).merge()

        assert second.success is True
        party_type = PartyType.objects.get(docket=docket)
        assert party_type.name == "Appellee"

    @merger_test(expected_query_count=20)
    def test_merge_empty_parties_preserves_existing(self):
        """Does a scrape with no parties leave existing parties, types, and
        roles untouched?"""
        rep = FloridaRepresentativeFactory.create(
            name="Jane Lawyer", primary_flag=True
        )
        scrape_party = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[rep],
        )
        docket_data = self._make_case(scrape_party)
        first = FloridaDocketMerger(docket_data, params=None).merge()
        assert first.success is True
        docket = self._merged_docket(first)

        docket_data.parties = []
        second = FloridaDocketMerger(docket_data, params=None).merge()

        assert second.success is True
        assert docket.parties.count() == 1
        assert PartyType.objects.filter(docket=docket).count() == 1
        assert Role.objects.filter(docket=docket).count() == 1


class FloridaDocketEntryMergerTest(TestCase):
    """Tests for merging docket entries from Florida cases."""

    @classmethod
    def setUpTestData(cls):
        cls.flsc = CourtFactory.create(id="fla")

    @staticmethod
    def _make_case(*entries) -> FloridaCase:
        return FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            entries=list(entries),
        )

    @staticmethod
    def _merged_docket(result: MergeResult) -> Docket:
        return Docket.objects.get(pk=next(iter(result.creates["Docket"])))

    @merger_test(expected_query_count=16)
    def test_merge_creates_docket_entries(self):
        """Does merging a case create its docket entries with the scrape's
        field values?"""
        entry = FloridaDocketEntryFactory.create(
            entry_type=ScrapeDocketEntryType.MOTION,
            entry_type_raw="motions other",
            entry_name="Motion for Extension",
            entry_description="Requesting more time.",
            entry_status="Docketed",
            attachments=[],
        )
        docket_data = self._make_case(entry)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert "FloridaDocketEntry" in result.creates
        docket = self._merged_docket(result)
        merged = docket.florida_docket_entries.get()
        assert str(merged.docket_entry_uuid) == str(entry.docket_entry_uuid)
        assert merged.date_filed == entry.datetime_filed
        assert merged.date_submitted == entry.date_submitted
        assert merged.entry_type == DocketEntryType.MOTION
        assert merged.entry_type_raw == "motions other"
        assert merged.entry_name == "Motion for Extension"
        assert merged.description == "Requesting more time."
        self.assertEqual(merged.status, FloridaDocketEntry.STATUS_DOCKETED)
        self.assertEqual(merged.submitted_by_name, "")
        self.assertIsNone(merged.submitted_by_id)

    @merger_test(expected_query_count=18)
    def test_merge_creates_all_docket_entries(self):
        """Are multiple entries in a scrape merged as separate objects?"""
        entries = [
            FloridaDocketEntryFactory.create(attachments=[]) for _ in range(3)
        ]
        docket_data = self._make_case(*entries)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        docket = self._merged_docket(result)
        assert docket.florida_docket_entries.count() == 3
        assert {
            str(uuid)
            for uuid in docket.florida_docket_entries.values_list(
                "docket_entry_uuid", flat=True
            )
        } == {str(e.docket_entry_uuid) for e in entries}

    @merger_test(expected_query_count=27)
    def test_remerge_entries_is_idempotent(self):
        """Does merging the same case twice avoid duplicating entries?"""
        entry = FloridaDocketEntryFactory.create(attachments=[])
        docket_data = self._make_case(entry)

        first = FloridaDocketMerger(docket_data, params=None).merge()
        second = FloridaDocketMerger(docket_data, params=None).merge()

        assert first.success is True
        assert second.success is True
        assert "FloridaDocketEntry" not in second.creates
        assert FloridaDocketEntry.objects.count() == 1

    @merger_test(expected_query_count=28)
    def test_remerge_updates_entry_fields(self):
        """Does remerging an entry update its fields in place?"""
        entry = FloridaDocketEntryFactory.create(
            entry_status="Docketed", attachments=[]
        )
        docket_data = self._make_case(entry)
        FloridaDocketMerger(docket_data, params=None).merge()
        merged = FloridaDocketEntry.objects.get()

        entry.entry_status = "Stricken"
        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert merged.pk in result.updates["FloridaDocketEntry"]
        merged.refresh_from_db()
        self.assertEqual(merged.status, FloridaDocketEntry.STATUS_STRICKEN)

    @merger_test(expected_query_count=16)
    def test_merge_unrecognized_entry_status_is_unknown(self):
        """Is an entry status Florida hasn't shown us before stored as
        unknown rather than failing the merge?"""
        entry = FloridaDocketEntryFactory.create(
            entry_status="Surprising", attachments=[]
        )
        docket_data = self._make_case(entry)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        self.assertTrue(result.success)
        merged = FloridaDocketEntry.objects.get()
        self.assertEqual(merged.status, FloridaDocketEntry.STATUS_UNKNOWN)

    @merger_test(expected_query_count=12)
    def test_merge_submitted_by_links_docket_party(self):
        """Is a submitter that matches a party on the docket linked to that
        party?"""
        party = FloridaCasePartyFactory.create(
            name="Acme Corp", representatives=[]
        )
        entry = FloridaDocketEntryFactory.create(
            submitted_by=[
                FloridaCaseActorFactory.create(display_name="Acme Corp")
            ],
            attachments=[],
        )
        docket_data = FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            entries=[entry],
            parties=[party],
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        self.assertTrue(result.success)
        merged = FloridaDocketEntry.objects.get()
        self.assertEqual(merged.submitted_by_name, "Acme Corp")
        self.assertEqual(
            merged.submitted_by_id, Party.objects.get(name="Acme Corp").pk
        )

    @merger_test(expected_query_count=17)
    def test_merge_submitted_by_unknown_party_keeps_name_only(self):
        """Is a submitter who isn't a party on the docket -- court staff, for
        instance -- recorded by name with no party link?"""
        entry = FloridaDocketEntryFactory.create(
            submitted_by=[
                FloridaCaseActorFactory.create(display_name="Broward Clerk")
            ],
            attachments=[],
        )
        docket_data = self._make_case(entry)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        self.assertTrue(result.success)
        merged = FloridaDocketEntry.objects.get()
        self.assertEqual(merged.submitted_by_name, "Broward Clerk")
        self.assertIsNone(merged.submitted_by_id)

    @merger_test(expected_query_count=20)
    def test_remerge_keeps_resolved_submitted_by_party(self):
        """Does a later scrape that can't match the submitter keep the party
        we resolved earlier?"""
        party = FloridaCasePartyFactory.create(
            name="Acme Corp", representatives=[]
        )
        entry = FloridaDocketEntryFactory.create(
            submitted_by=[
                FloridaCaseActorFactory.create(display_name="Acme Corp")
            ],
            attachments=[],
        )
        docket_data = FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            entries=[entry],
            parties=[party],
        )
        FloridaDocketMerger(docket_data, params=None).merge()
        merged = FloridaDocketEntry.objects.get()
        resolved_party_id = merged.submitted_by_id
        self.assertIsNotNone(resolved_party_id)

        entry.submitted_by = []
        result = FloridaDocketMerger(docket_data, params=None).merge()

        self.assertTrue(result.success)
        merged.refresh_from_db()
        self.assertEqual(merged.submitted_by_id, resolved_party_id)
        self.assertEqual(merged.submitted_by_name, "")

    @merger_test(expected_query_count=29)
    def test_merge_keeps_entries_missing_from_scrape(self):
        """Are DB entries kept when a later scrape doesn't include them?"""
        first_entry = FloridaDocketEntryFactory.create(attachments=[])
        docket_data = self._make_case(first_entry)
        FloridaDocketMerger(docket_data, params=None).merge()

        docket_data.entries = [
            FloridaDocketEntryFactory.create(attachments=[])
        ]
        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert FloridaDocketEntry.objects.count() == 2

    @merger_test(expected_query_count=2)
    def test_entry_merger_standalone(self):
        """Can an entry be merged directly into an existing docket, outside
        of a full docket merge?"""
        docket = DocketFactory.create(court=self.flsc)
        entry = FloridaDocketEntryFactory.create(attachments=[])

        result = FloridaDocketEntryMerger(
            entry,
            manager=docket.florida_docket_entries,
            params=RelatedParams(None, parent=docket),
        ).merge()

        assert result.success is True
        merged = docket.florida_docket_entries.get()
        assert str(merged.docket_entry_uuid) == str(entry.docket_entry_uuid)


class FloridaDocumentMergerTest(TestCase):
    """Tests for merging documents attached to Florida docket entries."""

    @classmethod
    def setUpTestData(cls):
        cls.flsc = CourtFactory.create(id="fla")

    @staticmethod
    def _make_case(*documents) -> FloridaCase:
        entry = FloridaDocketEntryFactory.create(
            attachments=list(documents),
        )
        return FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            entries=[entry],
        )

    @merger_test(expected_query_count=18)
    def test_merge_creates_documents(self):
        """Does merging a case create its entries' documents with the
        scrape's field values?"""
        document = FloridaDocumentFactory.create(
            document_name="Initial Brief",
            document_type="Brief",
            content_type="application/pdf",
            page_count=12,
            file_size=34567,
            url="https://acis.flcourts.gov/docs/1",
        )
        docket_data = self._make_case(document)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert "FloridaDocument" in result.creates
        merged = FloridaDocument.objects.get()
        assert merged.docket_entry.docket_entry_uuid is not None
        assert str(merged.link_uuid) == str(document.document_link_uuid)
        assert merged.document_name == "Initial Brief"
        assert merged.document_type == "Brief"
        assert merged.content_type == "application/pdf"
        assert merged.page_count == 12
        assert merged.file_size == 34567
        assert merged.url == "https://acis.flcourts.gov/docs/1"

    @merger_test(expected_query_count=18)
    def test_merge_document_without_type_is_blank(self):
        """Is a scrape document with no document type merged with a blank
        string instead of None?"""
        document = FloridaDocumentFactory.create(document_type=None)
        docket_data = self._make_case(document)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        merged = FloridaDocument.objects.get()
        assert merged.document_type == ""

    @merger_test(expected_query_count=18)
    def test_merge_document_without_content_type_is_blank(self):
        """Is a scrape document with no content type merged with a blank
        string instead of None?"""
        document = FloridaDocumentFactory.create(content_type=None)
        docket_data = self._make_case(document)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        self.assertTrue(result.success)
        merged = FloridaDocument.objects.get()
        self.assertEqual(merged.content_type, "")

    @merger_test(expected_query_count=30)
    def test_remerge_documents_is_idempotent(self):
        """Does merging the same case twice avoid duplicating documents?"""
        document = FloridaDocumentFactory.create()
        docket_data = self._make_case(document)

        first = FloridaDocketMerger(docket_data, params=None).merge()
        second = FloridaDocketMerger(docket_data, params=None).merge()

        assert first.success is True
        assert second.success is True
        assert "FloridaDocument" not in second.creates
        assert FloridaDocument.objects.count() == 1

    @merger_test(expected_query_count=31)
    def test_merge_keeps_documents_missing_from_scrape(self):
        """Are DB documents kept when a later scrape doesn't include them?"""
        document = FloridaDocumentFactory.create()
        docket_data = self._make_case(document)
        FloridaDocketMerger(docket_data, params=None).merge()

        docket_data.entries[0].attachments = [FloridaDocumentFactory.create()]
        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert FloridaDocument.objects.count() == 2

    def _merge_downloaded_bad_url_document(self):
        """Merge a case, then flag its document as downloaded with a bad URL.

        Returns the scrape document and the merged FloridaDocument, set up so
        a re-merge exercises the pre_update download-state reset."""
        document = FloridaDocumentFactory.create(
            url="https://acis.flcourts.gov/docs/old",
        )
        docket_data = self._make_case(document)
        FloridaDocketMerger(docket_data, params=None).merge()

        merged = FloridaDocument.objects.get()
        merged.processing_error = ProcessingError.BAD_URL
        merged.filepath_local = "florida/old-file.pdf"
        merged.ocr_status = FloridaDocument.OCR_UNNECESSARY
        merged.save()
        return document, docket_data, merged

    @merger_test(expected_query_count=31)
    def test_remerge_changed_url_resets_download_state(self):
        """Does updating a document clear its bad-URL flag, stored file, and
        OCR status so it gets downloaded again?"""
        document, docket_data, merged = (
            self._merge_downloaded_bad_url_document()
        )

        document.url = "https://acis.flcourts.gov/docs/new"
        result = FloridaDocketMerger(docket_data, params=None).merge()

        self.assertTrue(result.success)
        self.assertIn(merged.pk, result.updates["FloridaDocument"])
        merged.refresh_from_db()
        self.assertEqual(merged.url, "https://acis.flcourts.gov/docs/new")
        self.assertIsNone(merged.processing_error)
        self.assertFalse(merged.filepath_local)
        self.assertIsNone(merged.ocr_status)

    @merger_test(expected_query_count=30)
    def test_remerge_missing_file_is_update(self):
        """Is an unchanged document with no stored file and no processing
        error reported as updated, so a re-ingest retries its failed
        download?"""
        document = FloridaDocumentFactory.create()
        docket_data = self._make_case(document)
        FloridaDocketMerger(docket_data, params=None).merge()
        merged = FloridaDocument.objects.get()

        result = FloridaDocketMerger(docket_data, params=None).merge()

        self.assertTrue(result.success)
        self.assertIn(merged.pk, result.updates["FloridaDocument"])

    @merger_test(expected_query_count=30)
    def test_remerge_unchanged_document_keeps_download_state(self):
        """Is download state (bad-URL flag, stored file, OCR status) left
        alone when the rescraped document is unchanged?"""
        _document, docket_data, merged = (
            self._merge_downloaded_bad_url_document()
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        self.assertTrue(result.success)
        self.assertNotIn("FloridaDocument", result.updates)
        merged.refresh_from_db()
        self.assertEqual(merged.processing_error, ProcessingError.BAD_URL)
        self.assertEqual(merged.filepath_local, "florida/old-file.pdf")
        self.assertEqual(merged.ocr_status, FloridaDocument.OCR_UNNECESSARY)


class FloridaCaseTransferMergerTest(TestCase):
    """Tests for merging case transfers from Florida cases."""

    @classmethod
    def setUpTestData(cls):
        cls.flsc = CourtFactory.create(id="fla")
        cls.flca01 = CourtFactory.create(id="fladistctapp1")
        cls.flacirct = CourtFactory.create(id="flacirct")

    @staticmethod
    def _make_case(*transfers, **kwargs) -> FloridaCase:
        return FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            docket_number="SC2025-4242",
            originating_cases=[],
            transfers=list(transfers),
            entries=[],
            parties=[],
            **kwargs,
        )

    @staticmethod
    def _circuit_transfer(**kwargs) -> DocketTransfer:
        values = {
            "court_id": FloridaCourtID.CIRCUIT.value,
            "docket_number": "2024-CA-001234",
        } | kwargs
        return FloridaDocketTransferFactory.create(**values)

    @staticmethod
    def _merged_docket(result: MergeResult) -> Docket:
        return Docket.objects.get(pk=next(iter(result.creates["Docket"])))

    def test_merge_creates_appeal_transfer_from_circuit_court(self):
        """Does merging create an appeal transfer from the originating
        circuit court into the scraped docket's court?"""
        docket_data = self._make_case(self._circuit_transfer())

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert "CaseTransfer" in result.creates
        docket = self._merged_docket(result)
        transfer = CaseTransfer.objects.get()
        assert transfer.origin_court_id == "flacirct"
        assert transfer.origin_docket_number == "2024-CA-001234"
        assert transfer.origin_docket is None
        assert transfer.destination_court_id == "fla"
        assert transfer.destination_docket_number == docket_data.docket_number
        assert transfer.destination_docket_id == docket.pk
        assert transfer.transfer_date == docket_data.date_filed
        assert transfer.transfer_type == CaseTransfer.APPEAL

    @merger_test(expected_query_count=8)
    def test_merge_creates_transfer_from_appellate_court(self):
        """Does a transfer from a district court of appeal map to its
        specific CourtListener court?"""
        docket_data = self._make_case(
            self._circuit_transfer(
                court_id=FloridaCourtID.FIRST_COA.value,
                docket_number="1D2023-1111",
            )
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        transfer = CaseTransfer.objects.get()
        assert transfer.origin_court_id == "fladistctapp1"
        assert transfer.origin_docket_number == "1D2023-1111"

    @merger_test(expected_query_count=11)
    def test_merge_creates_transfer_into_appellate_docket(self):
        """Are transfers created for district court of appeal dockets too?"""
        docket_data = FloridaCaseFactory.create(
            court_id=FloridaCourtID.FIRST_COA.value,
            docket_number="1D2025-0777",
            originating_cases=[],
            transfers=[self._circuit_transfer()],
            entries=[],
            parties=[],
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        transfer = CaseTransfer.objects.get()
        assert transfer.origin_court_id == "flacirct"
        assert transfer.destination_court_id == "fladistctapp1"
        assert transfer.destination_docket_id == self._merged_docket(result).pk

    @merger_test(expected_query_count=8)
    def test_merge_maps_transfer_reason(self):
        """Does the transfer's reason map to the matching CaseTransfer
        type?"""
        docket_data = self._make_case(
            self._circuit_transfer(reason=ScrapeTransferReason.WORKLOAD)
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        transfer = CaseTransfer.objects.get()
        assert transfer.transfer_type == CaseTransfer.WORKLOAD

    @merger_test(expected_query_count=12)
    def test_merge_creates_all_transfers(self):
        """Are multiple transfers merged as separate objects?"""
        docket_data = self._make_case(
            self._circuit_transfer(),
            self._circuit_transfer(docket_number="2023-CA-000999"),
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert set(
            CaseTransfer.objects.values_list(
                "origin_court_id", "origin_docket_number"
            )
        ) == {
            ("flacirct", "2024-CA-001234"),
            ("flacirct", "2023-CA-000999"),
        }

    @merger_test(expected_query_count=12)
    def test_remerge_is_idempotent(self):
        """Does merging the same case twice avoid duplicating transfers?"""
        docket_data = self._make_case(self._circuit_transfer())

        first = FloridaDocketMerger(docket_data, params=None).merge()
        second = FloridaDocketMerger(docket_data, params=None).merge()

        assert first.success is True
        assert second.success is True
        assert "CaseTransfer" not in second.creates
        assert "CaseTransfer" not in second.updates
        assert CaseTransfer.objects.count() == 1

    @merger_test(expected_query_count=8)
    def test_merge_fills_existing_partial_transfer(self):
        """Does merging fill in the destination docket FK on an existing
        transfer that only knows its origin docket?"""
        scrape_transfer = self._circuit_transfer()
        docket_data = self._make_case(scrape_transfer)
        origin_docket = DocketFactory.create(
            court=self.flacirct,
            docket_number=scrape_transfer.docket_number,
        )
        partial = CaseTransfer.objects.create(
            origin_court=self.flacirct,
            origin_docket_number=scrape_transfer.docket_number,
            origin_docket=origin_docket,
            destination_court=self.flsc,
            destination_docket_number=docket_data.docket_number,
            destination_docket=None,
            transfer_date=docket_data.date_filed,
            transfer_type=CaseTransfer.APPEAL,
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        self.assertTrue(result.success)
        self.assertNotIn("CaseTransfer", result.creates)
        self.assertIn(partial.pk, result.updates["CaseTransfer"])
        self.assertEqual(CaseTransfer.objects.count(), 1)
        partial.refresh_from_db()
        self.assertEqual(
            partial.destination_docket_id, self._merged_docket(result).pk
        )
        # The origin side set by the earlier merge is left alone.
        self.assertEqual(partial.origin_docket_id, origin_docket.pk)

    @merger_test(expected_query_count=4)
    def test_merge_skips_outbound_transfer(self):
        """Are outbound transfers skipped without failing the merge?"""
        docket_data = self._make_case(
            self._circuit_transfer(direction=ScrapeTransferDirection.OUTBOUND)
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert CaseTransfer.objects.count() == 0

    @merger_test(expected_query_count=4)
    def test_merge_skips_unknown_transfer_reason(self):
        """Are transfers whose reason has no CaseTransfer type skipped?"""
        docket_data = self._make_case(
            self._circuit_transfer(reason=ScrapeTransferReason.UNKNOWN)
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert CaseTransfer.objects.count() == 0

    @merger_test(expected_query_count=4)
    def test_merge_skips_unmappable_court(self):
        """Are transfers from courts with no CourtListener mapping skipped
        without failing the merge?"""
        docket_data = self._make_case(
            self._circuit_transfer(
                court_id=FloridaCourtID.COMPENSATION_CLAIMS.value
            )
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert CaseTransfer.objects.count() == 0

    @merger_test(expected_query_count=5)
    def test_merge_skips_court_missing_from_db(self):
        """Is a mappable court that isn't in the DB skipped without failing
        the merge?"""
        docket_data = self._make_case(
            self._circuit_transfer(court_id=FloridaCourtID.COUNTY.value)
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert CaseTransfer.objects.count() == 0

    @merger_test(expected_query_count=4)
    def test_merge_skips_empty_docket_number(self):
        """Is a transfer with no docket number skipped?"""
        docket_data = self._make_case(self._circuit_transfer(docket_number=""))

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert CaseTransfer.objects.count() == 0


class FloridaIngestTaskTest(TestCase):
    """Tests for the fl_ingest_docket_task Celery task."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.flsc = CourtFactory.create(id="fla")

    @staticmethod
    def _make_case() -> FloridaCase:
        """Build a supreme court case with one entry holding one attachment."""
        entry = FloridaDocketEntryFactory.create(
            attachments=[FloridaDocumentFactory.create()],
        )
        return FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            entries=[entry],
        )

    @mock.patch("cl.corpus_importer.tasks.download_fl_document.si")
    def test_ingest_merges_docket_and_dispatches_downloads(
        self, download_mock: mock.Mock
    ) -> None:
        """Does ingesting a case merge the docket and dispatch a download for
        each created document?"""
        case = self._make_case()

        with mock.patch(
            "cl.corpus_importer.tasks.FloridaCase.deserialize",
            return_value=case,
        ):
            result = fl_ingest_docket_task((b"{}", "bucket", "key"))

        self.assertTrue(result.success)
        self.assertIn("Docket", result.creates)
        self.assertIn("FloridaDocument", result.creates)
        document_pk = next(iter(result.creates["FloridaDocument"]))
        download_mock.assert_called_once_with(document_pk)
        download_mock.return_value.apply_async.assert_called_once()

    @mock.patch("cl.corpus_importer.tasks.download_fl_document.si")
    def test_ingest_skips_downloads_when_disabled(
        self, download_mock: mock.Mock
    ) -> None:
        """Does download_attachments=False merge documents without
        downloading them?"""
        case = self._make_case()

        with mock.patch(
            "cl.corpus_importer.tasks.FloridaCase.deserialize",
            return_value=case,
        ):
            result = fl_ingest_docket_task(
                (b"{}", "bucket", "key"), download_attachments=False
            )

        self.assertTrue(result.success)
        self.assertIn("FloridaDocument", result.creates)
        download_mock.assert_not_called()

    @mock.patch("cl.corpus_importer.tasks.download_fl_document.si")
    def test_ingest_invalid_case_fails(self, download_mock: mock.Mock) -> None:
        """Does an undeserializable payload fail the merge without raising or
        downloading anything?"""
        result = fl_ingest_docket_task((b"not json", "bucket", "key"))

        self.assertFalse(result.success)
        self.assertIn("Docket", result.failures)
        download_mock.assert_not_called()


class FloridaDocumentDownloadTest(TestCase):
    """Tests for the download_fl_document Celery task."""

    def setUp(self) -> None:
        """Mock the task throttle, the download stream, and the extraction
        task dispatch."""
        self.throttle_patch = mock.patch(
            "cl.lib.celery_utils.get_task_wait", return_value=0
        )
        self.throttle_patch.start()
        self.addCleanup(self.throttle_patch.stop)
        self.download_document_patch = mock.patch(
            "cl.corpus_importer.tasks.download_document_in_stream"
        )
        self.download_document_mock = self.download_document_patch.start()
        self.addCleanup(self.download_document_patch.stop)
        self.extract_document_patch = mock.patch(
            "cl.scrapers.tasks.extract_formatted_text_document.si"
        )
        self.extract_document_mock = self.extract_document_patch.start()
        self.addCleanup(self.extract_document_patch.stop)

    def _mock_downloaded_file(self, tmp, sha1: str) -> None:
        """Point the mocked download stream at an open temporary file."""
        self.download_document_mock.return_value.__enter__.return_value = (
            tmp,
            sha1,
        )

    @mock.patch("cl.lib.microservice_utils.doc_page_count_service")
    @mock.patch("cl.scrapers.utils.get_extension", return_value=".pdf")
    def test_download_pdf_success(
        self,
        ext_mock: mock.Mock,
        pcs_mock: mock.Mock,
    ) -> None:
        """Does a PDF download store the file, and dispatch extraction?"""
        fl_document = FloridaDocumentModelFactory.create()
        pcs_mock.return_value = httpx.Response(200, text="1")

        with NamedTemporaryFile(suffix=".tmp") as tmp:
            tmp.write(b"fake pdf data")
            tmp.flush()
            tmp.seek(0)
            self._mock_downloaded_file(tmp, "pdfsha1")

            result = download_fl_document(fl_document.pk)

        self.assertEqual(result, fl_document.pk)
        self.download_document_mock.assert_called_once_with(
            fl_document.url, fl_document.pk, "fl_", require_pdf=False
        )
        fl_document.refresh_from_db()
        self.assertTrue(fl_document.filepath_local)
        self.assertIn(".pdf", fl_document.filepath_local.name)
        self.assertEqual(fl_document.sha1, "pdfsha1")
        self.assertIsNone(fl_document.processing_error)
        self.extract_document_mock.assert_called_once_with(
            pks=fl_document.pk,
            check_if_needed=False,
            model_name="search.FloridaDocument",
            strip_html_tags=False,
        )

    def test_download_not_found(self) -> None:
        """Is a missing FloridaDocument handled gracefully?"""
        result = download_fl_document(99999)

        self.assertIsNone(result)
        self.download_document_mock.assert_not_called()

    def test_download_bad_url_skipped(self) -> None:
        """Is a document flagged with a bad URL skipped without downloading?"""
        fl_document = FloridaDocumentModelFactory.create(
            processing_error=ProcessingError.BAD_URL,
        )

        result = download_fl_document(fl_document.pk)

        self.assertIsNone(result)
        self.download_document_mock.assert_not_called()

    def test_download_failure(self) -> None:
        """Is a failed download handled gracefully?"""
        fl_document = FloridaDocumentModelFactory.create(
            url="https://example.com/sample.pdf",
        )
        self.download_document_mock.return_value.__enter__.return_value = None

        result = download_fl_document(fl_document.pk)

        self.assertIsNone(result)
        self.download_document_mock.assert_called_once_with(
            "https://example.com/sample.pdf",
            fl_document.pk,
            "fl_",
            require_pdf=False,
        )
        fl_document.refresh_from_db()
        self.assertFalse(fl_document.filepath_local)
        self.extract_document_mock.assert_not_called()

    @mock.patch("cl.search.state.shared.logger")
    @mock.patch("cl.scrapers.utils.get_extension", return_value=".tiff")
    def test_download_tiff_extracts_without_warning(
        self,
        ext_mock: mock.Mock,
        logger_mock: mock.Mock,
    ) -> None:
        """Is a TIFF (expected and extractable) stored and extracted with no
        unexpected-extension warning?"""
        fl_document = FloridaDocumentModelFactory.create()

        with NamedTemporaryFile(suffix=".tmp") as tmp:
            tmp.write(b"fake tiff data")
            tmp.flush()
            tmp.seek(0)
            self._mock_downloaded_file(tmp, "tiffsha1")

            result = download_fl_document(fl_document.pk)

        self.assertEqual(result, fl_document.pk)
        logger_mock.warning.assert_not_called()
        fl_document.refresh_from_db()
        self.assertTrue(fl_document.filepath_local)
        self.assertIn(".tiff", fl_document.filepath_local.name)
        self.assertEqual(fl_document.sha1, "tiffsha1")
        self.assertIsNone(fl_document.ocr_status)
        self.extract_document_mock.assert_called_once()

    @mock.patch("cl.search.state.shared.logger")
    @mock.patch("cl.scrapers.utils.get_extension", return_value=".html")
    def test_download_html_unexpected_but_extractable(
        self,
        ext_mock: mock.Mock,
        logger_mock: mock.Mock,
    ) -> None:
        """Is an HTML file (unexpected but extractable) stored with a warning
        and still sent to extraction?"""
        fl_document = FloridaDocumentModelFactory.create()

        with NamedTemporaryFile(suffix=".tmp") as tmp:
            tmp.write(b"<html>test</html>")
            tmp.flush()
            tmp.seek(0)
            self._mock_downloaded_file(tmp, "htmlsha1")

            result = download_fl_document(fl_document.pk)

        self.assertEqual(result, fl_document.pk)
        logger_mock.warning.assert_any_call(
            "Document download: Unexpected extension '%s' for %s %s from %s. Proceeding anyway.",
            ".html",
            "FloridaDocument",
            fl_document.pk,
            fl_document.url,
        )
        fl_document.refresh_from_db()
        self.assertIn(".html", fl_document.filepath_local.name)
        self.assertIsNone(fl_document.ocr_status)
        self.extract_document_mock.assert_called_once()

    @mock.patch("cl.search.state.shared.logger")
    @mock.patch("cl.scrapers.utils.get_extension", return_value=".docx")
    def test_download_unknown_extension_skips_extraction(
        self,
        ext_mock: mock.Mock,
        logger_mock: mock.Mock,
    ) -> None:
        """Is an unknown file type stored with a warning, marked
        OCR_UNNECESSARY, and kept out of extraction?"""
        fl_document = FloridaDocumentModelFactory.create()

        with NamedTemporaryFile(suffix=".tmp") as tmp:
            tmp.write(b"fake docx data")
            tmp.flush()
            tmp.seek(0)
            self._mock_downloaded_file(tmp, "docxsha1")

            result = download_fl_document(fl_document.pk)

        self.assertEqual(result, fl_document.pk)
        logger_mock.warning.assert_any_call(
            "Document download: Unexpected extension '%s' for %s %s from %s. Proceeding anyway.",
            ".docx",
            "FloridaDocument",
            fl_document.pk,
            fl_document.url,
        )
        fl_document.refresh_from_db()
        self.assertTrue(fl_document.filepath_local)
        self.assertEqual(
            fl_document.ocr_status, FloridaDocument.OCR_UNNECESSARY
        )
        self.assertIsNone(fl_document.processing_error)
        self.extract_document_mock.assert_not_called()
