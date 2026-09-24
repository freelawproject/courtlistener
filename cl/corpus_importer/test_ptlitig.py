import csv
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command

from cl.corpus_importer.ptlitig import (
    make_party_list,
    merge_ptlitig_docket,
)
from cl.people_db.models import Party
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import (
    Court,
    Docket,
    DocketEntry,
    DocketIdentifier,
    RECAPDocument,
)
from cl.tests.cases import SimpleTestCase, TestCase


def make_case(**overrides) -> dict[str, str]:
    """Build a PTLITIG ``cases`` row for tests."""
    case = {
        "case_row_id": "1",
        "case_number": "5:05-cv-00123",
        "district_id": "cand",
        "pacer_id": "123456",
        "case_name": "Acme Corp v. Globex Corp",
        "assigned_to": "",
        "referred_to": "",
        "case_cause": "35:271 Patent Infringement",
        "jurisdictional_basis": "Federal Question",
        "date_filed": "2005-06-16",
        "date_closed": "2006-09-29",
        "date_last_filed": "2006-09-29",
        "jury_demand": "Plaintiff",
    }
    case.update(overrides)
    return case


class MakePartyListTest(SimpleTestCase):
    def test_links_attorneys_to_parties_by_party_row_count(self) -> None:
        """Attorneys are attached to their party via party_row_count, and the
        PACER contact blob / roles are passed through for normalization."""
        names = [
            {
                "party_row_count": "1",
                "party_type": "Plaintiff",
                "name": "Acme",
            },
            {
                "party_row_count": "2",
                "party_type": "Defendant",
                "name": "Globex",
            },
        ]
        attorneys = [
            {
                "party_row_count": "1",
                "attorney_name": "Jane Roe",
                "attorney_contactinfo": "Roe LLP; 1 Main St; Email: jane@roe.com",
                "position": "LEAD ATTORNEY; ATTORNEY TO BE NOTICED",
            }
        ]
        parties = make_party_list(names, attorneys)
        self.assertEqual(len(parties), 2)
        plaintiff, defendant = parties
        self.assertEqual(plaintiff["name"], "Acme")
        self.assertEqual(plaintiff["type"], "Plaintiff")
        self.assertEqual(len(plaintiff["attorneys"]), 1)
        atty = plaintiff["attorneys"][0]
        self.assertEqual(atty["name"], "Jane Roe")
        self.assertEqual(
            atty["contact"], "Roe LLP\n1 Main St\nEmail: jane@roe.com"
        )
        self.assertEqual(
            atty["roles"], ["LEAD ATTORNEY", "ATTORNEY TO BE NOTICED"]
        )
        self.assertEqual(defendant["attorneys"], [])


class AddUsptoPtlitigSourceTest(TestCase):
    def test_adds_bit_to_existing_source(self) -> None:
        d = DocketFactory(source=Docket.RECAP)
        d.add_uspto_ptlitig_source()
        self.assertEqual(d.source, Docket.RECAP_AND_USPTO_PTLITIG)

    def test_is_idempotent(self) -> None:
        d = DocketFactory(source=Docket.USPTO_PTLITIG)
        d.add_uspto_ptlitig_source()
        self.assertEqual(d.source, Docket.USPTO_PTLITIG)


class MergePtlitigDocketTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory(
            id="cand", jurisdiction=Court.FEDERAL_DISTRICT
        )

    def test_creates_new_docket_with_source_and_patents(self) -> None:
        patents = [
            {"patent": "7654321", "patent_doc_type": "Patent"},
            {"patent": "RE38123", "patent_doc_type": "Patent"},
            {"patent": "D456789", "patent_doc_type": "Patent"},
        ]
        d = merge_ptlitig_docket(make_case(), "830", patents, [])

        self.assertEqual(d.court_id, "cand")
        self.assertEqual(d.source, Docket.USPTO_PTLITIG)
        self.assertEqual(d.case_name, "Acme Corp v. Globex Corp")
        self.assertEqual(d.nature_of_suit, "830")
        self.assertEqual(d.date_filed, date(2005, 6, 16))
        self.assertEqual(
            sorted(d.identifiers.values_list("value", flat=True)),
            ["7654321", "D456789", "RE38123"],
        )
        self.assertTrue(
            all(i.type == DocketIdentifier.PATENT for i in d.identifiers.all())
        )

    def test_maps_doc_types_and_skips_blank_and_unknown(self) -> None:
        patents = [
            {"patent": "7654321", "patent_doc_type": "Patent"},
            {"patent": "12/910764", "patent_doc_type": "Application"},
            {
                "patent": "2007/0035812",
                "patent_doc_type": "Published Application",
            },
            {"patent": "EP1540403", "patent_doc_type": "Foreign Patent"},
            {"patent": "NA", "patent_doc_type": ""},
            {"patent": "", "patent_doc_type": "Patent"},
        ]
        d = merge_ptlitig_docket(make_case(), "830", patents, [])
        identifiers = {i.value: i.type for i in d.identifiers.all()}
        self.assertEqual(
            identifiers,
            {
                "7654321": DocketIdentifier.PATENT,
                "12/910764": DocketIdentifier.APPLICATION,
                "2007/0035812": DocketIdentifier.PUBLISHED_APPLICATION,
                "EP1540403": DocketIdentifier.FOREIGN_PATENT,
            },
        )

    def test_adds_source_bit_to_existing_docket(self) -> None:
        existing = DocketFactory(
            court=self.court,
            source=Docket.RECAP,
            pacer_case_id="123456",
            docket_number="5:05-cv-00123",
        )
        d = merge_ptlitig_docket(make_case(), "830", [], [])
        self.assertEqual(d.pk, existing.pk)
        self.assertEqual(d.source, Docket.RECAP_AND_USPTO_PTLITIG)

    def test_adds_parties_to_empty_docket(self) -> None:
        names = [
            {
                "party_row_count": "1",
                "party_type": "Plaintiff",
                "name": "Acme",
            },
        ]
        party_list = make_party_list(names, [])
        d = merge_ptlitig_docket(make_case(), "830", [], party_list)
        self.assertEqual(
            list(d.parties.values_list("name", flat=True)), ["Acme"]
        )

    def test_adds_numbered_and_unnumbered_entries(self) -> None:
        documents = [
            {
                "doc_number": "1",
                "short_description": "Complaint",
                "long_description": "Complaint filed by Acme Corp",
                "doc_date_filed": "2005-06-16",
            },
            {
                "doc_number": "2",
                "short_description": "Answer",
                "long_description": "Answer to complaint",
                "doc_date_filed": "",  # undated, but numbered: kept
            },
            {
                "doc_number": "",
                "short_description": "Minute Entry",
                "long_description": "Minute entry for proceedings",
                "doc_date_filed": "2005-07-01",  # unnumbered: also kept
            },
        ]
        d = merge_ptlitig_docket(make_case(), "830", [], [], documents)
        self.assertEqual(
            sorted(
                d.docket_entries.values_list("entry_number", flat=True),
                key=lambda n: (n is None, n),
            ),
            [1, 2, None],
        )
        # The unnumbered entry is kept, with its description.
        unnumbered = d.docket_entries.get(entry_number__isnull=True)
        self.assertEqual(unnumbered.date_filed, date(2005, 7, 1))
        self.assertEqual(
            unnumbered.description, "Minute entry for proceedings"
        )
        # Each created entry gets a single stub document.
        self.assertEqual(
            d.docket_entries.get(entry_number=1).recap_documents.count(), 1
        )

    def test_gap_fills_numbered_and_skips_unnumbered_on_existing_docket(
        self,
    ) -> None:
        """On a docket that already has entries, a missing numbered entry is
        added (existing ones untouched) but unnumbered entries are skipped."""
        existing = DocketFactory(
            court=self.court,
            source=Docket.RECAP,
            pacer_case_id="123456",
            docket_number="5:05-cv-00123",
        )
        original = DocketEntry.objects.create(
            docket=existing, entry_number=1, description="RECAP original"
        )
        RECAPDocument.objects.create(
            docket_entry=original,
            document_type=RECAPDocument.PACER_DOCUMENT,
            document_number="1",
            pacer_doc_id="999",
        )
        documents = [
            {
                "doc_number": "1",
                "short_description": "Complaint",
                "long_description": "PTLITIG version",
                "doc_date_filed": "2005-06-16",
            },
            {
                "doc_number": "2",
                "short_description": "Answer",
                "long_description": "Answer to complaint",
                "doc_date_filed": "2005-07-01",
            },
            {
                "doc_number": "",
                "short_description": "Minute Entry",
                "long_description": "Minute entry for proceedings",
                "doc_date_filed": "2005-07-02",  # unnumbered: skipped here
            },
        ]
        merge_ptlitig_docket(make_case(), "830", [], [], documents)

        # Entry 1 and its document are unchanged; entry 2 was added; the
        # unnumbered entry was not added because the docket already had entries.
        original.refresh_from_db()
        self.assertEqual(original.description, "RECAP original")
        self.assertEqual(original.recap_documents.count(), 1)
        self.assertEqual(
            sorted(
                existing.docket_entries.values_list("entry_number", flat=True)
            ),
            [1, 2],
        )
        self.assertFalse(
            existing.docket_entries.filter(entry_number__isnull=True).exists()
        )

    def test_rerun_is_idempotent(self) -> None:
        patents = [{"patent": "7654321", "patent_doc_type": "Patent"}]
        documents = [
            {
                "doc_number": "1",
                "short_description": "Complaint",
                "long_description": "Complaint filed",
                "doc_date_filed": "2005-06-16",
            },
            {
                "doc_number": "",
                "short_description": "Minute Entry",
                "long_description": "Minute entry for proceedings",
                "doc_date_filed": "2005-07-01",
            },
        ]
        names = [
            {
                "party_row_count": "1",
                "party_type": "Plaintiff",
                "name": "Acme",
            },
        ]
        for _ in range(2):
            merge_ptlitig_docket(
                make_case(),
                "830",
                patents,
                make_party_list(names, []),
                documents,
            )
        self.assertEqual(Docket.objects.count(), 1)
        self.assertEqual(DocketIdentifier.objects.count(), 1)
        # One numbered + one unnumbered entry; neither duplicated on re-run.
        self.assertEqual(DocketEntry.objects.count(), 2)
        self.assertEqual(Party.objects.count(), 1)


