"""Tests for Florida docket and originating-court-information merger."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from tempfile import NamedTemporaryFile
from typing import IO
from unittest import mock
from uuid import uuid4

import httpx
import requests
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
from juriscraper.state.florida.parties import FloridaParty

from cl.corpus_importer.management.commands.state_document_download import (
    extract_state_documents,
)
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
from cl.corpus_importer.state.merger import (
    MergerState,
    RelatedParams,
    Update,
)
from cl.corpus_importer.state.merger.tests import (
    merged_docket,
    merger_test,
    table_row,
)
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
    FloridaDocketEntryFactory as FloridaDocketEntryModelFactory,
)
from cl.search.state.florida.factories import (
    FloridaDocumentFactory as FloridaDocumentModelFactory,
)
from cl.search.state.florida.models import (
    FloridaDocketEntry,
    FloridaDocument,
)
from cl.search.state.shared import (
    CourtRefused,
    DocketEntryType,
    ProcessingError,
)
from cl.tests.cases import TestCase


def merge_case(case: FloridaCase) -> MergeResult:
    """Run a full docket merge of a scraped Florida case."""
    return FloridaDocketMerger(case, params=case.entries).merge()


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
    @merger_test(expected_query_count=13)
    def test_merge_skips_non_sc_oci(self, mock_merge: mock.Mock):
        """Does merge skip OCI merging for non-supreme-court dockets?"""
        docket_data = FloridaCaseFactory.create(
            court_id=FloridaCourtID.FIRST_COA.value,
        )

        result = merge_case(docket_data)

        mock_merge.assert_not_called()
        self.assertTrue(result.success)

    @merger_test(expected_query_count=12)
    def test_merge_creates_new_oci_from_first_originating_case(self):
        """Does merge create a new OCI from the first of the case's originating cases when the docket has none?"""
        self.docket_sc.originating_court_information = None
        self.docket_sc.save()

        docket_data = FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            originating_cases=[
                FloridaOriginatingCaseFactory.build(case_number="FIRST-001"),
                FloridaOriginatingCaseFactory.build(case_number="SECOND-002"),
            ],
        )

        result = FloridaDocketMerger(
            docket_data,
            existing=Update(self.docket_sc),
            params=docket_data.entries,
        ).merge()

        self.assertTrue(result.success)
        self.assertTrue(result.create)
        self.assertIn("OriginatingCourtInformation", result.creates)
        oci_pk = next(iter(result.creates["OriginatingCourtInformation"]))
        oci = OriginatingCourtInformation.objects.get(pk=oci_pk)
        self.assertEqual(oci.docket_number, "FIRST-001")
        self.assertEqual(oci.docket_number_raw, "FIRST-001")
        self.docket_sc.refresh_from_db()
        self.assertEqual(
            self.docket_sc.originating_court_information_id, oci_pk
        )

    @merger_test(expected_query_count=12)
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
            docket_data,
            existing=Update(self.docket_sc),
            params=docket_data.entries,
        ).merge()

        self.assertTrue(result.success)
        self.assertTrue(result.update)
        self.assertNotIn("OriginatingCourtInformation", result.creates)
        self.assertIn(
            existing_oci.pk, result.updates["OriginatingCourtInformation"]
        )
        existing_oci.refresh_from_db()
        self.assertEqual(existing_oci.docket_number, "UPDATED-001")
        self.assertEqual(existing_oci.docket_number_raw, "UPDATED-001")

    @merger_test(expected_query_count=11)
    def test_merge_no_originating_cases_skips_oci(self):
        """Does merge skip OCI merging when there are no originating cases?"""
        self.docket_sc.originating_court_information = None
        self.docket_sc.save()

        docket_data = FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            originating_cases=[],
        )

        result = FloridaDocketMerger(
            docket_data,
            existing=Update(self.docket_sc),
            params=docket_data.entries,
        ).merge()

        self.assertTrue(result.success)
        self.assertNotIn("OriginatingCourtInformation", result.creates)
        self.assertNotIn("OriginatingCourtInformation", result.updates)

    @merger_test(expected_query_count=0)
    def test_merge_docket_unknown_court_fails(self):
        """Does merge_docket fail when the court id is unknown?"""
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.CIRCUIT.value,
        )

        result = merge_case(docket_data)

        self.assertEqual(result.success, False)
        self.assertIn("Docket", result.failures)
        self.assertEqual(result.failures["Docket"], [None])

    @merger_test(expected_query_count=24)
    def test_merge_docket_creates_new_in_specific_court(self):
        """Does merge_docket create a new docket in the case's specific CourtListener court, carrying the scrape's names and filing date, when no existing docket matches?"""
        cases = (
            (FloridaCourtID.SUPREME_COURT, "SC2025-9999", "fla"),
            (FloridaCourtID.SECOND_COA, "2D2025-BRAND-NEW", "fladistctapp2"),
        )
        for court_id, docket_number, cl_court_id in cases:
            with table_row(self, cl_court_id):
                original_pks = set(Docket.objects.values_list("pk", flat=True))
                docket_data = FloridaCaseFactory(
                    court_id=court_id.value,
                    docket_number=docket_number,
                    entries=[],
                )

                result = merge_case(docket_data)

                self.assertTrue(result.success)
                new_pks = (
                    set(Docket.objects.values_list("pk", flat=True))
                    - original_pks
                )
                self.assertEqual(len(new_pks), 1)
                new_pk = new_pks.pop()
                self.assertIn(new_pk, result.creates["Docket"])
                new_docket = Docket.objects.get(pk=new_pk)
                self.assertEqual(new_docket.court_id, cl_court_id)
                self.assertEqual(new_docket.docket_number, docket_number)
                self.assertEqual(new_docket.docket_number_raw, docket_number)
                self.assertEqual(new_docket.case_name, docket_data.case_name)
                self.assertEqual(
                    new_docket.case_name_full, docket_data.case_name_full
                )
                self.assertEqual(
                    new_docket.case_name_short, docket_data.case_name_short
                )
                self.assertEqual(new_docket.date_filed, docket_data.date_filed)

    @merger_test(expected_query_count=12)
    def test_merge_docket_existing_supreme_court_is_update(self):
        """Does merge_docket update an existing supreme-court docket in place?"""
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            docket_number=self.docket_number_sc,
            entries=[],
        )

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertIn("Docket", result.updates)
        self.assertIn(self.docket_sc.pk, result.updates["Docket"])
        self.assertNotIn(
            self.docket_sc.pk, result.creates.get("Docket", set())
        )
        self.docket_sc.refresh_from_db()
        self.assertEqual(self.docket_sc.case_name, docket_data.case_name)

    @merger_test(expected_query_count=16)
    def test_merge_docket_appellate_disaggregates_existing(self):
        """Does merge_docket move a matching docket from the aggregate court into its specific district court?"""
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

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertIn("Docket", result.updates)
        self.assertIn(agg_docket.pk, result.updates["Docket"])
        agg_docket.refresh_from_db()
        self.assertEqual(agg_docket.court_id, "fladistctapp1")

    @merger_test(expected_query_count=16)
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

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.docket_sc.refresh_from_db()
        self.assertEqual(self.docket_sc.date_last_filing, date(2025, 3, 10))

    @merger_test(expected_query_count=12)
    def test_merge_docket_no_entries_falls_back_to_date_filed(self):
        """When there are no entries, does date_last_filing fall back to date_filed?"""
        filed = datetime(2024, 6, 15, 12, 0, 0)
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            docket_number=self.docket_number_sc,
            datetime_filed=filed,
            entries=[],
        )

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.docket_sc.refresh_from_db()
        self.assertEqual(self.docket_sc.date_filed, filed.date())
        self.assertEqual(self.docket_sc.date_last_filing, filed.date())

    @merger_test(expected_query_count=13)
    def test_uuid_matches(self):
        """Does case_uuid correctly map as a lookup to pacer_case_id?"""
        docket_data = FloridaCaseFactory(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            docket_number="SC2026-1337",
        )
        docket = DocketFactory.create(
            court=self.flsc,
            docket_number=docket_data.docket_number,
            docket_number_core=make_docket_number_core(
                docket_data.docket_number
            ),
            pacer_case_id=str(docket_data.case_uuid),
            # A random RECAP source makes Docket.save query the court table,
            # making the query count above flaky.
            source=Docket.SCRAPER,
        )
        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertTrue(result.update)
        self.assertIn("Docket", result.updates)
        self.assertIn(docket.pk, result.updates["Docket"])


