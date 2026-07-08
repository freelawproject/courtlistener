"""Tests for Florida docket and originating-court-information merger."""

from copy import copy
from datetime import date, datetime
from unittest import mock

from juriscraper.state.docket import (
    DocketEntryType as ScrapeDocketEntryType,
)
from juriscraper.state.docket import PartyType as ScrapePartyType
from juriscraper.state.florida.cases import FloridaCase
from juriscraper.state.florida.courts import FloridaCourtID

from cl.corpus_importer.state.florida.factories import (
    FloridaCaseFactory,
    FloridaCasePartyFactory,
    FloridaDocketEntryFactory,
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
from cl.corpus_importer.state.utils import MergeResult
from cl.people_db.factories import (
    AttorneyFactory,
    PartyFactory,
    PartyTypeFactory,
)
from cl.people_db.models import Attorney, Party, PartyType, Role
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import Docket, OriginatingCourtInformation
from cl.search.state.florida.models import (
    FloridaDocketEntry,
    FloridaDocument,
)
from cl.search.state.shared import DocketEntryType
from cl.tests.cases import TestCase


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

        merger = FloridaDocketMerger(docket_data, params=None)

        assert merger.result is not None
        assert merger.result.success is False
        assert "Docket" in merger.result.failures

        before = copy(merger.result)
        after = merger.merge()

        assert before == after

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
        agg_dn = "1D2025-AGG"
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

    def test_merge_creates_docket_entries(self):
        """Does merging a case create its docket entries with the scrape's
        field values?"""
        entry = FloridaDocketEntryFactory.create(
            entry_type=ScrapeDocketEntryType.MOTION,
            entry_type_raw="motions other",
            entry_name="Motion for Extension",
            entry_description="Requesting more time.",
            entry_status="Filed",
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
        assert merged.status == "Filed"

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

    def test_remerge_updates_entry_fields(self):
        """Does remerging an entry update its fields in place?"""
        entry = FloridaDocketEntryFactory.create(
            entry_status="Filed", attachments=[]
        )
        docket_data = self._make_case(entry)
        FloridaDocketMerger(docket_data, params=None).merge()
        merged = FloridaDocketEntry.objects.get()

        entry.entry_status = "Disposed"
        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert merged.pk in result.updates["FloridaDocketEntry"]
        merged.refresh_from_db()
        assert merged.status == "Disposed"

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

    def test_merge_document_without_type_is_blank(self):
        """Is a scrape document with no document type merged with a blank
        string instead of None?"""
        document = FloridaDocumentFactory.create(document_type=None)
        docket_data = self._make_case(document)

        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        merged = FloridaDocument.objects.get()
        assert merged.document_type == ""

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

    def test_merge_keeps_documents_missing_from_scrape(self):
        """Are DB documents kept when a later scrape doesn't include them?"""
        document = FloridaDocumentFactory.create()
        docket_data = self._make_case(document)
        FloridaDocketMerger(docket_data, params=None).merge()

        docket_data.entries[0].attachments = [FloridaDocumentFactory.create()]
        result = FloridaDocketMerger(docket_data, params=None).merge()

        assert result.success is True
        assert FloridaDocument.objects.count() == 2
