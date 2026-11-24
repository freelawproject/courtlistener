"""Tests for turning a New York Court of Appeals (Court-PASS) scrape run into merged dockets.

These cover the reshaping the loader's query does -- nesting files under their
filing, folding attorney rows into parties, standing a case's date in from its
earliest filing -- and the rows it leaves out.
"""

import hashlib
import json
import logging
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path, PurePosixPath
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
from cl.corpus_importer.state.new_york.storage import PRIVATE_PREFIX
from cl.corpus_importer.state.storage import PublishOutcome
from cl.corpus_importer.state.utils import FileTally
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

#: Where the scraper leaves a downloaded file. A merge publishes only what
#: sits under the private prefix, so a run fixture whose path is anything else
#: writes documents with no file at all and nothing to extract.
PRIVATE_PATH = f"{PRIVATE_PREFIX}nycourts_gov/{DOCKET_NUMBER}_brief_0.pdf"


def archived(local_path: str) -> tuple[str, str, int, str]:
    """The archive row a jkent run holds for a file it downloaded.

    Args:
        local_path: Where the scraper stored the file.

    Returns:
        The path, its hash, its size, and the kind of file it is.
    """
    digest = hashlib.sha256(local_path.encode()).hexdigest()
    return (
        local_path,
        digest,
        len(local_path) * 1000,
        PurePosixPath(local_path).suffix.lstrip("."),
    )