class FloridaPartyMergerTest(TestCase):
    """Tests for merging parties, attorneys, and attorney roles from Florida cases."""

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
    def _represented_party() -> FloridaParty:
        """Build an appellant scraped with one primary representative."""
        return FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[
                FloridaRepresentativeFactory.create(
                    name="Jane Lawyer", primary_flag=True
                )
            ],
        )

    @merger_test(expected_query_count=11)
    def test_merge_creates_all_parties(self):
        """Are multiple parties in a scrape merged as separate objects, each linked to the docket by its own party type?"""
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

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertIn("Party", result.creates)
        docket = merged_docket(result)
        self.assertEqual(
            set(docket.parties.values_list("name", flat=True)),
            {"Acme Corp", "Bob Smith"},
        )
        self.assertEqual(
            set(
                PartyType.objects.filter(docket=docket).values_list(
                    "party__name", "name", "pro_se"
                )
            ),
            {
                ("Acme Corp", "Appellant", PartyType.PRO_SE_NO),
                ("Bob Smith", "Appellee", PartyType.PRO_SE_YES),
            },
        )

    @merger_test(expected_query_count=15)
    def test_merge_representatives_become_attorneys_with_roles(self):
        """Is each of a party's representatives merged as a separate, named attorney, linked to the party on the merged docket as lead attorney when primary and with the unknown role otherwise?"""
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

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        docket = merged_docket(result)
        party = docket.parties.get()
        self.assertEqual(party.attorneys.count(), 2)
        self.assertEqual(
            set(
                Role.objects.filter(party=party).values_list(
                    "attorney__name", "role", "docket_id"
                )
            ),
            {
                ("Jane Lawyer", Role.ATTORNEY_LEAD, docket.pk),
                ("John Counsel", Role.UNKNOWN, docket.pk),
            },
        )

    @merger_test(expected_query_count=22)
    def test_remerge_is_idempotent(self):
        """Does merging the same case twice avoid duplicating parties, attorneys, and their links?"""
        docket_data = self._make_case(self._represented_party())

        first_merger = FloridaDocketMerger(
            docket_data, params=docket_data.entries
        )
        first = first_merger.merge()
        second_merger = FloridaDocketMerger(
            docket_data, params=docket_data.entries
        )
        second = second_merger.merge()

        match first_merger.state, second_merger.state:
            case MergerState.Complete(output=first_db), MergerState.Complete(
                output=second_db
            ):
                self.assertEqual(first_db, second_db)
            case states:
                self.fail(f"Merges did not complete: {states}")
        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertFalse(second.create)
        self.assertFalse(second.update)
        self.assertEqual(Party.objects.count(), 1)
        self.assertEqual(Attorney.objects.count(), 1)
        self.assertEqual(Role.objects.count(), 1)
        self.assertEqual(PartyType.objects.count(), 1)

    @merger_test(expected_query_count=13)
    def test_merge_leaves_other_dockets_parties_alone(self):
        """Does merging one docket create its own party rather than renaming a party on another docket, and leave that party's types and attorney roles in place?"""
        other_docket = DocketFactory.create(court=self.flsc)
        other_party = PartyFactory.create(
            name="Unrelated Party",
            docket=other_docket,
            attorneys=[AttorneyFactory.create(docket=other_docket)],
        )
        other_party_type = PartyTypeFactory.create(
            docket=other_docket, party=other_party, name="plaintiff"
        )
        other_role = Role.objects.get(party=other_party)
        docket_data = self._make_case(self._represented_party())

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        other_party.refresh_from_db()
        self.assertEqual(other_party.name, "Unrelated Party")
        self.assertEqual(
            list(merged_docket(result).parties.values_list("name", flat=True)),
            ["Acme Corp"],
        )
        self.assertTrue(
            PartyType.objects.filter(pk=other_party_type.pk).exists()
        )
        self.assertTrue(Role.objects.filter(pk=other_role.pk).exists())
        other_role.refresh_from_db()
        # pyrefly:ignore[missing-attribute]
        self.assertEqual(other_role.docket_id, other_docket.pk)

    @merger_test(expected_query_count=16)
    def test_party_type_change_renames_in_place(self):
        """When a party's type changes between scrapes, is the single PartyType row renamed rather than duplicated?"""
        scrape_party = FloridaCasePartyFactory.create(
            name="Acme Corp",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[],
        )
        docket_data = self._make_case(scrape_party)
        first = merge_case(docket_data)
        self.assertTrue(first.success)
        docket = merged_docket(first)

        scrape_party.party_type = ScrapePartyType.APPELLEE
        second = merge_case(docket_data)

        self.assertTrue(second.success)
        party_type = PartyType.objects.get(docket=docket)
        self.assertEqual(party_type.name, "Appellee")

    @merger_test(expected_query_count=17)
    def test_remerge_keeps_same_name_parties_distinct(self):
        """When two parties on a docket share a name (e.g. a cross-appellant), does a re-merge match each by its UUID rather than collapsing both onto one party?"""
        appellant = FloridaCasePartyFactory.create(
            name="State of Florida",
            party_type=ScrapePartyType.APPELLANT,
            representatives=[],
        )
        appellee = FloridaCasePartyFactory.create(
            name="State of Florida",
            party_type=ScrapePartyType.APPELLEE,
            representatives=[],
        )
        docket_data = self._make_case(appellant, appellee)
        first = merge_case(docket_data)
        self.assertTrue(first.success)
        docket = merged_docket(first)

        second = merge_case(docket_data)

        self.assertTrue(second.success, second.failures)
        self.assertFalse(second.create)
        self.assertFalse(second.update)
        self.assertEqual(Party.objects.count(), 2)
        self.assertEqual(
            {
                (pt.party.extra_info, pt.name)
                for pt in PartyType.objects.filter(docket=docket)
            },
            {
                (str(appellant.party_uuid), "Appellant"),
                (str(appellee.party_uuid), "Appellee"),
            },
        )

    @merger_test(expected_query_count=17)
    def test_merge_empty_parties_preserves_existing(self):
        """Does a scrape with no parties leave existing parties, types, and roles untouched?"""
        docket_data = self._make_case(self._represented_party())
        first = merge_case(docket_data)
        self.assertTrue(first.success)
        docket = merged_docket(first)

        docket_data.parties = []
        second = merge_case(docket_data)

        self.assertTrue(second.success)
        self.assertEqual(docket.parties.count(), 1)
        self.assertEqual(PartyType.objects.filter(docket=docket).count(), 1)
        self.assertEqual(Role.objects.filter(docket=docket).count(), 1)

    @merger_test(expected_query_count=22)
    def test_same_named_attorneys_on_one_party_fail(self):
        """Do two representatives of one party who share a name both fail, since nothing tells the stored attorneys apart, and are the party's roles left in place rather than pruned?"""
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
        first = merge_case(docket_data)
        self.assertTrue(first.success)
        docket = merged_docket(first)
        roles = set(
            Role.objects.filter(docket=docket).values_list("pk", flat=True)
        )

        second_chair.name = "Jane Lawyer"
        second = merge_case(docket_data)

        self.assertEqual(second.failures["Attorney"], [None, None])
        self.assertEqual(
            set(
                Role.objects.filter(docket=docket).values_list("pk", flat=True)
            ),
            roles,
        )
        self.assertEqual(
            set(Attorney.objects.values_list("name", flat=True)),
            {"Jane Lawyer", "John Counsel"},
        )


