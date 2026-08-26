"""Tests for turning a New York Court of Appeals (Court-PASS) scrape run into
merged dockets.

These cover the reshaping the loader's query does -- nesting files under their
filing, folding attorney rows into parties, standing a case's date in from its
earliest filing -- and the rows it leaves out.
"""

import json
import logging
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from juriscraper.state.docket import PartyType as ScrapePartyType
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    FilingDocType,
    FilingRole,
    IssueCategory,
)

from cl.corpus_importer.state.ledger import PARTS as LEDGER_PARTS
from cl.corpus_importer.state.loader import (
    ExtractionReport,
    LoadPhase,
    WaitOutcome,
)
from cl.corpus_importer.state.new_york.loader import NYCoACourtPassLoader
from cl.lib.redis_utils import get_redis_interface
from cl.people_db.models import Party
from cl.search.factories import CourtFactory
from cl.search.models import Docket
from cl.search.state.new_york.models import (
    NYCoADocketEntry,
    NYCoADocketIssue,
    NYCoADocument,
)
from cl.search.state.new_york.vocabularies import UNASSIGNED, UNKNOWN
from cl.tests.cases import TestCase

DOCKET_NUMBER = "APL-2024-00177"
DOCKET_NUMBER_CORE = "apl202400177"


def _run_database(path: Path, rows: list[tuple[str, dict]]) -> None:
    """Write a minimal stand-in for a jkent run database.

    Only the columns the loaders read are created, since the loader's contract
    is with the `results` table rather than with the whole schema."""
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "CREATE TABLE results ("
            "  id INTEGER PRIMARY KEY,"
            "  result_type VARCHAR NOT NULL,"
            "  data_json VARCHAR NOT NULL,"
            "  is_valid BOOLEAN DEFAULT 1 NOT NULL"
            ")"
        )
        connection.executemany(
            "INSERT INTO results (result_type, data_json) VALUES (?, ?)",
            [(result_type, json.dumps(data)) for result_type, data in rows],
        )
        connection.commit()


def _docket(**overrides: Any) -> dict[str, Any]:
    """A Court-PASS docket in the shape the scraper stores it."""
    return {
        "docket_number": DOCKET_NUMBER,
        "court": "ny",
        "case_name": "Smith v. Jones",
        "case_short_name": "Smith v Jones",
        "argument_date": "2024-05-01",
        "decision_date": None,
        "issues": [],
        "official_citation": None,
        "lower_court_citation": None,
        "no_files_for_case": True,
        "docket_entries": [],
        "attorneys": [],
        "files": [],
    } | overrides


ENTRY = {
    "filing_type": "Appellant Brief",
    "party": "Smith",
    "date_due": None,
    "date_received": "2024-03-02",
    "docket_entry_id": "e:appellant-brief:smith:1",
    "entry_index": 0,
    "raw_filing_type": "Appellant Brief",
    "entry_filing_type": "Appellant Brief",
    "entry_role": "appellant",
    "entry_doctype": "brf",
    "filing_type_recognized": True,
    "inferred_from_file": False,
    "file_indexes": [0],
}

FILE = {
    "file_name": "SmithvJones-app-Smith-Brf",
    "file_index": 0,
    "available": True,
    "docket_number": DOCKET_NUMBER,
    "doc_role": "appellant",
    "doc_party": "Smith",
    "doc_type": "brf",
    "volume": None,
    "part": None,
    "docket_entry_id": "e:appellant-brief:smith:1",
    "link_status": "matched",
}