class ImportUsptoPtlitigCommandTest(TestCase):
    """End-to-end test of the management command's CSV reading and two passes."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory(
            id="cand", jurisdiction=Court.FEDERAL_DISTRICT
        )

    @staticmethod
    def _write(
        directory: Path,
        name: str,
        fieldnames: list[str],
        row: dict[str, str],
    ) -> None:
        with (directory / name).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(row)

    def test_imports_a_case_end_to_end(self) -> None:
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self._write(
                directory,
                "cases.csv",
                [
                    "case_row_id",
                    "case_number",
                    "case_number_raw",
                    "district_id",
                    "court_name",
                    "pacer_id",
                    "case_name",
                    "assigned_to",
                    "referred_to",
                    "case_cause",
                    "jurisdictional_basis",
                    "date_filed",
                    "date_closed",
                    "date_last_filed",
                    "jury_demand",
                    "demand",
                    "lead_case",
                    "related_case",
                    "settlement",
                    "case_type_1",
                    "case_type_2",
                    "case_type_3",
                    "case_type_note",
                ],
                {
                    "case_row_id": "1",
                    "case_number": "5:05-cv-00123",
                    "district_id": "cand",
                    "pacer_id": "123456",
                    "case_name": "Acme Corp v. Globex Corp",
                    "date_filed": "2005-06-16",
                },
            )
            self._write(
                directory,
                "pacer_cases.csv",
                [
                    "pacer_id",
                    "case_number",
                    "district_id",
                    "court_name",
                    "case_name",
                    "date_filed",
                    "date_closed",
                    "nos",
                ],
                {
                    "pacer_id": "123456",
                    "case_number": "5:05-cv-00123",
                    "district_id": "cand",
                    "nos": "830",
                },
            )
            self._write(
                directory,
                "patents.csv",
                [
                    "case_row_id",
                    "case_number",
                    "district_id",
                    "nos",
                    "date_filed",
                    "case_name",
                    "case_type_1",
                    "case_type_2",
                    "case_type_3",
                    "case_type_note",
                    "patent",
                    "patent_doc_type",
                ],
                {
                    "case_row_id": "1",
                    "patent": "7654321",
                    "patent_doc_type": "Patent",
                },
            )
            self._write(
                directory,
                "names.csv",
                [
                    "case_row_id",
                    "case_number",
                    "case_number_raw",
                    "district_id",
                    "party_row_count",
                    "party_type",
                    "name",
                    "name_long",
                ],
                {
                    "case_row_id": "1",
                    "party_row_count": "1",
                    "party_type": "Plaintiff",
                    "name": "Acme Corp",
                },
            )
            self._write(
                directory,
                "attorneys.csv",
                [
                    "case_row_id",
                    "case_number",
                    "case_number_raw",
                    "district_id",
                    "party_row_count",
                    "party_type",
                    "attorney_row_count",
                    "attorney_name",
                    "attorney_contactinfo",
                    "position",
                ],
                {
                    "case_row_id": "1",
                    "party_row_count": "1",
                    "party_type": "Plaintiff",
                    "attorney_name": "Jane Roe",
                    "attorney_contactinfo": "Roe LLP; 1 Main St",
                    "position": "LEAD ATTORNEY",
                },
            )
            self._write(
                directory,
                "documents.csv",
                [
                    "case_row_id",
                    "case_number",
                    "case_number_raw",
                    "district_id",
                    "doc_count",
                    "doc_number",
                    "short_description",
                    "long_description",
                    "attachment",
                    "doc_date_filed",
                    "doc_date_uploaded",
                    "document_url",
                ],
                {
                    "case_row_id": "1",
                    "doc_number": "1",
                    "short_description": "Complaint",
                    "long_description": "Complaint filed by Acme Corp",
                    "doc_date_filed": "2005-06-16",
                },
            )
            call_command("import_uspto_ptlitig", input_dir=tmp)

        docket = Docket.objects.get(docket_number="5:05-cv-00123")
        self.assertEqual(docket.court_id, "cand")
        self.assertEqual(docket.source, Docket.USPTO_PTLITIG)
        self.assertEqual(docket.nature_of_suit, "830")
        self.assertEqual(
            list(docket.identifiers.values_list("value", flat=True)),
            ["7654321"],
        )
        self.assertEqual(docket.docket_entries.count(), 1)
        self.assertEqual(
            list(docket.parties.values_list("name", flat=True)), ["Acme Corp"]
        )