class FloridaDocketEntryMergerTest(TestCase):
    """Tests for merging docket entries from Florida cases."""

    @classmethod
    def setUpTestData(cls):
        cls.flsc = CourtFactory.create(id="fla")

    @staticmethod
    def _make_case(*entries, **kwargs) -> FloridaCase:
        return FloridaCaseFactory.create(
            court_id=FloridaCourtID.SUPREME_COURT.value,
            entries=list(entries),
            **kwargs,
        )

    @merger_test(expected_query_count=15)
    def test_merge_creates_docket_entries(self):
        """Does merging a case create each of its docket entries as a separate object with the scrape's field values?"""
        entry = FloridaDocketEntryFactory.create(
            entry_type=ScrapeDocketEntryType.MOTION,
            entry_type_raw="motions other",
            entry_name="Motion for Extension",
            entry_description="Requesting more time.",
            entry_status="Docketed",
            attachments=[],
        )
        others = [
            FloridaDocketEntryFactory.create(attachments=[]) for _ in range(2)
        ]
        docket_data = self._make_case(entry, *others)

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertIn("FloridaDocketEntry", result.creates)
        # pyrefly:ignore[missing-attribute]
        merged_entries = merged_docket(result).florida_docket_entries
        self.assertEqual(merged_entries.count(), 3)
        self.assertEqual(
            {
                str(uuid)
                for uuid in merged_entries.values_list(
                    "docket_entry_uuid", flat=True
                )
            },
            {str(e.docket_entry_uuid) for e in (entry, *others)},
        )
        merged = merged_entries.get(
            docket_entry_uuid=str(entry.docket_entry_uuid)
        )
        self.assertEqual(merged.date_filed, entry.datetime_filed)
        self.assertEqual(merged.date_submitted, entry.date_submitted)
        self.assertEqual(merged.entry_type, DocketEntryType.MOTION)
        self.assertEqual(merged.entry_type_raw, "motions other")
        self.assertEqual(merged.entry_name, "Motion for Extension")
        self.assertEqual(merged.description, "Requesting more time.")
        self.assertEqual(merged.status, FloridaDocketEntry.STATUS_DOCKETED)
        self.assertEqual(merged.submitted_by_name, "")
        self.assertIsNone(merged.submitted_by_id)

    @merger_test(expected_query_count=22)
    def test_remerge_entries_is_idempotent(self):
        """Does merging the same case twice avoid duplicating entries?"""
        docket_data = self._make_case(
            FloridaDocketEntryFactory.create(attachments=[])
        )

        first = merge_case(docket_data)
        second = merge_case(docket_data)

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertNotIn("FloridaDocketEntry", second.creates)
        self.assertEqual(FloridaDocketEntry.objects.count(), 1)

    @merger_test(expected_query_count=23)
    def test_remerge_updates_entry_fields(self):
        """Does remerging an entry update its fields in place?"""
        entry = FloridaDocketEntryFactory.create(
            entry_status="Docketed", attachments=[]
        )
        docket_data = self._make_case(entry)
        merge_case(docket_data)
        merged = FloridaDocketEntry.objects.get()

        entry.entry_status = "Stricken"
        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertIn(merged.pk, result.updates["FloridaDocketEntry"])
        merged.refresh_from_db()
        self.assertEqual(merged.status, FloridaDocketEntry.STATUS_STRICKEN)

    @merger_test(expected_query_count=13)
    def test_merge_unrecognized_entry_status_is_unknown(self):
        """Is an entry status Florida hasn't shown us before stored as unknown rather than failing the merge?"""
        docket_data = self._make_case(
            FloridaDocketEntryFactory.create(
                entry_status="Surprising", attachments=[]
            )
        )

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        merged = FloridaDocketEntry.objects.get()
        self.assertEqual(merged.status, FloridaDocketEntry.STATUS_UNKNOWN)

    @merger_test(expected_query_count=17)
    def test_submitted_by_party_link_survives_remerge(self):
        """Is a submitter that matches a party on the docket linked to that party, and does a later scrape that can't match the submitter keep that link?"""
        entry = FloridaDocketEntryFactory.create(
            submitted_by=[
                FloridaCaseActorFactory.create(display_name="Acme Corp")
            ],
            attachments=[],
        )
        docket_data = self._make_case(
            entry,
            parties=[
                FloridaCasePartyFactory.create(
                    name="Acme Corp", representatives=[]
                )
            ],
        )
        first = merge_case(docket_data)
        self.assertTrue(first.success)
        merged = FloridaDocketEntry.objects.get()
        self.assertEqual(merged.submitted_by_name, "Acme Corp")
        resolved_party_id = Party.objects.get(name="Acme Corp").pk
        # pyrefly:ignore[missing-attribute]
        self.assertEqual(merged.submitted_by_id, resolved_party_id)

        entry.submitted_by = []
        result = merge_case(docket_data)

        self.assertTrue(result.success)
        merged.refresh_from_db()
        # pyrefly:ignore[missing-attribute]
        self.assertEqual(merged.submitted_by_id, resolved_party_id)
        self.assertEqual(merged.submitted_by_name, "")

    @merger_test(expected_query_count=14)
    def test_merge_submitted_by_unknown_party_keeps_name_only(self):
        """Is a submitter who isn't a party on the docket -- court staff, for instance -- recorded by name with no party link?"""
        docket_data = self._make_case(
            FloridaDocketEntryFactory.create(
                submitted_by=[
                    FloridaCaseActorFactory.create(
                        display_name="Broward Clerk"
                    )
                ],
                attachments=[],
            )
        )

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        merged = FloridaDocketEntry.objects.get()
        self.assertEqual(merged.submitted_by_name, "Broward Clerk")
        # pyrefly:ignore[missing-attribute]
        self.assertIsNone(merged.submitted_by_id)

    @merger_test(expected_query_count=24)
    def test_merge_keeps_entries_missing_from_scrape(self):
        """Are DB entries kept when a later scrape doesn't include them?"""
        docket_data = self._make_case(
            FloridaDocketEntryFactory.create(attachments=[])
        )
        merge_case(docket_data)

        docket_data.entries = [
            FloridaDocketEntryFactory.create(attachments=[])
        ]
        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertEqual(FloridaDocketEntry.objects.count(), 2)

    @merger_test(expected_query_count=2)
    def test_entry_merger_standalone(self):
        """Can an entry be merged directly into an existing docket, outside of a full docket merge?"""
        docket = DocketFactory.create(court=self.flsc)
        entry = FloridaDocketEntryFactory.create(attachments=[])

        result = FloridaDocketEntryMerger(
            entry,
            # pyrefly:ignore[missing-attribute]
            manager=docket.florida_docket_entries,
            params=RelatedParams([entry], parent=docket),
        ).merge()

        self.assertTrue(result.success)
        # pyrefly:ignore[missing-attribute]
        merged = docket.florida_docket_entries.get()
        self.assertEqual(
            str(merged.docket_entry_uuid), str(entry.docket_entry_uuid)
        )


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

    @merger_test(expected_query_count=17)
    def test_merge_creates_documents(self):
        """Does merging a case create its entries' documents with the scrape's field values?"""
        document = FloridaDocumentFactory.create(
            document_name="Initial Brief",
            document_type="Brief",
            content_type="application/pdf",
            page_count=12,
            file_size=34567,
            url="https://acis.flcourts.gov/docs/1",
        )
        docket_data = self._make_case(document)

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertIn("FloridaDocument", result.creates)
        merged = FloridaDocument.objects.get()
        self.assertIsNotNone(merged.docket_entry.docket_entry_uuid)
        self.assertEqual(
            str(merged.link_uuid), str(document.document_link_uuid)
        )
        self.assertEqual(merged.document_name, "Initial Brief")
        self.assertEqual(merged.document_type, "Brief")
        self.assertEqual(merged.content_type, "application/pdf")
        self.assertEqual(merged.page_count, 12)
        self.assertEqual(merged.file_size, 34567)
        self.assertEqual(merged.url, "https://acis.flcourts.gov/docs/1")

    @merger_test(expected_query_count=34)
    def test_merge_document_missing_optional_text_is_blank(self):
        """Is a scrape document with no document type or no content type merged with a blank string instead of None?"""
        for field in ("document_type", "content_type"):
            with table_row(self, field):
                docket_data = self._make_case(
                    FloridaDocumentFactory.create(**{field: None})
                )

                result = merge_case(docket_data)

                self.assertTrue(result.success)
                merged = FloridaDocument.objects.get()
                self.assertEqual(getattr(merged, field), "")

    @merger_test(expected_query_count=27)
    def test_remerge_documents_is_idempotent(self):
        """Does merging the same case twice match the stored document rather than duplicating it, and report it as updated while it has no stored file and no processing error, so a re-ingest retries its failed download?"""
        docket_data = self._make_case(FloridaDocumentFactory.create())

        first = merge_case(docket_data)
        merged = FloridaDocument.objects.get()
        second = merge_case(docket_data)

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertNotIn("FloridaDocument", second.creates)
        self.assertIn(merged.pk, second.updates["FloridaDocument"])
        self.assertEqual(FloridaDocument.objects.count(), 1)

    @merger_test(expected_query_count=31)
    def test_merge_removes_documents_missing_from_scrape(self):
        """Are DB documents deleted when a later scrape doesn't include them?"""
        docket_data = self._make_case(FloridaDocumentFactory.create())
        merge_case(docket_data)
        stale = FloridaDocument.objects.get()

        replacement = FloridaDocumentFactory.create()
        docket_data.entries[0].attachments = [replacement]
        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertEqual(
            list(FloridaDocument.objects.values_list("link_uuid", flat=True)),
            [replacement.document_link_uuid],
        )
        self.assertFalse(FloridaDocument.objects.filter(pk=stale.pk).exists())

    def _merge_downloaded_bad_url_document(self):
        """Merge a case, then flag its document as downloaded with a bad URL.

        Returns the scrape document and the merged FloridaDocument, set up so
        a re-merge exercises the pre_update download-state reset.
        """
        document = FloridaDocumentFactory.create(
            url="https://acis.flcourts.gov/docs/old",
        )
        docket_data = self._make_case(document)
        merge_case(docket_data)

        merged = FloridaDocument.objects.get()
        merged.processing_error = ProcessingError.BAD_URL
        merged.filepath_local = "florida/old-file.pdf"
        merged.ocr_status = FloridaDocument.OCR_UNNECESSARY
        merged.save()
        return document, docket_data, merged

    @merger_test(expected_query_count=28)
    def test_remerge_changed_url_resets_download_state(self):
        """Does updating a document clear its bad-URL flag, stored file, and OCR status so it gets downloaded again?"""
        document, docket_data, merged = (
            self._merge_downloaded_bad_url_document()
        )

        document.url = "https://acis.flcourts.gov/docs/new"
        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertIn(merged.pk, result.updates["FloridaDocument"])
        merged.refresh_from_db()
        self.assertEqual(merged.url, "https://acis.flcourts.gov/docs/new")
        self.assertIsNone(merged.processing_error)
        self.assertFalse(merged.filepath_local)
        self.assertIsNone(merged.ocr_status)

    @merger_test(expected_query_count=27)
    def test_remerge_unchanged_document_keeps_download_state(self):
        """Is download state (bad-URL flag, stored file, OCR status) left alone when the rescraped document is unchanged?"""
        _document, docket_data, merged = (
            self._merge_downloaded_bad_url_document()
        )

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertNotIn("FloridaDocument", result.updates)
        merged.refresh_from_db()
        self.assertEqual(merged.processing_error, ProcessingError.BAD_URL)
        self.assertEqual(merged.filepath_local, "florida/old-file.pdf")
        self.assertEqual(merged.ocr_status, FloridaDocument.OCR_UNNECESSARY)

    def test_remerge_changed_link_uuid_updates_document_in_place(self):
        """Is a document whose link UUID changed between scrapes matched on its title and updated, rather than duplicated?"""
        document = FloridaDocumentFactory.create()
        docket_data = self._make_case(document)
        merge_case(docket_data)
        merged = FloridaDocument.objects.get()

        document.document_link_uuid = uuid4()
        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertNotIn("FloridaDocument", result.creates)
        self.assertEqual(result.updates["FloridaDocument"], {merged.pk})
        merged.refresh_from_db()
        self.assertEqual(merged.link_uuid, document.document_link_uuid)
        self.assertEqual(FloridaDocument.objects.count(), 1)

    def test_merge_same_title_distinct_link_uuids_stay_separate(self):
        """Are documents sharing a title kept apart when the scrape lists each of their link UUIDs?"""
        first = FloridaDocumentFactory.create(document_name="Brief")
        second = FloridaDocumentFactory.create(document_name="Brief")
        docket_data = self._make_case(first, second)

        merge_case(docket_data)
        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertNotIn("FloridaDocument", result.creates)
        self.assertEqual(
            set(FloridaDocument.objects.values_list("link_uuid", flat=True)),
            {first.document_link_uuid, second.document_link_uuid},
        )

    def test_merge_new_link_uuid_with_new_title_creates_document(self):
        """Is a document with an unseen title and link UUID created even though the entry already has another document?"""
        first = FloridaDocumentFactory.create(document_name="Brief")
        docket_data = self._make_case(first)
        merge_case(docket_data)

        second = FloridaDocumentFactory.create(document_name="Reply")
        docket_data.entries[0].attachments = [first, second]
        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertEqual(FloridaDocument.objects.count(), 2)
        self.assertEqual(len(result.creates["FloridaDocument"]), 1)

    def test_remerge_changed_link_uuid_with_sibling_entries(self):
        """Is a document whose link UUID changed matched on its title when the case has other entries?"""
        document = FloridaDocumentFactory.create(document_name="Brief")
        docket_data = self._make_case(document)
        docket_data.entries.append(
            FloridaDocketEntryFactory.create(
                attachments=[FloridaDocumentFactory.create()]
            )
        )
        merge_case(docket_data)
        merged = FloridaDocument.objects.get(
            link_uuid=document.document_link_uuid
        )

        document.document_link_uuid = uuid4()
        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertNotIn("FloridaDocument", result.creates)
        merged.refresh_from_db()
        self.assertEqual(merged.link_uuid, document.document_link_uuid)

    def test_remerge_replaced_document_with_new_duplicate_title(self):
        """When a document's file is replaced and a new document with the same title is added, are both created rather than one taking over the stored row, regardless of attachment order?"""
        for replacement_first in (False, True):
            with self.subTest(replacement_first=replacement_first):
                original = FloridaDocumentFactory.create(
                    document_name="Motion"
                )
                docket_data = self._make_case(original)
                merge_case(docket_data)
                stored = FloridaDocument.objects.get(
                    link_uuid=original.document_link_uuid
                )

                added = FloridaDocumentFactory.create(document_name="Motion")
                replacement = original.model_copy(
                    update={"document_link_uuid": uuid4()}
                )
                attachments = [added, replacement]
                if replacement_first:
                    attachments.reverse()
                docket_data.entries[0].attachments = attachments
                result = merge_case(docket_data)

                self.assertTrue(result.success)
                self.assertFalse(
                    FloridaDocument.objects.filter(pk=stored.pk).exists()
                )
                self.assertEqual(
                    set(
                        FloridaDocument.objects.filter(
                            docket_entry=stored.docket_entry
                        ).values_list("link_uuid", flat=True)
                    ),
                    {
                        added.document_link_uuid,
                        replacement.document_link_uuid,
                    },
                )

    def test_remerge_single_title_match_with_multiple_stored_candidates(self):
        """When an entry has two stored documents sharing a title and the next scrape has only one document with that title and an unseen link UUID, is the new document created and are the stale ones removed?"""
        first = FloridaDocumentFactory.create(document_name="Motion")
        second = FloridaDocumentFactory.create(document_name="Motion")
        docket_data = self._make_case(first, second)
        merge_case(docket_data)

        replacement = FloridaDocumentFactory.create(document_name="Motion")
        docket_data.entries[0].attachments = [replacement]
        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertEqual(len(result.creates["FloridaDocument"]), 1)
        self.assertEqual(
            list(FloridaDocument.objects.values_list("link_uuid", flat=True)),
            [replacement.document_link_uuid],
        )


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

    @merger_test(expected_query_count=21)
    def test_merge_creates_inbound_transfer(self):
        """Does merging create a transfer from the scrape's origin court, mapped to its specific CourtListener court, into the scraped docket, typed by the transfer's reason?"""
        cases = (
            ("circuit appeal", {}, "flacirct", CaseTransfer.APPEAL),
            (
                "district court of appeal",
                {
                    "court_id": FloridaCourtID.FIRST_COA.value,
                    "docket_number": "1D2023-1111",
                },
                "fladistctapp1",
                CaseTransfer.APPEAL,
            ),
            (
                "workload reason",
                {"reason": ScrapeTransferReason.WORKLOAD},
                "flacirct",
                CaseTransfer.WORKLOAD,
            ),
        )
        for label, overrides, origin_court_id, transfer_type in cases:
            with table_row(self, label):
                scrape_transfer = self._circuit_transfer(**overrides)
                docket_data = self._make_case(scrape_transfer)

                result = merge_case(docket_data)

                self.assertTrue(result.success)
                self.assertIn("CaseTransfer", result.creates)
                transfer = CaseTransfer.objects.get()
                self.assertEqual(transfer.origin_court_id, origin_court_id)
                self.assertEqual(
                    transfer.origin_docket_number,
                    scrape_transfer.docket_number,
                )
                self.assertIsNone(transfer.origin_docket)
                self.assertEqual(transfer.destination_court_id, "fla")
                self.assertEqual(
                    transfer.destination_docket_number,
                    docket_data.docket_number,
                )
                self.assertEqual(
                    transfer.destination_docket_id,
                    merged_docket(result).pk,
                )
                self.assertEqual(
                    transfer.transfer_date, docket_data.date_filed
                )
                self.assertEqual(transfer.transfer_type, transfer_type)

    @merger_test(expected_query_count=10)
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

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        transfer = CaseTransfer.objects.get()
        self.assertEqual(transfer.origin_court_id, "flacirct")
        self.assertEqual(transfer.destination_court_id, "fladistctapp1")
        self.assertEqual(
            transfer.destination_docket_id, merged_docket(result).pk
        )

    @merger_test(expected_query_count=10)
    def test_merge_creates_all_transfers(self):
        """Are multiple transfers merged as separate objects?"""
        docket_data = self._make_case(
            self._circuit_transfer(),
            self._circuit_transfer(docket_number="2023-CA-000999"),
        )

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertEqual(
            set(
                CaseTransfer.objects.values_list(
                    "origin_court_id", "origin_docket_number"
                )
            ),
            {
                ("flacirct", "2024-CA-001234"),
                ("flacirct", "2023-CA-000999"),
            },
        )

    @merger_test(expected_query_count=10)
    def test_remerge_is_idempotent(self):
        """Does merging the same case twice avoid duplicating transfers?"""
        docket_data = self._make_case(self._circuit_transfer())

        first = merge_case(docket_data)
        second = merge_case(docket_data)

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertNotIn("CaseTransfer", second.creates)
        self.assertNotIn("CaseTransfer", second.updates)
        self.assertEqual(CaseTransfer.objects.count(), 1)

    @merger_test(expected_query_count=7)
    def test_merge_fills_existing_partial_transfer(self):
        """Does merging fill in the destination docket FK on an existing transfer that only knows its origin docket?"""
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

        result = merge_case(docket_data)

        self.assertTrue(result.success)
        self.assertNotIn("CaseTransfer", result.creates)
        self.assertIn("CaseTransfer", result.updates)
        self.assertIn(partial.pk, result.updates["CaseTransfer"])
        self.assertEqual(CaseTransfer.objects.count(), 1)
        partial.refresh_from_db()
        self.assertEqual(
            partial.destination_docket_id, merged_docket(result).pk
        )
        # The origin side set by the earlier merge is left alone.
        self.assertEqual(partial.origin_docket_id, origin_docket.pk)

    @merger_test(expected_query_count=20)
    def test_merge_skips_unmergeable_transfer(self):
        """Is a transfer that is outbound, has a reason with no CaseTransfer type, comes from a court with no CourtListener mapping or one missing from the DB, or has no docket number skipped without failing the merge?"""
        cases = {
            "outbound": {"direction": ScrapeTransferDirection.OUTBOUND},
            "unknown reason": {"reason": ScrapeTransferReason.UNKNOWN},
            "unmappable court": {
                "court_id": FloridaCourtID.COMPENSATION_CLAIMS.value
            },
            "court missing from DB": {"court_id": FloridaCourtID.COUNTY.value},
            "empty docket number": {"docket_number": ""},
        }
        for label, overrides in cases.items():
            with table_row(self, label):
                docket_data = self._make_case(
                    self._circuit_transfer(**overrides)
                )

                result = merge_case(docket_data)

                self.assertTrue(result.success)
                self.assertEqual(CaseTransfer.objects.count(), 0)


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

    def _ingest_with_stored_file(
        self, download_mock: mock.Mock
    ) -> tuple[FloridaCase, FloridaDocument]:
        """Ingest a case, then give its document a stored file.

        Resets `download_mock` so a re-ingest's download dispatches can be
        checked on their own.
        """
        case = self._make_case()
        fl_ingest_docket_task((case, "bucket", "key"))
        document = FloridaDocument.objects.get()
        document.filepath_local = "florida/stored-file.pdf"
        document.save()
        download_mock.reset_mock()
        return case, document

    @mock.patch("cl.corpus_importer.tasks.download_fl_document.si")
    def test_ingest_merges_docket_and_dispatches_downloads(
        self, download_mock: mock.Mock
    ) -> None:
        """Does ingesting a case merge the docket and dispatch a download for each created document?"""
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
        """Does download_attachments=False merge documents without downloading them?"""
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
    def test_reingest_with_stored_file_skips_download(
        self, download_mock: mock.Mock
    ) -> None:
        """Does re-ingesting an unchanged case skip downloading a document whose file is already stored?"""
        case, _document = self._ingest_with_stored_file(download_mock)

        result = fl_ingest_docket_task((case, "bucket", "key"))

        self.assertTrue(result.success)
        self.assertNotIn("FloridaDocument", result.creates)
        self.assertNotIn("FloridaDocument", result.updates)
        download_mock.assert_not_called()

    @mock.patch("cl.corpus_importer.tasks.download_fl_document.si")
    def test_reingest_metadata_update_with_stored_file_skips_download(
        self, download_mock: mock.Mock
    ) -> None:
        """Does a rescrape that only updates a document's metadata skip downloading a file that's already stored for the same link UUID?"""
        case, document = self._ingest_with_stored_file(download_mock)

        case.entries[0].attachments[0].document_name = "Renamed document"
        result = fl_ingest_docket_task((case, "bucket", "key"))

        self.assertTrue(result.success)
        self.assertEqual(result.updates["FloridaDocument"], {document.pk})
        download_mock.assert_not_called()

    @mock.patch("cl.corpus_importer.tasks.download_fl_document.si")
    def test_reingest_changed_link_uuid_with_stored_file_skips_download(
        self, download_mock: mock.Mock
    ) -> None:
        """Does a rescrape that changes a document's link UUID update the existing document and skip downloading its already stored file?"""
        case, document = self._ingest_with_stored_file(download_mock)

        new_uuid = uuid4()
        case.entries[0].attachments[0].document_link_uuid = new_uuid
        result = fl_ingest_docket_task((case, "bucket", "key"))

        self.assertTrue(result.success)
        self.assertNotIn("FloridaDocument", result.creates)
        self.assertEqual(result.updates["FloridaDocument"], {document.pk})
        document.refresh_from_db()
        self.assertEqual(document.link_uuid, new_uuid)
        download_mock.assert_not_called()

    @mock.patch("cl.corpus_importer.tasks.download_fl_document.si")
    def test_reingest_missing_file_downloads_again(
        self, download_mock: mock.Mock
    ) -> None:
        """Does re-ingesting an unchanged case re-dispatch the download for a document whose earlier download never stored a file?"""
        case = self._make_case()
        fl_ingest_docket_task((case, "bucket", "key"))
        document = FloridaDocument.objects.get()
        download_mock.reset_mock()

        result = fl_ingest_docket_task((case, "bucket", "key"))

        self.assertTrue(result.success)
        download_mock.assert_called_once_with(document.pk)
        download_mock.return_value.apply_async.assert_called_once()

    @mock.patch("cl.corpus_importer.tasks.download_fl_document.si")
    def test_ingest_invalid_case_fails(self, download_mock: mock.Mock) -> None:
        """Does an undeserializable payload fail the merge without raising or downloading anything?"""
        result = fl_ingest_docket_task((b"not json", "bucket", "key"))

        self.assertFalse(result.success)
        self.assertIn("Docket", result.failures)
        download_mock.assert_not_called()