class NYCoALoaderTest(TestCase):
    """Tests for turning a Court-PASS run database into merged dockets."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.ny = CourtFactory.create(id="ny")

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "run.db"
        extraction = patch("cl.scrapers.tasks.extract_formatted_text_document")
        self.extraction = extraction.start()
        self.addCleanup(extraction.stop)
        self.key = f"state_scrape_load:test:{self.id()}"
        self.redis = get_redis_interface("CACHE")
        self.clear_run_keys()
        self.addCleanup(self.clear_run_keys)

    def clear_run_keys(self) -> None:
        """Take away the run's checkpoint and every part of its ledger."""
        self.redis.delete(
            self.key,
            *(f"{self.key}:{part}" for part in LEDGER_PARTS),
        )

    def loader(self, **kwargs: Any) -> NYCoACourtPassLoader:
        """A loader over the test run, keeping a ledger so that its report is
        filled in from what the merges actually did.

        Neither wait sleeps: celery runs eagerly here, so the merges have
        already happened, and extraction is mocked out and never will -- a
        zero `in_flight_time` says exactly that, so the waits reach the
        stalled exit rather than sitting out the timeout."""
        kwargs.setdefault("run_key", self.key)
        kwargs.setdefault("in_flight_time", 0)
        kwargs.setdefault("verify_timeout", 0)
        return NYCoACourtPassLoader(self.database, **kwargs)

    def scrape(self, rows: list[tuple[str, dict]]) -> Any:
        """The single scrape the loader reads out of a run holding `rows`."""
        _run_database(self.database, rows)
        scrapes = list(NYCoACourtPassLoader(self.database).scrapes())
        self.assertEqual(len(scrapes), 1)
        return scrapes[0]

    def test_missing_database(self) -> None:
        """Is a run database that isn't there reported as such?"""
        loader = NYCoACourtPassLoader(self.database)
        with self.assertRaises(FileNotFoundError):
            loader.load()

    def test_nests_files_under_their_filing(self) -> None:
        """The scraper stores a docket's files in one flat list. Does the
        loader put each one under the filing it belongs to?"""
        scrape = self.scrape(
            [
                (
                    "NYCourtPassDocket",
                    _docket(docket_entries=[ENTRY], files=[FILE]),
                ),
                ("NYCourtPassFile", FILE | {"local_path": "/tmp/brief.pdf"}),
            ]
        )

        self.assertEqual(len(scrape.entries), 1)
        entry = scrape.entries[0]
        self.assertEqual(entry.docket_entry_id, "e:appellant-brief:smith:1")
        self.assertEqual(entry.date_filed, date(2024, 3, 2))
        self.assertEqual(entry.entry_role, FilingRole.APPELLANT)
        self.assertEqual(entry.entry_doctype, FilingDocType.BRIEF)
        self.assertEqual(len(entry.attachments), 1)
        self.assertEqual(entry.attachments[0].doc_type, FilingDocType.BRIEF)
        self.assertEqual(
            entry.attachments[0].local_path,
            "/tmp/brief.pdf",
            "The download record's local path is joined onto the file.",
        )

    def test_case_date_filed_is_earliest_filing(self) -> None:
        """Court-PASS dates no case, only its filings. Does the earliest
        filing date stand in?"""
        later = ENTRY | {
            "docket_entry_id": "e:respondent-brief:jones:1",
            "date_received": "2024-06-01",
        }
        scrape = self.scrape(
            [("NYCourtPassDocket", _docket(docket_entries=[ENTRY, later]))]
        )

        self.assertEqual(scrape.date_filed, date(2024, 3, 2))

    def test_undated_case_has_no_date_filed(self) -> None:
        """A case whose filings were all reconstructed from the file list
        carries no date at all."""
        undated = ENTRY | {"date_received": None}
        scrape = self.scrape(
            [("NYCourtPassDocket", _docket(docket_entries=[undated]))]
        )

        self.assertIsNone(scrape.date_filed)

    def test_groups_attorneys_into_parties(self) -> None:
        """Court-PASS lists attorneys, not parties. Are the attorney rows
        folded into one party each?"""
        attorneys = [
            {
                "party_name": "Smith",
                "party_role": "Appellant",
                "firm": "Roe & Roe LLP",
                "attorney_name": "Jane Roe",
                "address": "1 Main St",
                "phone": "(518) 555-1212",
            },
            {
                "party_name": "Smith",
                "party_role": "Appellant",
                "firm": None,
                "attorney_name": "John Doe",
                "address": None,
                "phone": None,
            },
            {
                "party_name": "Concerned Citizens",
                "party_role": "Amicus Curiae",
                "firm": None,
                "attorney_name": "Ada Lovelace",
                "address": None,
                "phone": None,
            },
        ]
        scrape = self.scrape(
            [("NYCourtPassDocket", _docket(attorneys=attorneys))]
        )

        self.assertEqual(len(scrape.parties), 2)
        smith, amicus = scrape.parties
        self.assertEqual(smith.name, "Smith")
        self.assertEqual(smith.party_type, ScrapePartyType.APPELLANT)
        self.assertEqual(
            [a.name for a in smith.representatives], ["Jane Roe", "John Doe"]
        )
        self.assertEqual(
            amicus.party_role_raw,
            "Amicus Curiae",
            "The Court's own wording is kept for roles the vocabulary lacks.",
        )
        self.assertEqual(
            amicus.party_type,
            ScrapePartyType.UNASSIGNED,
            "A role the cross-state vocabulary cannot express is unassigned.",
        )

    def test_keeps_a_party_no_attorney_appeared_for(self) -> None:
        """Court-PASS lists a party through its attorneys, and prints one
        without an attorney of record all the same. Is the party kept, with
        nobody under it?"""
        scrape = self.scrape(
            [
                (
                    "NYCourtPassDocket",
                    _docket(
                        attorneys=[
                            {
                                "party_name": "Smith",
                                "party_role": "Appellant",
                                "attorney_name": None,
                            }
                        ]
                    ),
                )
            ]
        )

        self.assertEqual(len(scrape.parties), 1)
        self.assertEqual(scrape.parties[0].name, "Smith")
        self.assertEqual(scrape.parties[0].representatives, [])

    def test_reads_a_docket_whose_sections_are_null(self) -> None:
        """The scraper stores a section it read nothing in as `null`, and
        SQLite yields a row for that null rather than no rows at all. Is it
        kept out of the payload, rather than becoming an empty filing,
        party or issue?"""
        scrape = self.scrape(
            [
                (
                    "NYCourtPassDocket",
                    _docket(
                        docket_entries=None,
                        attorneys=None,
                        issues=None,
                        files=None,
                    ),
                )
            ]
        )

        self.assertEqual(scrape.entries, [])
        self.assertEqual(scrape.parties, [])
        self.assertEqual(scrape.issues, [])

    def test_one_contact_per_attorney(self) -> None:
        """CourtListener keeps one attorney per name per docket, and Court-PASS
        can print a different firm for the same attorney on each party it
        represents. Is one set of details published for all of them, so the
        merge does not rewrite the row on every scrape?"""
        attorneys = [
            {
                "party_name": "Smith",
                "party_role": "Appellant",
                "firm": "Roe & Roe LLP",
                "attorney_name": "Jane Roe",
                "address": "1 Main St",
                "phone": "(518) 555-1212",
            },
            {
                "party_name": "Jones",
                "party_role": "Respondent",
                "firm": "Pryor Cashman LLP",
                "attorney_name": "Jane Roe",
                "address": "7 Times Square",
                "phone": "(212) 555-0000",
            },
        ]
        scrape = self.scrape(
            [("NYCourtPassDocket", _docket(attorneys=attorneys))]
        )

        published = [
            representative
            for party in scrape.parties
            for representative in party.representatives
            if representative.name == "Jane Roe"
        ]
        self.assertEqual(len(published), 2)
        self.assertEqual(
            {(r.firm, r.address, r.phone) for r in published},
            {("Roe & Roe LLP", "1 Main St", "(518) 555-1212")},
            "The first listing on the page stands for every party.",
        )

    def test_refuses_a_docket_whose_file_list_went_unparsed(self) -> None:
        """A filing detail page that carried neither the Court's "no files"
        line nor a file table the scraper could read attests to nothing about
        the case's filings, and merging its empty file list would prune every
        document the docket has. Is it refused, and does the rest load?"""
        _run_database(
            self.database,
            [
                ("NYCourtPassDocket", _docket(no_files_for_case=False)),
                (
                    "NYCourtPassDocket",
                    _docket(docket_number="APL-2024-00178"),
                ),
            ],
        )

        report = self.loader().load()

        self.assertEqual(
            (report.seen, report.merged, report.refused, report.invalid),
            (2, 1, 1, 0),
            "The refused docket is counted as refused, not passed over.",
        )
        self.assertEqual(Docket.objects.get().docket_number, "APL-2024-00178")

    def test_an_unparsed_file_list_names_the_docket_it_lost(self) -> None:
        """Drift in the file table could cost every docket in a run, and the
        count alone does not say which. Does the log name the docket?"""
        _run_database(
            self.database,
            [("NYCourtPassDocket", _docket(no_files_for_case=False))],
        )
        # The test runner disables logging outright for speed, and what an
        # operator can find in the log is the point of this test.
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable)

        with self.assertLogs(
            "cl.corpus_importer.state.loader", "ERROR"
        ) as logs:
            self.loader().load()

        self.assertIn(DOCKET_NUMBER, logs.output[0])
        self.assertFalse(Docket.objects.exists())

    def test_loads_a_docket_stating_an_uncovered_subcategory(self) -> None:
        """A subcategory the vocabulary does not cover must not cost the
        docket. Does the case load, with the issue recorded as unassigned and
        the Court's own wording kept?"""
        _run_database(
            self.database,
            [
                (
                    "NYCourtPassDocket",
                    _docket(
                        issues=[
                            {
                                "category_raw": (
                                    "Corporations--Not-For-Profit Corporation"
                                ),
                                "category": "Corporations",
                                "subcategory": "Not-For-Profit Corporation",
                                "detail": "Whether the by-laws bind.",
                            }
                        ]
                    ),
                )
            ],
        )

        report = self.loader().load()

        self.assertEqual(
            (report.seen, report.merged, report.invalid), (1, 1, 0)
        )
        issue = NYCoADocketIssue.objects.get()
        self.assertEqual(issue.subcategory, UNASSIGNED)
        self.assertEqual(
            issue.category,
            IssueCategory.CORPORATIONS.code,
            "The half the vocabulary does cover is still classified.",
        )
        self.assertEqual(
            issue.category_raw, "Corporations--Not-For-Profit Corporation"
        )

    def test_loads_a_filing_the_filings_table_never_listed(self) -> None:
        """A filing the scraper reconstructed from a document states no filing
        type at all, which is not the same as stating one the vocabulary does
        not cover. The scraper reports both as `None`, so what separates them by
        the time the merge stores a code is the raw string the loader hands over
        beside it: blank for the filing no table row named."""
        for label, raw, expected in (
            ("no table row named it", None, UNKNOWN),
            ("named but not covered", "Appellant Sur-Reply Brief", UNASSIGNED),
        ):
            with self.subTest(label):
                # Each reading gets a run of its own, so the second does not
                # merge into the docket the first wrote.
                Docket.objects.all().delete()
                self.database.unlink(missing_ok=True)
                _run_database(
                    self.database,
                    [
                        (
                            "NYCourtPassDocket",
                            _docket(
                                docket_entries=[
                                    ENTRY
                                    | {
                                        "raw_filing_type": raw,
                                        "entry_filing_type": None,
                                    }
                                ]
                            ),
                        )
                    ],
                )

                report = self.loader().load()

                self.assertEqual((report.seen, report.merged), (1, 1))
                entry = NYCoADocketEntry.objects.get()
                self.assertEqual(entry.filing_type, expected)
                self.assertEqual(entry.filing_type_raw, raw or "")

    def test_merges_a_docket_the_court_states_has_no_files(self) -> None:
        """Court-PASS says outright when a case has no files at all. Is that
        docket merged, rather than taken for one whose file list went
        unread?"""
        _run_database(
            self.database,
            [("NYCourtPassDocket", _docket(no_files_for_case=True))],
        )

        report = self.loader().load()

        self.assertEqual(
            (report.seen, report.merged, report.failed), (1, 1, 0)
        )

    def test_collapses_a_file_listed_twice(self) -> None:
        """Court-PASS sometimes lists one document twice on a filing, once
        servable and once not. Is the servable copy the one kept?"""
        sealed = FILE | {"file_index": 1, "available": False}
        scrape = self.scrape(
            [
                (
                    "NYCourtPassDocket",
                    _docket(docket_entries=[ENTRY], files=[sealed, FILE]),
                )
            ]
        )

        attachments = scrape.entries[0].attachments
        self.assertEqual(len(attachments), 1)
        self.assertTrue(attachments[0].available)

    def test_one_row_per_docket(self) -> None:
        """A docket listed at two positions in the search grid is scraped
        once per position. Is it merged once?"""
        _run_database(
            self.database,
            [
                ("NYCourtPassDocket", _docket(search_row=8)),
                ("NYCourtPassDocket", _docket(search_row=9)),
            ],
        )

        report = self.loader().load()

        self.assertEqual(report.seen, 1)
        self.assertEqual(report.merged, 1)
        self.assertEqual(Docket.objects.count(), 1)

    def test_load_merges(self) -> None:
        """Does a load actually write the docket and everything under it?"""
        _run_database(
            self.database,
            [
                (
                    "NYCourtPassDocket",
                    _docket(
                        docket_entries=[ENTRY],
                        files=[FILE],
                        issues=[
                            {
                                "category_raw": "Crimes--Appeal",
                                "category": "Crimes",
                                "subcategory": "Appeal",
                                "detail": "Whether the appeal lies.",
                            }
                        ],
                        attorneys=[
                            {
                                "party_name": "Smith",
                                "party_role": "Appellant",
                                "firm": "Roe & Roe LLP",
                                "attorney_name": "Jane Roe",
                                "address": "1 Main St",
                                "phone": "(518) 555-1212",
                            }
                        ],
                    ),
                )
            ],
        )

        report = self.loader().load()

        self.assertEqual((report.seen, report.merged), (1, 1))
        self.assertEqual((report.invalid, report.failed), (0, 0))
        docket = Docket.objects.get()
        self.assertEqual(docket.docket_number_core, DOCKET_NUMBER_CORE)
        self.assertEqual(docket.nycoa_docket_entries.count(), 1)
        self.assertEqual(NYCoADocument.objects.count(), 1)
        self.assertEqual(NYCoADocketIssue.objects.count(), 1)
        self.assertEqual(Party.objects.count(), 1)

    def _run_holding_one_document(self) -> None:
        """Write a run of one docket whose file the scraper downloaded."""
        _run_database(
            self.database,
            [
                (
                    "NYCourtPassDocket",
                    _docket(docket_entries=[ENTRY], files=[FILE]),
                ),
                ("NYCourtPassFile", FILE | {"local_path": "/tmp/brief.pdf"}),
            ],
        )

    def test_dispatches_extraction_for_the_documents_it_writes(self) -> None:
        """A merge only records where a document's file is. Is the document
        handed off for text extraction as the load goes?"""
        self._run_holding_one_document()

        report = self.loader().load()

        self.assertEqual(report.merged, 1)
        document = NYCoADocument.objects.get()
        self.extraction.si.assert_called_once_with(
            pks=document.pk,
            check_if_needed=False,
            model_name="search.NYCoADocument",
            strip_html_tags=False,
        )
        self.extraction.si.return_value.set.assert_called_once_with(
            queue="celery"
        )

    def test_extraction_goes_to_the_queue_it_is_given(self) -> None:
        """Is a load's extraction queue passed through to the task?"""
        self._run_holding_one_document()

        self.loader(extraction_queue="batch1").load()

        self.extraction.si.return_value.set.assert_called_once_with(
            queue="batch1"
        )

    def extraction_report(self, **kwargs: Any) -> ExtractionReport:
        """The extraction half of a load's report over a run of one docket."""
        report = self.loader(**kwargs).load()
        self.assertEqual(report.merged, 1)
        self.assertIsNotNone(report.extraction)
        assert report.extraction is not None  # For the type checker.
        return report.extraction

    def test_extraction_that_never_ran_is_reported(self) -> None:
        """A merge reporting success says extraction was dispatched, not that
        it ran, and a failed call to the extraction service leaves no other
        trace. Does the load notice the document sitting there unextracted?"""
        self._run_holding_one_document()

        extraction = self.extraction_report()

        document = NYCoADocument.objects.get()
        self.assertEqual(extraction.dispatched, 1)
        self.assertEqual(
            (extraction.outstanding, extraction.failed),
            (1, 0),
            "Extraction is mocked out here, so it never ran.",
        )
        self.assertEqual(extraction.sample, [document.pk])
        self.assertFalse(extraction.complete)
        self.assertTrue(
            extraction.abandoned, "The count never moved, so it is a finding."
        )

    def test_an_extracted_document_is_not_reported(self) -> None:
        """The check has to clear once extraction has run, or every load would
        end by crying wolf. Does a document that came back count as done?"""
        self._run_holding_one_document()

        with patch.object(NYCoADocument, "extract", autospec=True) as extract:
            # Stand in for the extraction task having run and written back.
            def extracted(document: NYCoADocument, queue: str) -> bool:
                NYCoADocument.objects.filter(pk=document.pk).update(
                    ocr_status=NYCoADocument.OCR_COMPLETE
                )
                return True

            extract.side_effect = extracted
            extraction = self.extraction_report()

        self.assertEqual(extraction.dispatched, 1)
        self.assertEqual(extraction.outstanding, 0)
        self.assertTrue(extraction.complete)

    def test_a_document_extraction_could_not_read_is_counted_apart(
        self,
    ) -> None:
        """A document extraction ran on and failed is the extraction
        pipeline's problem, not the load's. Is it kept out of the count of
        documents extraction never reached?"""
        self._run_holding_one_document()

        with patch.object(NYCoADocument, "extract", autospec=True) as extract:

            def failed(document: NYCoADocument, queue: str) -> bool:
                NYCoADocument.objects.filter(pk=document.pk).update(
                    ocr_status=NYCoADocument.OCR_FAILED
                )
                return True

            extract.side_effect = failed
            extraction = self.extraction_report()

        self.assertEqual((extraction.outstanding, extraction.failed), (0, 1))
        self.assertTrue(
            extraction.complete, "Nothing here is still waiting to be read."
        )

    def test_unextracted_documents_get_their_own_sentry_issue(self) -> None:
        """Extraction that never ran is a different problem from a merge that
        failed. Is it filed on its own, under the loader rather than the run?"""
        self._run_holding_one_document()
        # The test runner disables logging outright for speed, and the error
        # is what carries this to Sentry.
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable)

        with self.assertLogs(
            "cl.corpus_importer.state.loader", "ERROR"
        ) as logs:
            self.loader().load()

        self.assertEqual(
            logs.records[0].fingerprint,  # type: ignore[attr-defined]
            ["nycoa", LoadPhase.EXTRACTION],
        )
        self.assertIn("state_document_download", logs.output[0])

    def test_each_phase_waits_on_its_own_clock(self) -> None:
        """Extraction cannot begin until the merges that write the documents
        have landed, so one budget shared between the two waits would have a
        run that spent it all on slow merges report every document as
        unextracted. Does each phase get its own wait?"""
        self._run_holding_one_document()
        loader = self.loader()

        with patch.object(
            loader, "_await_drain", wraps=loader._await_drain
        ) as drain:
            loader.load()

        self.assertEqual(
            [call.kwargs["work"] for call in drain.call_args_list],
            ["merges", "extractions"],
            "One wait for each, each with its own budget.",
        )

    def test_extraction_still_running_is_not_called_abandoned(self) -> None:
        """A run that gives up while extraction is still coming down has found
        nothing wrong. Is that told apart from extraction that stopped?"""
        self._run_holding_one_document()

        extraction = self.extraction_report(
            in_flight_time=600, verify_timeout=0
        )

        self.assertEqual(extraction.outstanding, 1)
        self.assertEqual(extraction.wait, WaitOutcome.TIMED_OUT)
        self.assertFalse(
            extraction.abandoned,
            "Nothing says these will not be extracted; the load just stopped "
            "watching.",
        )

    def test_a_load_dispatching_no_extraction_checks_none(self) -> None:
        """Is the extraction check held back for a load that left the work to
        the sweep, rather than reporting every document as outstanding?"""
        self._run_holding_one_document()

        report = self.loader(extract=False).load()

        self.assertEqual(report.merged, 1)
        self.assertIsNone(report.extraction)

    def test_skipping_extraction_still_merges(self) -> None:
        """`extract=False` leaves the work to the sweep. Is the document
        written all the same, and nothing dispatched?"""
        self._run_holding_one_document()

        report = self.loader(extract=False).load()

        self.assertEqual(report.merged, 1)
        self.assertTrue(NYCoADocument.objects.exists())
        self.extraction.si.assert_not_called()

    def test_dispatches_nothing_for_a_docket_with_no_documents(self) -> None:
        """Is a merge that wrote no documents left alone?"""
        _run_database(self.database, [("NYCourtPassDocket", _docket())])

        report = self.loader().load()

        self.assertEqual(report.merged, 1)
        self.extraction.si.assert_not_called()

    def test_limit(self) -> None:
        """Does `limit` stop the load early?"""
        _run_database(
            self.database,
            [
                ("NYCourtPassDocket", _docket(docket_number="APL-2024-00001")),
                ("NYCourtPassDocket", _docket(docket_number="APL-2024-00002")),
            ],
        )

        report = self.loader(limit=1).load()

        self.assertEqual(report.seen, 1)
        self.assertEqual(Docket.objects.count(), 1)

    def test_skips_a_docket_with_no_number(self) -> None:
        """A docket with no number cannot be matched against anything we
        already hold. Is it skipped rather than merged into nothing?"""
        _run_database(
            self.database,
            [
                ("NYCourtPassDocket", _docket(docket_number=None)),
                ("NYCourtPassDocket", _docket()),
            ],
        )

        report = self.loader().load()

        self.assertEqual(
            report.seen, 1, "The unnumbered docket is not selected."
        )
        self.assertEqual(report.merged, 1)

    def test_counts_a_payload_that_does_not_fit_the_model(self) -> None:
        """Scraper drift should be reported, not raised."""
        _run_database(
            self.database,
            [("NYCourtPassDocket", _docket(argument_date="not a date"))],
        )

        report = self.loader().load()

        self.assertEqual(
            (report.seen, report.invalid, report.merged), (1, 1, 0)
        )
        self.assertFalse(Docket.objects.exists())
