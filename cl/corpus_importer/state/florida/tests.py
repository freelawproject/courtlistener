"""Tests for Florida docket and originating-court-information merger."""

from datetime import date, datetime
from unittest import mock

from juriscraper.state.florida.courts import FloridaCourtID

from cl.corpus_importer.state.florida.factories import (
    FloridaCaseFactory,
    FloridaDocketEntryFactory,
    FloridaOriginatingCaseFactory,
)
from cl.corpus_importer.state.florida.mergers import (
    FloridaDocketMerger,
)
from cl.corpus_importer.state.florida.utils import make_docket_number_core
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import Docket, OriginatingCourtInformation
from cl.tests.cases import TestCase


class FloridaUtilsTest(TestCase):
    def test_docket_number_core(self) -> None:
        """Can we correctly normalize Texas docket numbers?"""
        self.assertEqual(make_docket_number_core("SC1983-2014"), "sc19832014")
        self.assertEqual(
            make_docket_number_core("SC1983-2014", court_id="fla"),
            "sc19832014",
        )
        self.assertEqual(
            make_docket_number_core("3D2001-20145", court_id="fla"),
            "3D2001-20145",
        )
        self.assertEqual(
            make_docket_number_core("Meowdy, partner", court_id="tx"),
            "Meowdy, partner",
        )
        self.assertEqual(
            make_docket_number_core("3D2001-20145", court_id="fladistctapp2"),
            "3d200120145",
        )
        self.assertEqual(
            make_docket_number_core("SC1983-2014", court_id="fladistctapp2"),
            "SC1983-2014",
        )
        self.assertEqual(
            make_docket_number_core("WR-70,849-04"), "WR-70,849-04"
        )

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

        self.assertEqual(
            make_docket_number_core("garbage text"), "garbage text"
        )


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
        assert result.create is False
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
        assert result.create is False
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
        assert new_docket.case_name_short == docket_data.case_name
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
        agg_dn = "1D2025-AGG"
        agg_docket = DocketFactory.create(
            court=self.flagg,
            docket_number=agg_dn,
            docket_number_raw=agg_dn,
            docket_number_core="",
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