def _run_database(
    path: Path,
    rows: list[tuple[str, dict]],
    archive: list[tuple[str, str, int, str]] | None = None,
) -> None:
    """Write a minimal stand-in for a jkent run database.

    Only the columns the loaders read are created, since the loader's contract
    is with the `results` and `archived_files` tables rather than with the
    whole schema.

    Args:
        path: Where to write the database.
        rows: The scrape results, as `(result_type, payload)` pairs.
        archive: The archive rows, as `archived` returns them. Defaults to
            one per downloaded file, which is the invariant a real run holds to:
            the scraper hashes and measures every file it stores. Pass this to
            write a run that breaks it, or one whose file has been rescraped and
            now hashes differently.
    """
    if archive is None:
        archive = [
            archived(local_path)
            for result_type, data in rows
            if result_type == "NYCourtPassFile"
            and (local_path := data.get("local_path"))
        ]
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "CREATE TABLE results ("
            "  id INTEGER PRIMARY KEY,"
            "  result_type VARCHAR NOT NULL,"
            "  data_json VARCHAR NOT NULL,"
            "  is_valid BOOLEAN DEFAULT 1 NOT NULL"
            ")"
        )
        connection.execute(
            "CREATE TABLE archived_files ("
            "  id INTEGER PRIMARY KEY,"
            "  file_path VARCHAR NOT NULL,"
            "  expected_type VARCHAR,"
            "  file_size INTEGER,"
            "  content_hash VARCHAR"
            ")"
        )
        connection.executemany(
            "INSERT INTO results (result_type, data_json) VALUES (?, ?)",
            [(result_type, json.dumps(data)) for result_type, data in rows],
        )
        connection.executemany(
            "INSERT INTO archived_files "
            "(file_path, content_hash, file_size, expected_type) "
            "VALUES (?, ?, ?, ?)",
            archive,
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


def _one_document(local_path: str = PRIVATE_PATH) -> list[tuple[str, dict]]:
    """The results of a run holding one docket whose one file the scraper downloaded.

    Args:
        local_path: Where the scraper stored the file.

    Returns:
        The rows, as `_run_database` takes them.
    """
    return [
        ("NYCourtPassDocket", _docket(docket_entries=[ENTRY], files=[FILE])),
        ("NYCourtPassFile", FILE | {"local_path": local_path}),
    ]


class NYCoALoaderTest(TestCase):
    """Tests for turning a Court-PASS run database into merged dockets.

    Stands in for S3 as well as for the extraction queue: each merge is
    followed by moving the files it wrote documents for out of the private
    bucket, so a load run
    against a real storage backend would reach for the network once per file.
    `publish_outcome` makes the copy report whichever way of failing a test is
    after.
    """

    publish_outcome: PublishOutcome

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
        self.publish_outcome = PublishOutcome.PUBLISHED
        self.stub_storage()
        self.key = f"state_scrape_load:test:{self.id()}"
        self.redis = get_redis_interface("CACHE")
        self.clear_run_keys()
        self.addCleanup(self.clear_run_keys)

    def stub_storage(self) -> None:
        """Keep the file moves each merge is followed by off the network."""
        for target, double in (
            (
                "cl.corpus_importer.state.loader.copy_file",
                lambda *_args, **_kw: self.publish_outcome,
            ),
            (
                "cl.corpus_importer.state.loader.delete_file",
                lambda *_args: None,
            ),
            (
                "cl.corpus_importer.state.new_york.mergers.delete_file",
                lambda *_args: None,
            ),
        ):
            patcher = patch(target, double)
            patcher.start()
            self.addCleanup(patcher.stop)

    def clear_run_keys(self) -> None:
        """Take away the run's checkpoint and every part of its ledger."""
        self.redis.delete(
            self.key,
            *(f"{self.key}:{part}" for part in LEDGER_PARTS),
        )

    def start_over(self) -> None:
        """Take away everything a load left behind, so that a test running several loads gives each a run of its own rather than merging into the docket the last one wrote."""
        Docket.objects.all().delete()
        self.clear_run_keys()
        self.extraction.reset_mock()
        self.database.unlink(missing_ok=True)

    def loader(self, **kwargs: Any) -> NYCoACourtPassLoader:
        """A loader over the test run, keeping a ledger so that its report is filled in from what the merges actually did.

        Neither wait sleeps: celery runs eagerly here, so the merges have
        already happened, and extraction is mocked out and never will -- a
        zero `in_flight_time` says exactly that, so the waits reach the
        stalled exit rather than sitting out the timeout.
        """
        kwargs.setdefault("run_key", self.key)
        kwargs.setdefault("in_flight_time", 0)
        kwargs.setdefault("verify_timeout", 0)
        return NYCoACourtPassLoader(self.database, **kwargs)

    def scrape(
        self,
        rows: list[tuple[str, dict]],
        archive: list[tuple[str, str, int, str]] | None = None,
    ) -> Any:
        """The single scrape the loader reads out of a run holding `rows`, asserting that the run holds exactly one.

        Args:
            rows: The scrape results, as `_run_database` takes them.
            archive: The archive rows, as `_run_database` takes them. Pass
                this for a run that breaks the invariant the derived archive
                holds to.

        Returns:
            The scrape.
        """
        _run_database(self.database, rows, archive=archive)
        scrapes = list(NYCoACourtPassLoader(self.database).scrapes())
        self.assertEqual(len(scrapes), 1)
        return scrapes[0]

    def test_nests_files_under_their_filing(self) -> None:
        """The scraper stores a docket's files in one flat list.

        Does the loader put each one under the filing it belongs to?
        """
        scrape = self.scrape(_one_document())

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
            PRIVATE_PATH,
            "The download record's local path is joined onto the file.",
        )

    def test_joins_the_archive_row_onto_the_file(self) -> None:
        """What the file is and what it hashes to are known only to the download, which the run records apart from the docket. Does the loader put the archive's account of a file onto the file itself?"""
        _, digest, size, _ = archived(PRIVATE_PATH)

        scrape = self.scrape(_one_document())

        document = scrape.entries[0].attachments[0]
        self.assertEqual(document.content_hash, digest)
        self.assertEqual(document.file_size, size)
        self.assertEqual(
            document.content_type,
            "application/pdf",
            "The archive says the file is a PDF; the loader says what that "
            "means to S3.",
        )

    def test_an_oral_argument_playlist_is_typed_as_one(self) -> None:
        """Court-PASS publishes recordings as playlists rather than PDFs, and a playlist served as a PDF is one a browser will not play. Is the type taken from the file rather than assumed?"""
        playlist = f"{PRIVATE_PREFIX}nycourts_gov/{DOCKET_NUMBER}_webcast.asx"

        scrape = self.scrape(_one_document(playlist))

        self.assertEqual(
            scrape.entries[0].attachments[0].content_type, "video/x-ms-asf"
        )

    def test_a_file_with_no_archive_row_is_left_undescribed(self) -> None:
        """A downloaded file is always hashed, so a path with no archive row is the run contradicting itself. Does the file merge anyway, with nothing said about bytes nothing accounted for?"""
        scrape = self.scrape(_one_document(), archive=[])

        document = scrape.entries[0].attachments[0]
        self.assertEqual(document.local_path, PRIVATE_PATH)
        self.assertEqual(document.content_hash, "")
        self.assertIsNone(document.file_size)
        self.assertEqual(
            document.content_type,
            "",
            "S3 falls back to its own default rather than being told a type "
            "nothing established.",
        )

    def test_a_file_stored_under_another_extension_is_left_undescribed(
        self,
    ) -> None:
        """The archive's account of a file and the name it was stored under have to agree, or one of them is wrong about what the file is. Is the type withheld rather than read off the wrong one?"""
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable)

        with self.assertLogs(
            "cl.corpus_importer.state.new_york.loader", level=logging.ERROR
        ) as logs:
            scrape = self.scrape(
                _one_document(),
                archive=[(PRIVATE_PATH, "0" * 64, 1024, "asx")],
            )

        self.assertEqual(scrape.entries[0].attachments[0].content_type, "")
        self.assertIn("does not end in", logs.output[0])

    def test_case_date_filed_is_earliest_filing(self) -> None:
        """Court-PASS dates no case, only its filings.

        Does the earliest filing date stand in, and does a case whose filings
        were all reconstructed from the file list carry no date at all?
        """
        later = ENTRY | {
            "docket_entry_id": "e:respondent-brief:jones:1",
            "date_received": "2024-06-01",
        }
        undated = ENTRY | {"date_received": None}
        for label, entries, expected in (
            ("dated filings", [ENTRY, later], date(2024, 3, 2)),
            ("undated filings", [undated], None),
        ):
            with self.subTest(label):
                self.start_over()
                scrape = self.scrape(
                    [("NYCourtPassDocket", _docket(docket_entries=entries))]
                )

                self.assertEqual(scrape.date_filed, expected)

    def test_groups_attorneys_into_parties(self) -> None:
        """Court-PASS lists attorneys, not parties.

        Are the attorney rows folded into one party each?
        """
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
        """Court-PASS lists a party through its attorneys, and prints one without an attorney of record all the same. Is the party kept, with nobody under it?"""
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
        """The scraper stores a section it read nothing in as `null`, and SQLite yields a row for that null rather than no rows at all. Is it kept out of the payload, rather than becoming an empty filing, party or issue?"""
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
        """CourtListener keeps one attorney per name per docket, and Court-PASS can print a different firm for the same attorney on each party it represents. Is one set of details published for all of them, so the merge does not rewrite the row on every scrape?"""
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
        """A filing detail page that carried neither the Court's "no files" line nor a file table the scraper could read attests to nothing about the case's filings, and merging its empty file list would prune every document the docket has. Is it refused and named in the log, while a docket the Court states has no files at all still merges?"""
        _run_database(
            self.database,
            [
                ("NYCourtPassDocket", _docket(no_files_for_case=False)),
                (
                    "NYCourtPassDocket",
                    _docket(
                        docket_number="APL-2024-00178", no_files_for_case=True
                    ),
                ),
            ],
        )
        # The test runner disables logging outright for speed, and the log is
        # the only place an operator learns which docket drift in the file
        # table cost.
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable)

        with self.assertLogs(
            "cl.corpus_importer.state.loader", "ERROR"
        ) as logs:
            report = self.loader().load()

        self.assertEqual(
            (
                report.seen,
                report.merged,
                report.refused,
                report.invalid,
                report.failed,
            ),
            (2, 1, 1, 0, 0),
            "The refused docket is counted as refused, not passed over.",
        )
        self.assertEqual(Docket.objects.get().docket_number, "APL-2024-00178")
        self.assertIn(DOCKET_NUMBER, logs.output[0])

    def test_loads_a_docket_stating_an_uncovered_subcategory(self) -> None:
        """A subcategory the vocabulary does not cover must not cost the docket. Does the case load, with the issue recorded as unassigned and the Court's own wording kept?"""
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
        """A filing the scraper reconstructed from a document states no filing type at all, which is not the same as stating one the vocabulary does not cover. The scraper reports both as `None`, so what separates them by the time the merge stores a code is the raw string the loader hands over beside it: blank for the filing no table row named."""
        for label, raw, expected in (
            ("no table row named it", None, UNKNOWN),
            ("named but not covered", "Appellant Sur-Reply Brief", UNASSIGNED),
        ):
            with self.subTest(label):
                self.start_over()
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

    def test_the_worker_rebuilds_the_scrape_the_loader_read(self) -> None:
        """What celery carries is the scrape's own dump, so the worker's `model_validate_json` has to invert `model_dump_json` exactly. The vocabulary fields are where that can fail: an uncovered reading and an unstated one both dump as strings no vocabulary covers, so a vocabulary that could not read its own dump back would silently turn one into the other. Does the worker rebuild the scrape the loader validated?"""
        _run_database(
            self.database,
            [
                (
                    "NYCourtPassDocket",
                    _docket(
                        docket_entries=[
                            ENTRY
                            | {
                                # A filing the FILINGS table named in words no
                                # vocabulary covers, implying neither a role
                                # nor a document type.
                                "raw_filing_type": "Appellant Sur-Reply Brief",
                                "entry_filing_type": None,
                                "entry_role": None,
                                "entry_doctype": None,
                            }
                        ],
                        # An uncovered role beside an unstated document type.
                        files=[
                            FILE
                            | {"doc_role": "sur-appellant", "doc_type": None}
                        ],
                        issues=[
                            {
                                "category_raw": (
                                    "Corporations--Not-For-Profit Corporation"
                                ),
                                "category": "Corporations",
                                "subcategory": "Not-For-Profit Corporation",
                                "detail": "Whether the by-laws bind.",
                            }
                        ],
                    ),
                )
            ],
        )
        # The same run, read the way `scrapes()` reads it: this is the scrape
        # the load validated and dumped onto the queue.
        read = list(NYCoACourtPassLoader(self.database).scrapes())

        with patch(
            "cl.corpus_importer.tasks.merge_state_scrape_row.si"
        ) as task:
            self.loader(verify=False).load()

        payloads = [call.kwargs["payload"] for call in task.call_args_list]
        self.assertEqual(len(payloads), 1)
        self.assertEqual(
            NYCoACourtPassLoader.scrape_model.model_validate_json(payloads[0]),
            read[0],
        )

    def test_collapses_a_file_listed_twice(self) -> None:
        """Court-PASS sometimes lists one document twice on a filing, once servable and once not. Is the servable copy the one kept?"""
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

    def test_the_last_reading_of_a_docket_is_the_one_kept(self) -> None:
        """A docket listed at two positions in the search grid is scraped once per position, and the later reading is the better one -- and it is the reading the file archive keeps too. Does the query yield the docket once, as its last reading?"""
        scrape = self.scrape(
            [
                (
                    "NYCourtPassDocket",
                    _docket(case_name="Smith v. Roe", search_row=8),
                ),
                (
                    "NYCourtPassDocket",
                    _docket(case_name="Smith v. Jones", search_row=9),
                ),
            ]
        )

        self.assertEqual(scrape.case_name, "Smith v. Jones")

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
        _run_database(self.database, _one_document())

    def test_dispatches_extraction_for_the_documents_it_writes(self) -> None:
        """A merge only records where a document's file is.

        Is the document handed off for text extraction as the load goes, on
        the queue the load was given?
        """
        for label, kwargs, queue in (
            ("default queue", {}, "celery"),
            ("queue given", {"extraction_queue": "batch1"}, "batch1"),
        ):
            with self.subTest(label):
                self.start_over()
                self._run_holding_one_document()

                report = self.loader(**kwargs).load()

                self.assertEqual(report.merged, 1)
                document = NYCoADocument.objects.get()
                self.extraction.si.assert_called_once_with(
                    pks=document.pk,
                    check_if_needed=False,
                    model_name="search.NYCoADocument",
                    strip_html_tags=False,
                )
                self.extraction.si.return_value.set.assert_called_once_with(
                    queue=queue
                )

    def extraction_report(self, **kwargs: Any) -> ExtractionReport:
        """The extraction half of a load's report over a run of one docket."""
        report = self.loader(**kwargs).load()
        self.assertEqual(report.merged, 1)
        if (extraction := report.extraction) is None:
            self.fail("A load dispatching extraction reports on it.")
        return extraction

    def test_extraction_that_never_ran_is_reported(self) -> None:
        """A merge reporting success says extraction was dispatched, not that it ran, and a failed call to the extraction service leaves no other trace. Does the load notice the document sitting there unextracted?"""
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

    def test_a_document_extraction_ran_on_is_not_outstanding(self) -> None:
        """The check has to clear once extraction has run, or every load would end by crying wolf, and a document extraction ran on and failed is the extraction pipeline's problem rather than the load's. Does a document that came back count as done, with one that failed counted apart from those extraction never reached?"""
        for status, failed in (
            (NYCoADocument.OCR_COMPLETE, 0),
            (NYCoADocument.OCR_FAILED, 1),
        ):
            with (
                self.subTest(status=status),
                patch.object(
                    NYCoADocument, "extract", autospec=True
                ) as extract,
            ):
                self.start_over()
                self._run_holding_one_document()

                # Stand in for the extraction task having run and written
                # back.
                def ran(
                    document: NYCoADocument, queue: str, status: int = status
                ) -> bool:
                    NYCoADocument.objects.filter(pk=document.pk).update(
                        ocr_status=status
                    )
                    return True

                extract.side_effect = ran
                extraction = self.extraction_report()

                self.assertEqual(extraction.dispatched, 1)
                self.assertEqual(
                    (extraction.outstanding, extraction.failed), (0, failed)
                )
                self.assertTrue(
                    extraction.complete,
                    "Nothing here is still waiting to be read.",
                )

    def test_unextracted_documents_get_their_own_sentry_issue(self) -> None:
        """Extraction that never ran is a different problem from a merge that failed. Is it filed on its own, under the loader rather than the run?"""
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
        """Extraction cannot begin until the merges that write the documents have landed, so one budget shared between the two waits would have a run that spent it all on slow merges report every document as unextracted. Does each phase get its own wait?"""
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
        """A run that gives up while extraction is still coming down has found nothing wrong. Is that told apart from extraction that stopped?"""
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

    def test_reports_what_became_of_the_files_the_run_moved(self) -> None:
        """Only the workers see a file move, so a load has no way to know what became of one except by what the merges wrote down, and a file that never reached the public bucket leaves a document with nothing to serve, which no other count in the report would show. Does each outcome reach the report, with the two ways of failing reported apart so a reader knows whether re-running the load would mend it?"""
        for outcome, expected, unpublished in (
            (PublishOutcome.PUBLISHED, FileTally(moved=1), 0),
            (PublishOutcome.FAILED, FileTally(failed=1), 1),
            (PublishOutcome.MISSING, FileTally(missing=1), 1),
        ):
            with self.subTest(outcome=outcome):
                self.start_over()
                self._run_holding_one_document()
                self.publish_outcome = outcome

                report = self.loader().load()

                self.assertEqual(report.merged, 1)
                self.assertEqual(report.files, expected)
                self.assertEqual(
                    report.files.unpublished,
                    unpublished,
                    "Only a moved file is one CourtListener can serve.",
                )

    def test_unmoved_files_get_their_own_sentry_issue(self) -> None:
        """A file stuck in the private bucket is a different problem from a merge that failed -- the merge succeeded. Is it filed on its own?"""
        self.publish_outcome = PublishOutcome.FAILED
        self._run_holding_one_document()
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable)

        with self.assertLogs(
            "cl.corpus_importer.state.loader", "ERROR"
        ) as logs:
            report = self.loader().load()

        self.assertEqual(report.files, FileTally(failed=1))
        self.assertEqual(
            [record.fingerprint for record in logs.records],  # type: ignore[attr-defined]
            [["nycoa", LoadPhase.PUBLISHING]],
            "The merges themselves were clean; only the copy was not.",
        )

    def test_a_docket_with_no_documents_moves_and_extracts_nothing(
        self,
    ) -> None:
        """A docket with no files to move must not read as a run whose files all failed. Is its empty tally left empty, and is a merge that wrote no documents left without extraction?"""
        _run_database(self.database, [("NYCourtPassDocket", _docket())])

        report = self.loader().load()

        self.assertEqual(report.merged, 1)
        self.assertFalse(report.files)
        self.extraction.si.assert_not_called()

    def test_file_counts_survive_into_a_verify_only_pass(self) -> None:
        """`--skip-load` reads the ledger and never opens the run database, so anything the merges reported has to be in Redis rather than in the loading process. Are the file counts still there?"""
        self._run_holding_one_document()
        self.loader().load()

        report = self.loader().verify_only()

        self.assertFalse(report.rows_read)
        self.assertEqual(report.files, FileTally(moved=1))

    def test_skipping_extraction_still_merges(self) -> None:
        """`extract=False` leaves the work to the sweep.

        Is the document written all the same, with nothing dispatched and the
        extraction check held back rather than reporting every document as
        outstanding?
        """
        self._run_holding_one_document()

        report = self.loader(extract=False).load()

        self.assertEqual(report.merged, 1)
        self.assertTrue(NYCoADocument.objects.exists())
        self.extraction.si.assert_not_called()
        self.assertIsNone(report.extraction)

    def test_skips_a_docket_with_no_number(self) -> None:
        """A docket with no number cannot be matched against anything we already hold. Is it skipped rather than merged into nothing?"""
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