class FloridaDocumentDownloadTest(TestCase):
    """Tests for the download_fl_document Celery task."""

    def setUp(self) -> None:
        """Mock the task throttle, the ACIS proof-of-work gate, the download stream, and the extraction task dispatch."""
        self.throttle_patch = mock.patch(
            "cl.lib.celery_utils.get_task_wait", return_value=0
        )
        self.throttle_patch.start()
        self.addCleanup(self.throttle_patch.stop)
        # A 204 from the challenge endpoint means the gate is off, so the
        # stored URL is fetched unchanged. The gate itself is covered in
        # cl.search.state.florida.tests.
        self.challenge_patch = mock.patch(
            "cl.search.state.florida.models.httpx.get",
            return_value=httpx.Response(
                204, request=httpx.Request("GET", "https://acis-api.test")
            ),
        )
        self.challenge_patch.start()
        self.addCleanup(self.challenge_patch.stop)
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

    @staticmethod
    @contextmanager
    def _temporary_file(data: bytes) -> Iterator[IO[bytes]]:
        """Yield an open temporary file holding `data`, rewound for reading."""
        with NamedTemporaryFile(suffix=".tmp") as tmp:
            tmp.write(data)
            tmp.flush()
            tmp.seek(0)
            yield tmp

    def _mock_downloaded_file(self, tmp: IO[bytes], sha1: str) -> None:
        """Point the mocked download stream at an open temporary file."""
        self.download_document_mock.return_value.__enter__.return_value = (
            tmp,
            sha1,
        )

    def _refuse_downloads(self) -> None:
        """Make every download attempt fail with a 403 refusal from the court."""
        self.download_document_mock.return_value.__enter__.side_effect = (
            requests.HTTPError(response=mock.Mock(status_code=403))
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

        with self._temporary_file(b"fake pdf data") as tmp:
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

    @mock.patch("cl.lib.microservice_utils.doc_page_count_service")
    @mock.patch("cl.scrapers.utils.get_extension", return_value=".pdf")
    def test_download_refusal_is_retried(
        self,
        ext_mock: mock.Mock,
        pcs_mock: mock.Mock,
    ) -> None:
        """Is a 403 from the court retried, and the file stored once the court relents? A refusal is a transient block on our requests, not a sealed document, so one must not cost us the file."""
        fl_document = FloridaDocumentModelFactory.create()
        pcs_mock.return_value = httpx.Response(200, text="1")
        refused = requests.HTTPError(response=mock.Mock(status_code=403))

        with self._temporary_file(b"fake pdf data") as tmp:
            self.download_document_mock.return_value.__enter__.side_effect = [
                refused,
                (tmp, "pdfsha1"),
            ]

            download_fl_document.apply(args=(fl_document.pk,))

        self.assertEqual(self.download_document_mock.call_count, 2)
        fl_document.refresh_from_db()
        self.assertTrue(fl_document.filepath_local)
        self.assertEqual(fl_document.sha1, "pdfsha1")
        self.extract_document_mock.assert_called_once()

    def test_download_refusal_fails_after_full_backoff(self) -> None:
        """Does a court that keeps refusing eventually fail the task with the refusal, rather than retrying forever or passing silently, after waiting every retry's whole backoff interval? A retry sent while the court is still blocking us is wasted, so the waits must not be shortened at random."""
        fl_document = FloridaDocumentModelFactory.create()
        self._refuse_downloads()

        with mock.patch.object(
            download_fl_document, "retry", wraps=download_fl_document.retry
        ) as retry_mock:
            result = download_fl_document.apply(args=(fl_document.pk,))

        self.assertTrue(result.failed())
        self.assertIsInstance(result.result, CourtRefused)
        self.assertEqual(
            self.download_document_mock.call_count,
            download_fl_document.max_retries + 1,
        )
        minute = 60
        # The final call to retry raises the refusal instead of waiting.
        waits = [
            call.kwargs["countdown"]
            for call in retry_mock.call_args_list[
                : download_fl_document.max_retries
            ]
        ]
        self.assertEqual(
            waits,
            [5 * minute, 10 * minute, 20 * minute, 40 * minute, 60 * minute],
        )
        fl_document.refresh_from_db()
        self.assertFalse(fl_document.filepath_local)
        self.extract_document_mock.assert_not_called()

    def test_download_non_pdf_file_types(self) -> None:
        """Is a downloaded non-PDF file stored with a warning only when its type is unexpected, and sent to extraction only when extractable, being marked OCR_UNNECESSARY otherwise?"""
        cases = (
            # extension, unexpected, extractable
            (".tiff", False, True),
            (".html", True, True),
            (".docx", True, False),
        )
        for extension, unexpected, extractable in cases:
            with (
                table_row(self, extension),
                mock.patch(
                    "cl.scrapers.utils.get_extension", return_value=extension
                ),
                mock.patch("cl.search.state.shared.logger") as logger_mock,
                self._temporary_file(b"fake data") as tmp,
            ):
                self.extract_document_mock.reset_mock()
                fl_document = FloridaDocumentModelFactory.create()
                self._mock_downloaded_file(tmp, f"{extension}sha1")

                result = download_fl_document(fl_document.pk)

                self.assertEqual(result, fl_document.pk)
                unexpected_warning = mock.call(
                    "Document download: Unexpected extension '%s' for %s %s from %s. Proceeding anyway.",
                    extension,
                    "FloridaDocument",
                    fl_document.pk,
                    fl_document.url,
                )
                self.assertEqual(
                    logger_mock.warning.call_args_list,
                    [unexpected_warning] if unexpected else [],
                )
                fl_document.refresh_from_db()
                self.assertTrue(fl_document.filepath_local)
                self.assertIn(extension, fl_document.filepath_local.name)
                self.assertEqual(fl_document.sha1, f"{extension}sha1")
                self.assertIsNone(fl_document.processing_error)
                self.assertEqual(
                    fl_document.ocr_status,
                    None if extractable else FloridaDocument.OCR_UNNECESSARY,
                )
                self.assertEqual(
                    self.extract_document_mock.call_count, int(extractable)
                )


class StateDocumentExtractionTest(TestCase):
    """Tests for the extract_state_documents page_count filtering."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create documents covering every page_count scenario.

        They share one docket entry since each new entry would create a
        duplicate AttorneyOrganization through the party factories.
        """
        entry = FloridaDocketEntryModelFactory.create()
        cls.small_pdf = FloridaDocumentModelFactory.create(
            docket_entry=entry, filepath_local="small.pdf", page_count=5
        )
        cls.big_pdf = FloridaDocumentModelFactory.create(
            docket_entry=entry, filepath_local="big.pdf", page_count=51
        )
        cls.zero_pdf = FloridaDocumentModelFactory.create(
            docket_entry=entry, filepath_local="zero.pdf", page_count=0
        )
        cls.negative_pdf = FloridaDocumentModelFactory.create(
            docket_entry=entry,
            filepath_local="negative.pdf",
            page_count=-2147483648,
        )
        cls.null_pdf = FloridaDocumentModelFactory.create(
            docket_entry=entry, filepath_local="null.pdf", page_count=None
        )
        cls.html_doc = FloridaDocumentModelFactory.create(
            docket_entry=entry, filepath_local="doc.html", page_count=None
        )

    def setUp(self) -> None:
        """Mock the throttle and the extraction task dispatch."""
        self.throttle_patch = mock.patch(
            "cl.lib.celery_utils.get_task_wait", return_value=0
        )
        self.throttle_patch.start()
        self.addCleanup(self.throttle_patch.stop)
        self.extract_document_patch = mock.patch(
            "cl.corpus_importer.management.commands.state_document_download"
            ".extract_formatted_text_document.si"
        )
        self.extract_document_mock = self.extract_document_patch.start()
        self.addCleanup(self.extract_document_patch.stop)

    def _scheduled_pks(self) -> set[int]:
        """Collect every pk scheduled for extraction across all calls."""
        return {
            pk
            for call in self.extract_document_mock.call_args_list
            for pk in call.kwargs["pks"]
        }

    def test_page_limit_filters_pdfs_only(self) -> None:
        """Does --page-limit keep only PDFs with a real page count within the limit while still scheduling non-PDF documents, and does omitting it schedule every document regardless of its page_count, including null, zero and negative values?"""
        cases = (
            (50, {self.small_pdf.pk, self.html_doc.pk}),
            (
                None,
                {
                    self.small_pdf.pk,
                    self.big_pdf.pk,
                    self.zero_pdf.pk,
                    self.negative_pdf.pk,
                    self.null_pdf.pk,
                    self.html_doc.pk,
                },
            ),
        )
        for page_limit, expected_pks in cases:
            with table_row(self, f"page_limit={page_limit}"):
                self.extract_document_mock.reset_mock()

                extract_state_documents(
                    FloridaDocument,
                    throttle_min_items=100,
                    extraction_queue="celery",
                    batch_size=10,
                    delay=0,
                    page_limit=page_limit,
                )

                self.assertEqual(self._scheduled_pks(), expected_pks)
