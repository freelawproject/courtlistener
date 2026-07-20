"""Tests for Florida docket and originating-court-information merger."""

from datetime import date, datetime
from unittest import mock

from juriscraper.state.docket import PartyType as ScrapePartyType
from juriscraper.state.florida.cases import FloridaCase
from juriscraper.state.florida.courts import FloridaCourtID

from cl.corpus_importer.state.florida.factories import (
    FloridaCaseFactory,
    FloridaCasePartyFactory,
    FloridaDocketEntryFactory,
    FloridaOriginatingCaseFactory,
    FloridaRepresentativeFactory,
)
from cl.corpus_importer.state.florida.mergers import (
    FloridaDocketMerger,
)
from cl.corpus_importer.state.florida.utils import make_docket_number_core
from cl.corpus_importer.state.utils import MergeResult
from cl.people_db.factories import (
    AttorneyFactory,
    PartyFactory,
    PartyTypeFactory,
)
from cl.people_db.models import Attorney, Party, PartyType, Role
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import Docket, OriginatingCourtInformation
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
    def test_merge_skips_non_sc_oci(self, mock_merge: mock.Mock):
        """Does merge skip OCI merging for non-supreme-court dockets?"""
        docket_data = FloridaCaseFactory.create(
            court_id=FloridaCourtID.FIRST_COA.value,
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        mock_merge.assert_not_called()
        assert result.success is True

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

        assert result.success is True
        assert result.create is True
        assert "OriginatingCourtInformation" in result.creates
        oci_pk = next(iter(result.creates["OriginatingCourtInformation"]))
        oci = OriginatingCourtInformation.objects.get(pk=oci_pk)
        assert oci.docket_number == "ORIG-001"
        assert oci.docket_number_raw == "ORIG-001"

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

    def test_merge_docket_unknown_court_fails(self):
        """Does merge_docket fail when the court id is unknown?"""
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.CIRCUIT.value,
        )

        result = FloridaDocketMerger(docket_data, params=None).merge()

        self.assertEqual(result.success, False)
        self.assertIn("Docket", result.failures)
        self.assertEqual(result.failures["Docket"], [None])

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
        )
        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert result.update is True
        assert "Docket" in result.updates
        assert docket.pk in result.updates["Docket"]


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
        assert party_type.name == "appellant"

    def test_merge_creates_all_parties(self):
        """Are multiple parties in a scrape merged as separate objects, each
        with its own party type?"""
        appellant = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[],
        )
        appellee = FloridaCasePartyFactory.create(
            name="Bob Smith",
            party_type=ScrapePartyType.APPELLEE,
            representatives=[],
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
                "party__name", "name"
            )
        ) == {("Acme Corp", "appellant"), ("Bob Smith", "appellee")}

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

        first = FloridaDocketMerger(docket_data, params=None).merge()
        second = FloridaDocketMerger(docket_data, params=None).merge()

        assert first.success is True
        assert second.success is True
        assert second.create is False
        assert Party.objects.count() == 1
        assert Attorney.objects.count() == 1
        assert Role.objects.count() == 1
        assert PartyType.objects.count() == 1

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
