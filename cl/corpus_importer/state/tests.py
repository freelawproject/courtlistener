import json
import sqlite3
import time
from collections.abc import Generator, Iterable, Iterator, Sequence
from contextlib import closing, contextmanager, nullcontext
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, ClassVar
from unittest.mock import MagicMock, Mock, call, patch

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import override_settings
from pydantic import BaseModel

from cl.corpus_importer.management.commands.load_state_scrape import (
    DEFAULT_THROTTLE,
)
from cl.corpus_importer.state.ledger import LoadLedger
from cl.corpus_importer.state.loader import (
    JKentScrapeLoader,
    LoadPhase,
    LoadReport,
    UnusableScrape,
    WaitOutcome,
)
from cl.corpus_importer.state.merger import (
    Constant,
    Merger,
    MergerConfig,
    MergerState,
    Scrape,
)
from cl.corpus_importer.state.preflight import (
    STANDARD_CHECKS,
    CheckError,
    CheckOutcome,
    CheckResult,
    InvalidRows,
    PreflightCheck,
    PreflightFailed,
    UnhashedFiles,
    run_checks,
)
from cl.corpus_importer.state.registry import LOADERS
from cl.corpus_importer.state.run_db import (
    RunDatabaseUnavailable,
    downloaded_run_database,
    scrape_bucket_storage,
)
from cl.corpus_importer.state.storage import (
    PublishOutcome,
    copy_file,
    delete_file,
)
from cl.corpus_importer.state.test_helpers import (
    ARCHIVED_FILE_INSERT,
    ARCHIVED_FILES_TABLE,
    RESULTS_TABLE,
    ArchivedFile,
    RunDatabaseTestCase,
    write_run_database,
)
from cl.corpus_importer.state.utils import FileTally, MergeResult
from cl.corpus_importer.tasks import merge_state_scrape_row
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.lib.storage import AWSMediaStorage
from cl.search.docket_sources import DocketSources
from cl.search.factories import CourtFactory
from cl.search.models import (
    Court,
    Docket,
)
from cl.tests.cases import SimpleTestCase


def _archived_files(hashes: Sequence[str | None]) -> list[ArchivedFile]:
    """The `archived_files` rows for a downloaded file per entry in `hashes`.

    Args:
        hashes: One content hash per file. An empty string or `None` stands
            for a file the scraper stored without hashing it.
    """
    return [
        (f"f{n}.pdf", digest, None, None) for n, digest in enumerate(hashes)
    ]


def _run_database(
    path: Path,
    payloads: list[dict[str, Any] | str],
    hashes: Sequence[str | None] = (),
) -> None:
    """Write a run database of `TestResult` rows for the generic loader.

    Args:
        path: Where to write the database.
        payloads: One entry per row. A dict is serialized; a string is
            stored as given, so a test can write a blob that will not decode.
        hashes: One content hash per downloaded file the run archived.
    """
    write_run_database(
        path,
        [
            (
                "TestResult",
                payload if isinstance(payload, str) else json.dumps(payload),
            )
            for payload in payloads
        ],
        _archived_files(hashes),
    )


class LoaderScrape(BaseModel):
    """The scrape a `JKentScrapeLoader` test subclass validates rows into."""

    docket_number: str
    case_name: str = ""


class LoaderTestCase(RunDatabaseTestCase):
    """A run database in a temporary directory and a generic loader over it.

    The loader is court-agnostic, so its tests exercise it through a throwaway
    scrape model and merger rather than through any one state's loader.

    Celery runs eagerly under test, so a load's merges happen inline as it
    dispatches them and its ledger is full by the time it verifies.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()

    def loader_class(
        self, **attributes: Any
    ) -> type[JKentScrapeLoader[Any, Any, Any]]:
        """A loader over the test database, merging into `Docket`.

        The class is put in the registry for the test's lifetime, because a
        merge task is handed a loader's name and looks the class back up by
        it -- a loader nothing has registered cannot be merged.

        Args:
            attributes: Overrides for the returned class, so a test can
                supply its own `normalize` or merger.

        Returns:
            The loader class.
        """
        # Not named `court`: a class body cannot close over an enclosing local
        # whose name it also assigns.
        test_court = self.court

        class TestMerger(Merger[LoaderScrape, None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(test_court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Scrape(LoaderScrape).docket_number
            case_name: str = Scrape(LoaderScrape).case_name

            def lookup(
                self, state: MergerState.Lookup[LoaderScrape, None, Docket]
            ) -> MergerState.LookupOutput[LoaderScrape, None, Docket]:
                return self.found(
                    state,
                    Docket.objects.filter(
                        court=test_court,
                        docket_number=state.scrape.docket_number,
                    ).only(*self.config.fields)[:2],
                )

        loader: type[JKentScrapeLoader[Any, Any]] = type(
            "TestLoader",
            (JKentScrapeLoader,),
            {
                "name": "test",
                "query": "SELECT data_json FROM results ORDER BY id",
                "scrape_model": LoaderScrape,
                "merger": TestMerger,
            }
            | attributes,
        )
        LOADERS[loader.name] = loader
        self.addCleanup(LOADERS.pop, loader.name, None)
        return loader

    def raising_loader(
        self, dockets: set[str], error: Exception | None = None
    ) -> type[JKentScrapeLoader[Any, Any, Any]]:
        """A loader whose merger raises on the dockets named in `dockets`.

        Args:
            dockets: Docket numbers to raise on, read at merge time so a test
                can empty it and retry the same rows successfully.
            error: What to raise, defaulting to a `DatabaseError`, which the
                merge task retries before giving up on the row.

        Returns:
            The loader class.
        """
        raised = error or DatabaseError("the database is having none of it")

        class RaisingMerger(self.loader_class().merger):  # type: ignore[misc, name-defined]
            def merge(self) -> Any:
                if self.state.scrape.docket_number in dockets:
                    raise raised
                return super().merge()

        return self.loader_class(merger=RaisingMerger)

    def merge_retry(self) -> set[str]:
        """The rows the ledger is holding for a merge retry."""
        return set(self.redis.smembers(f"{self.key}:merge_retry"))

    def extraction_retry(self) -> set[str]:
        """The documents the ledger is holding for an extraction retry."""
        return set(self.redis.smembers(f"{self.key}:extraction_retry"))


class JKentScrapeLoaderTest(LoaderTestCase):
    """Tests for the generic jkent run-database loader."""

    def test_missing_database(self) -> None:
        """Is a run database that isn't there reported as such, rather than counted as an empty run?"""
        loader = self.loader()

        with self.assertRaises(FileNotFoundError):
            loader.load()

    def test_load_merges_every_row(self) -> None:
        """Does a clean run merge one object per row and report it?"""
        _run_database(
            self.database,
            [
                {"docket_number": "A-1", "case_name": "Smith v Jones"},
                {"docket_number": "A-2", "case_name": "Roe v Doe"},
            ],
        )

        report = self.loader().load()

        self.assertEqual((report.seen, report.dispatched), (2, 2))
        self.assertEqual((report.merged, report.failed), (2, 0))
        self.assertEqual((report.invalid, report.refused), (0, 0))
        self.assertTrue(report.accounted_for)
        self.assertEqual(report.creates, {"Docket": 2})
        self.assertEqual(
            set(Docket.objects.values_list("docket_number", flat=True)),
            {"A-1", "A-2"},
        )

    def test_every_row_goes_to_the_queue_in_its_own_task(self) -> None:
        """Merging a docket per task is what lets one that fails cost only itself. Is one task dispatched per row, carrying the row's own payload?"""
        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        with patch(
            "cl.corpus_importer.tasks.merge_state_scrape_row.si"
        ) as task:
            self.loader(ingest_queue="batch2", verify=False).load()

        self.assertEqual(
            [call.kwargs["row"] for call in task.call_args_list], [1, 2]
        )
        self.assertEqual(
            [
                json.loads(call.kwargs["payload"])["docket_number"]
                for call in task.call_args_list
            ],
            ["A-1", "A-2"],
        )
        task.return_value.set.assert_called_with(queue="batch2")

    def test_scrapes_yields_without_writing(self) -> None:
        """`scrapes()` is the seam for inspecting a run.

        Does it produce the validated scrapes and leave the database alone?
        """
        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        scrapes = list(self.loader().scrapes())

        self.assertEqual([s.docket_number for s in scrapes], ["A-1", "A-2"])
        self.assertFalse(Docket.objects.exists())

    def test_limit_stops_the_run_early(self) -> None:
        """Does `limit` stop the load after exactly that many rows, including a limit computed at runtime that came out zero, rather than the one row an off-by-one would let through?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        for limit in (2, 0):
            with self.subTest(limit=limit):
                Docket.objects.all().delete()

                report = self.loader(limit=limit).load()

                self.assertEqual(
                    (report.seen, report.dispatched, report.merged),
                    (limit, limit, limit),
                )
                self.assertEqual(Docket.objects.count(), limit)

    def test_normalize_returning_none_is_invalid(self) -> None:
        """`normalize` returning `None` is the loader's own judgment that there is nothing to do with a row. Is it counted as invalid, and left undispatched?"""

        def normalize(
            self: Any, payload: dict[str, Any], row: sqlite3.Row
        ) -> dict[str, Any] | None:
            return None if payload["docket_number"] == "A-1" else payload

        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        report = self.loader(self.loader_class(normalize=normalize)).load()

        self.assertEqual(
            (report.seen, report.invalid, report.dispatched, report.merged),
            (2, 1, 1, 1),
        )
        self.assertEqual(report.refused, 0)
        self.assertEqual(Docket.objects.count(), 1)

    def test_normalize_raising_unusable_scrape_is_refused(self) -> None:
        """`UnusableScrape` says the run needs looking at.

        Is the row counted as refused and never dispatched, since merging it is
        exactly what the loader objected to?
        """

        def normalize(
            self: Any, payload: dict[str, Any], row: sqlite3.Row
        ) -> dict[str, Any] | None:
            raise UnusableScrape(f"{payload['docket_number']} is unusable")

        _run_database(self.database, [{"docket_number": "A-1"}])

        report = self.loader(self.loader_class(normalize=normalize)).load()

        self.assertEqual(
            (report.seen, report.refused, report.dispatched), (1, 1, 0)
        )
        self.assertEqual(
            (report.invalid, report.merged, report.failed), (0, 0, 0)
        )
        self.assertFalse(Docket.objects.exists())

    def test_a_bad_payload_is_invalid(self) -> None:
        """A payload the scrape model rejects usually means scraper drift, and a scrape that stopped mid-write leaves a truncated blob behind. Is either counted as invalid rather than raised, so one bad row doesn't cost the run?"""
        bad_payloads: tuple[tuple[str, dict[str, Any] | str], ...] = (
            ("does not fit the model", {"case_name": "No docket number here"}),
            ("will not decode", '{"docket_number": "A-1'),
        )
        for label, bad_payload in bad_payloads:
            with self.subTest(label):
                self.database.unlink(missing_ok=True)
                Docket.objects.all().delete()
                _run_database(
                    self.database, [bad_payload, {"docket_number": "A-2"}]
                )

                report = self.loader().load()

                self.assertEqual(
                    (
                        report.seen,
                        report.invalid,
                        report.merged,
                        report.failed,
                    ),
                    (2, 1, 1, 0),
                )
                self.assertEqual(
                    Docket.objects.get().docket_number,
                    "A-2",
                    "The row after the bad one still merges.",
                )

    def test_a_bad_row_is_named_in_the_log(self) -> None:
        """A count of bad rows says something drifted; only the row number says where to go and look, and it is what `--start-row` would need to reach that row again. Does the log carry it?"""
        _run_database(
            self.database,
            [
                {"docket_number": "A-1"},
                '{"docket_number": "A-2',
                {"docket_number": "A-3"},
            ],
        )
        self.enable_logging()

        with self.assertLogs(
            "cl.corpus_importer.state.loader", "ERROR"
        ) as logs:
            self.loader().load()

        self.assertIn("row 2 of run.db", logs.output[0])

    def test_a_bad_payload_is_named_by_its_docket_where_it_has_one(
        self,
    ) -> None:
        """A row number gets you back to the row, but a docket number is what anybody actually searches for. Does a validation failure carry both where the payload decoded far enough to have a docket number, and fall back to the row number where it did not?"""
        self.enable_logging()
        for label, payload, expected in (
            (
                "has a docket number",
                {"docket_number": "A-1", "case_name": 7},
                "A-1 (row 1) of run.db",
            ),
            (
                "has none to give",
                {"case_name": "No docket number here"},
                "row 1 of run.db",
            ),
        ):
            with self.subTest(label):
                self.database.unlink(missing_ok=True)
                _run_database(self.database, [payload])

                with self.assertLogs(
                    "cl.corpus_importer.state.loader", "ERROR"
                ) as logs:
                    report = self.loader().load()

                self.assertEqual(report.invalid, 1)
                self.assertIn(expected, logs.output[0])
                self.assertIn("LoaderScrape", logs.output[0])

    def test_merger_declining_a_scrape_is_a_failure(self) -> None:
        """A merger refuses a scrape in its own `validator`, which it reports as a failure. Does the row come back from the queue counted as one, with the rest of the run left to merge?"""

        class RejectingMerger(self.loader_class().merger):  # type: ignore[misc, name-defined]
            @staticmethod
            def validator(scrape: LoaderScrape) -> bool:
                return scrape.docket_number != "A-1"

        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        report = self.loader(self.loader_class(merger=RejectingMerger)).load()

        self.assertEqual(
            (report.seen, report.dispatched, report.merged, report.failed),
            (2, 2, 1, 1),
        )
        self.assertEqual(
            (report.rejected, report.errored),
            (1, 0),
            "The merge ran and would not have the scrape, which is the "
            "scraper's problem rather than a row to re-run.",
        )
        self.assertTrue(report.accounted_for)
        self.assertEqual(Docket.objects.count(), 1)

    def test_a_merge_out_of_retries_is_recorded_rather_than_dropped(
        self,
    ) -> None:
        """Celery says nothing when a task's retries run out, which is the whole reason for the ledger. Each row is merged in a task of its own, so is the row written off as failed rather than left looking like it never ran, while the rest of the run continues?"""
        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )
        self.enable_logging()

        with (
            patch.object(merge_state_scrape_row, "max_retries", 0),
            self.assertLogs("cl.corpus_importer.tasks", "ERROR") as logs,
        ):
            report = self.loader(self.raising_loader({"A-1"})).load()

        self.assertEqual(
            (report.seen, report.dispatched, report.failed, report.merged),
            (2, 2, 1, 1),
        )
        self.assertEqual(
            Docket.objects.get().docket_number,
            "A-2",
            "The row after the raising one still merges.",
        )
        self.assertEqual(
            (report.rejected, report.errored),
            (0, 1),
            "No merge reached a verdict, so this is a row to re-run rather "
            "than a scrape to go and fix.",
        )
        self.assertTrue(
            report.accounted_for,
            "The row was written off, not left looking undispatched.",
        )
        self.assertIn("giving up", logs.output[0])
        self.assertEqual(
            logs.records[0].fingerprint,  # type: ignore[attr-defined]
            ["test", LoadPhase.MERGE],
            "Filed under the loader's own Sentry issue for merge failures.",
        )

    def test_a_merger_bug_is_not_mistaken_for_a_dropped_task(self) -> None:
        """An exception the task does not expect is a bug in the merger, not a broker that lost a message. Left to propagate it would take its row with it, and reconciliation would report the docket as one celery dropped -- sending somebody to the broker for a fault in the code. Is it written off as a merge failure instead?"""
        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )
        self.enable_logging()
        buggy = self.raising_loader(
            {"A-1", "A-2"}, AttributeError("the merger has a typo in it")
        )

        with self.assertLogs("cl.corpus_importer.tasks", "ERROR") as logs:
            report = self.loader(buggy).load()
            # Asserted inside the block so that a regression fails on the
            # mis-attribution rather than on the log line that goes with it.
            self.assertEqual(
                report.missing_count,
                0,
                "Celery lost nothing. The merger raised, and that is a "
                "different problem with a different fix.",
            )
            self.assertEqual((report.dispatched, report.failed), (2, 2))
            self.assertTrue(report.accounted_for)

        self.assertIn("raised AttributeError", logs.output[0])
        self.assertEqual(
            logs.records[0].fingerprint,  # type: ignore[attr-defined]
            ["test", LoadPhase.MERGE],
        )

    def test_a_merge_that_never_reports_is_missing(self) -> None:
        """A worker killed mid-merge takes its task with it and tells no one.

        Does the load name the row rather than reporting a clean run?
        """
        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        # Nothing runs the task, which is what a lost message looks like from
        # here: the ledger holds the dispatch and never gets an outcome.
        with patch("cl.corpus_importer.tasks.merge_state_scrape_row.si"):
            report = self.loader(verify_timeout=0).load()

        self.assertEqual((report.dispatched, report.merged), (2, 0))
        self.assertFalse(report.accounted_for)
        self.assertEqual(report.missing_count, 2)
        self.assertEqual(report.missing, {1: "A-1", 2: "A-2"})
        self.assertEqual(report.merge_wait, WaitOutcome.STALLED)
        self.assertTrue(report.dropped)

    def test_dropped_rows_get_their_own_sentry_issue(self) -> None:
        """A dropped task is the one failure nothing else in the system reports, so it has to be findable on its own rather than mixed in with the merges that failed loudly. Is it filed under its own fingerprint, keyed on the loader rather than the run?"""
        _run_database(self.database, [{"docket_number": "A-1"}])
        self.enable_logging()

        with (
            patch("cl.corpus_importer.tasks.merge_state_scrape_row.si"),
            self.assertLogs(
                "cl.corpus_importer.state.loader", "ERROR"
            ) as logs,
        ):
            self.loader(verify_timeout=0).load()

        self.assertEqual(
            logs.records[0].fingerprint,  # type: ignore[attr-defined]
            ["test", LoadPhase.RECONCILIATION],
        )
        self.assertNotIn(
            "run.db",
            str(logs.records[0].fingerprint),  # type: ignore[attr-defined]
            "Fingerprinting by run database would open a fresh Sentry issue "
            "every hourly load.",
        )

    def test_a_settled_row_leaves_nothing_behind(self) -> None:
        """The ledger is what keeps a long run from costing Redis a row per docket. Does a row that reported back take itself off, whichever way it went, leaving only counters?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        report = self.loader().load()

        self.assertEqual(report.merged, 5)
        self.assertEqual(
            self.redis.hlen(f"{self.key}:pending"),
            0,
            "Five merged dockets cost the ledger no rows at all.",
        )
        self.assertEqual(self.ledger().totals().merged, 5, "Only the count.")

    def test_file_counts_share_the_run_s_counter_hash(self) -> None:
        """A load moves a file per document, so anything the ledger spent per file would dwarf what it spends per docket. Do the file tallies ride along in the counter hash the row's own outcome is written to, rather than taking a key or a round trip of their own?"""
        ledger = self.ledger()
        ledger.dispatched(1, "A-1")

        ledger.merged(1, MergeResult(), FileTally(moved=2, missing=1))

        self.assertEqual(
            set(self.redis.keys(f"{self.key}:*")),
            {f"{self.key}:counts"},
            "The file counts cost the ledger no key of their own.",
        )
        self.assertEqual(ledger.totals().files, FileTally(moved=2, missing=1))

    def test_a_merge_that_moved_no_files_counts_none(self) -> None:
        """Most loaders publish nothing at all, and most merges of the one that does move no files. Is the usual merge left writing exactly what it wrote before?"""
        ledger = self.ledger()
        ledger.dispatched(1, "A-1")

        ledger.merged(1, MergeResult())

        self.assertEqual(
            set(self.redis.hkeys(f"{self.key}:counts")),
            {"dispatched", "merged"},
            "Nothing was moved, so nothing counts it.",
        )
        self.assertFalse(ledger.totals().files)

    def test_file_counts_add_up_across_rows(self) -> None:
        """The tally spans the run rather than any one docket.

        Does each row's merge add to it?
        """
        ledger = self.ledger()

        for row, files in enumerate(
            (
                FileTally(moved=3),
                FileTally(moved=1, failed=2),
                FileTally(missing=1),
            )
        ):
            ledger.dispatched(row, f"A-{row}")
            ledger.merged(row, MergeResult(), files)

        self.assertEqual(
            ledger.totals().files, FileTally(moved=4, missing=1, failed=2)
        )

    def test_a_rejected_row_still_counts_the_files_it_moved(self) -> None:
        """Publishing happens before the write that can fail, so a merge that went on to be rejected has still left files in the public bucket. Are they counted, rather than lost with the row?"""
        ledger = self.ledger()
        ledger.dispatched(1, "A-1")

        ledger.rejected(
            1,
            MergeResult(failures={"Docket": [None]}),
            FileTally(moved=1),
        )

        self.assertEqual(ledger.totals().files, FileTally(moved=1))
        self.assertEqual(ledger.totals().rejected, 1)

    def test_a_falling_count_is_waited_on(self) -> None:
        """A count still coming down means somebody is working on our rows.

        Does the load keep waiting, and poll the count rather than dragging
        every pending row across on each pass?
        """
        loader = self.loader(in_flight_time=600, verify_timeout=600)
        counts = [3, 2, 1, 0]

        with (
            patch.object(LoadLedger, "outstanding_count", side_effect=counts),
            patch.object(LoadLedger, "outstanding") as rows,
            patch("cl.corpus_importer.state.loader.time.sleep") as sleep,
        ):
            outstanding, wait = loader._await_drain(
                self.ledger().outstanding_count, poll=1, work="merges"
            )

        self.assertEqual((outstanding, wait), (0, WaitOutcome.DRAINED))
        self.assertEqual(sleep.call_count, len(counts) - 1)
        rows.assert_not_called()

    def test_a_count_that_stops_falling_ends_the_wait(self) -> None:
        """A count that stops moving within the in-flight time says the work is gone, while giving up at the deadline on a queue that was still working is not a finding. Is the first reported as a conclusive stall, and the second told apart from it as a timeout that says nothing about the work still left?"""
        for in_flight_time, verify_timeout, expected, conclusive in (
            (0, 600, WaitOutcome.STALLED, True),
            (600, 0, WaitOutcome.TIMED_OUT, False),
        ):
            with self.subTest(expected=expected):
                loader = self.loader(
                    in_flight_time=in_flight_time,
                    verify_timeout=verify_timeout,
                )

                with patch.object(
                    LoadLedger, "outstanding_count", return_value=4
                ):
                    outstanding, wait = loader._await_drain(
                        self.ledger().outstanding_count, poll=1, work="merges"
                    )

                self.assertEqual((outstanding, wait), (4, expected))
                self.assertEqual(wait.conclusive, conclusive)

    def test_skipping_verification_reports_only_what_was_dispatched(
        self,
    ) -> None:
        """A load meant to be left running should not sit waiting on its queues. Does `verify=False` return the dispatch counts alone?"""
        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        report = self.loader(verify=False).load()

        self.assertEqual((report.seen, report.dispatched), (2, 2))
        self.assertEqual(
            (report.merged, report.failed),
            (0, 0),
            "Nothing was read back out of the ledger.",
        )
        self.assertEqual(
            Docket.objects.count(), 2, "The merges ran all the same."
        )

    def test_report_str_names_every_count(self) -> None:
        """The report is what an operator reads off a load.

        Does its summary state every count, keeping the two ways a merge fails
        apart?
        """
        report = LoadReport(
            seen=8,
            dispatched=5,
            merged=2,
            rejected=1,
            errored=1,
            invalid=2,
            refused=1,
            missing_count=1,
            missing={4: "A-4"},
        )

        self.assertEqual(
            str(report),
            "8 seen, 5 dispatched, 2 merged, 1 rejected, 1 errored, "
            "2 invalid, 1 refused, 1 missing",
        )
        self.assertEqual(report.failed, 2, "Both, for a caller wanting one.")

    def test_db_delay_waits_between_rows(self) -> None:
        """A long load has to leave the queue room to drain, but the default is to run flat out. Does `db_delay` wait after each row, and does the default zero delay skip the wait rather than sleeping zero seconds three thousand times?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(3)],
        )

        cases: tuple[tuple[str, dict[str, Any], list[Any]], ...] = (
            ("a delay", {"db_delay": 0.25}, [call(0.25)] * 3),
            ("the default", {}, []),
        )
        for label, kwargs, expected in cases:
            with self.subTest(label):
                with patch(
                    "cl.corpus_importer.state.loader.time.sleep"
                ) as sleep:
                    self.loader(**kwargs).load()

                self.assertEqual(sleep.call_args_list, expected)

    def test_both_queues_get_a_throttle(self) -> None:
        """Merges dispatch their own extraction, so a load can bury either queue. Is a throttle built for each one it was given a rate for?"""
        with patch(
            "cl.corpus_importer.state.loader.CeleryThrottle"
        ) as throttle_class:
            self.loader(
                ingest_throttle=4,
                ingest_queue="batch1",
                extraction_throttle=6,
                extraction_queue="batch2",
            )

        self.assertEqual(
            throttle_class.call_args_list,
            [
                call(min_items=4, queue_name="batch1"),
                call(min_items=6, queue_name="batch2"),
            ],
        )

    def test_every_throttle_gets_its_say_before_a_row_goes_out(self) -> None:
        """A throttle only holds a load back if it is consulted.

        Does each one get asked before every dispatch?
        """
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(3)],
        )
        with patch(
            "cl.corpus_importer.state.loader.CeleryThrottle"
        ) as throttle_class:
            loader = self.loader(ingest_throttle=4, extraction_throttle=6)

        loader.load()

        self.assertEqual(throttle_class.return_value.maybe_wait.call_count, 6)

    def test_a_queue_with_nothing_to_hold_back_is_not_throttled(self) -> None:
        """Building a throttle polls the celery queue. Does a load that asked for no throttling, or that dispatches no extraction for its extraction throttle to hold back, poll no queues?"""
        cases: tuple[tuple[str, dict[str, Any]], ...] = (
            ("no throttle", {}),
            ("no extraction", {"extract": False, "extraction_throttle": 6}),
        )
        for label, kwargs in cases:
            with self.subTest(label):
                self.assertEqual(self.loader(**kwargs).throttles, [])


class ExtractionTestCase(LoaderTestCase):
    """A loader test case with a stand-in for a state document model.

    What these tests check is which queries the loader asks the document model
    and what it does with the answers. Checking that extraction actually ran
    takes a real model, and lives with the New York loader's tests.
    """

    def document(self, pk: int, dispatched: bool = True) -> Any:
        """A document row that reports whether extraction was dispatched."""
        document = Mock(pk=pk)
        document.extract.return_value = dispatched
        return document

    def document_model(self, outstanding: Sequence[int] = ()) -> Any:
        """A stand-in document model reporting `outstanding` unextracted PKs.

        Args:
            outstanding: The PKs `unextracted` reports, both when a load
                verifies itself and when a retry re-checks.

        Returns:
            The model.
        """
        model = Mock(__name__="Doc")
        unextracted = model.unextracted.return_value
        # What the wait polls on, what the report reads, and what a retry
        # re-checks against, in that order.
        unextracted.count.return_value = 0
        unextracted.values_list.return_value = list(outstanding)
        unextracted.filter.return_value = [
            self.document(pk) for pk in outstanding
        ]
        model.written_since.return_value.filter.return_value.count.return_value = 0
        return model


class JKentScrapeLoaderExtractionTest(ExtractionTestCase):
    """Tests for the documents a load hands to the extraction queue."""

    def test_only_documents_actually_sent_are_expected_back(self) -> None:
        """A document with no file to read is never dispatched and will never change status. Is it left out of what the load waits on?"""
        model = self.document_model()
        model._default_manager.filter.return_value = [
            self.document(1),
            self.document(2, dispatched=False),
        ]
        loader_class = self.loader_class(document_model=model)

        dispatched = loader_class.dispatch_extraction(
            MergeResult(creates={"Doc": {1, 2}}), "batch1"
        )

        self.assertEqual(dispatched, {1})
        model._default_manager.filter.assert_called_once_with(pk__in={1, 2})

    def test_a_loader_writing_no_documents_dispatches_nothing(self) -> None:
        """Does a loader with no document model leave extraction alone?"""
        loader_class = self.loader_class()

        self.assertEqual(
            loader_class.dispatch_extraction(
                MergeResult(creates={"Docket": {1}}), "celery"
            ),
            set(),
        )


class StateStorageTest(SimpleTestCase):
    """Tests for the server-side copies and deletes publishing is built on.

    The loader and merger tests stand in for this module, so this is where the
    S3 calls it makes are pinned down.
    """

    SOURCE_KEY = "responses/dockets/ny/abc123.pdf"
    PUBLISHED_KEY = "recap/gov.uscourts.ny.1/gov.uscourts.ny.1.undated.2.pdf"

    def setUp(self) -> None:
        super().setUp()
        self.storage = MagicMock()
        self.storage.get_object_parameters.return_value = {
            "CacheControl": "max-age=315360000"
        }
        self.client: MagicMock = self.storage.connection.meta.client
        patcher = patch(
            "cl.corpus_importer.state.storage.AWSMediaStorage",
            return_value=self.storage,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def copy(self, content_type: str = "") -> PublishOutcome:
        """Copy `SOURCE_KEY` out of the private bucket to `PUBLISHED_KEY`."""
        return copy_file(
            settings.AWS_PRIVATE_STORAGE_BUCKET_NAME,
            self.SOURCE_KEY,
            self.PUBLISHED_KEY,
            content_type,
        )

    @staticmethod
    def error(code: str) -> ClientError:
        """The error S3 raises when it answers a copy with `code`."""
        return ClientError(
            {"Error": {"Code": code, "Message": "nope"}}, "CopyObject"
        )

    def test_copy_describes_how_the_file_should_be_served(self) -> None:
        """Does the copy land in the public bucket with the ACL, cache headers and content type a file served from there needs?"""
        self.assertIs(self.copy("application/pdf"), PublishOutcome.PUBLISHED)

        self.client.copy_object.assert_called_once_with(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=self.PUBLISHED_KEY,
            CopySource={
                "Bucket": settings.AWS_PRIVATE_STORAGE_BUCKET_NAME,
                "Key": self.SOURCE_KEY,
            },
            MetadataDirective="REPLACE",
            CacheControl="max-age=315360000",
            ACL=settings.AWS_DEFAULT_ACL,
            ContentType="application/pdf",
        )

    def test_copy_leaves_the_original_alone(self) -> None:
        """The loader deletes the original only once the document points at the copy. Does copying alone delete nothing?"""
        self.copy()

        self.client.delete_object.assert_not_called()

    def test_copy_without_a_content_type_leaves_it_to_s3(self) -> None:
        """A scrape does not always state a MIME type.

        Is the argument left off rather than sent empty, which would serve the
        file as nothing?
        """
        self.copy()

        self.assertNotIn(
            "ContentType", self.client.copy_object.call_args.kwargs
        )

    def test_copy_reports_how_it_failed(self) -> None:
        """A source that is not there will not appear on a re-run, unlike a refusal, so the two are reported apart. A `BotoCoreError` never got an answer out of S3, so it counts as the retriable kind. Is each read off the error the copy raised, without asking the bucket again?"""
        for error, expected in (
            (self.error("AccessDenied"), PublishOutcome.FAILED),
            (self.error("NoSuchKey"), PublishOutcome.MISSING),
            (BotoCoreError(), PublishOutcome.FAILED),
        ):
            with self.subTest(expected=expected):
                self.client.copy_object.side_effect = error

                self.assertIs(self.copy(), expected)
        self.client.head_object.assert_not_called()

    def test_delete_names_the_bucket(self) -> None:
        """Files are deleted from both buckets.

        Does the delete go to the one it was asked to?
        """
        delete_file(settings.AWS_PRIVATE_STORAGE_BUCKET_NAME, self.SOURCE_KEY)

        self.client.delete_object.assert_called_once_with(
            Bucket=settings.AWS_PRIVATE_STORAGE_BUCKET_NAME,
            Key=self.SOURCE_KEY,
        )

    def test_delete_swallows_a_refusal(self) -> None:
        """The document is settled by the time this runs, so a file left behind must not fail the load."""
        self.client.delete_object.side_effect = self.error("AccessDenied")

        delete_file(settings.AWS_STORAGE_BUCKET_NAME, self.PUBLISHED_KEY)


class PreflightCheckTest(SimpleTestCase):
    """Tests for the checks themselves, apart from any load that runs them."""

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database_count = 0

    def open_database(
        self,
        schema: str,
        insert: str = "",
        rows: Iterable[tuple[Any, ...]] = (),
    ) -> sqlite3.Connection:
        """A fresh run database, open and ready to be checked.

        Each call gets a database of its own, so one test can build two.

        Args:
            schema: The statement creating the database's one table.
            insert: The statement each of `rows` is inserted with.
            rows: The table's rows.

        Returns:
            The open connection.
        """
        self.database_count += 1
        database = Path(self.directory.name) / f"run-{self.database_count}.db"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute(schema)
            if insert:
                connection.executemany(insert, rows)
            connection.commit()
        opened = sqlite3.connect(database)
        opened.row_factory = sqlite3.Row
        self.addCleanup(opened.close)
        return opened

    def results(self, rows: list[tuple[str, int]]) -> sqlite3.Connection:
        """A run database holding `rows` in its `results` table.

        Args:
            rows: One `(result_type, is_valid)` pair per row.

        Returns:
            The open connection.
        """
        return self.open_database(
            RESULTS_TABLE,
            "INSERT INTO results (result_type, data_json, is_valid) "
            "VALUES (?, '{}', ?)",
            rows,
        )

    def archive(self, hashes: list[str | None]) -> sqlite3.Connection:
        """A run database whose archive holds a file per entry in `hashes`.

        Args:
            hashes: One content hash per downloaded file. An empty string or
                `None` stands for a file the scraper stored without hashing
                it.

        Returns:
            The open connection.
        """
        return self.open_database(
            ARCHIVED_FILES_TABLE, ARCHIVED_FILE_INSERT, _archived_files(hashes)
        )

    def test_a_clean_run_database_passes(self) -> None:
        """Does a run database with nothing invalid, or whose scraper hashed everything it downloaded -- including an empty archive, which must pass rather than divide by nothing -- come back as passing, with nothing to report?"""
        for label, check, connection in (
            (
                "nothing invalid",
                InvalidRows(),
                self.results([("Docket", 1)] * 3),
            ),
            (
                "every file hashed",
                UnhashedFiles(),
                self.archive(["a" * 64, "b" * 64]),
            ),
            ("nothing downloaded", UnhashedFiles(), self.archive([])),
        ):
            with self.subTest(label):
                result = check.run(connection)

                self.assertEqual(result.outcome, CheckOutcome.PASSED)
                self.assertEqual(result.errors, ())
                self.assertFalse(result.outcome.stops_the_load)

    def test_invalid_rows_are_reported_per_result_type(self) -> None:
        """The counts are what an operator acts on, and which result type they belong to is what says whether it matters. Is there one finding per type with invalid rows, carrying both counts, and none for a type with nothing invalid, which would only bury the ones that are wrong? The loader's own query passes over these rows, so the rest of the run is still worth loading: is this a partial finding rather than one that stops the load?"""
        result = InvalidRows().run(
            self.results(
                [
                    ("Docket", 1),
                    ("Docket", 1),
                    ("Docket", 0),
                    ("File", 0),
                    ("Opinion", 1),
                ]
            )
        )

        self.assertEqual(result.outcome, CheckOutcome.PARTIAL)
        self.assertEqual(
            [error.detail for error in result.errors],
            [
                {"result_type": "Docket", "invalid": 1, "valid": 2},
                {"result_type": "File", "invalid": 1, "valid": 0},
            ],
        )
        self.assertFalse(result.outcome.stops_the_load)
        self.assertTrue(result.outcome.is_failure)

    def test_a_question_the_database_cannot_answer_is_a_failure(self) -> None:
        """A column the check names and the database has not got is one the loader's own query names too. Is that reported as a database this loader cannot read, rather than raised out of the check?"""
        result = InvalidRows().run(
            self.open_database("CREATE TABLE results (id INTEGER)")
        )

        self.assertTrue(result.outcome.stops_the_load)
        self.assertIn("no such column", str(result.errors[0]))
        self.assertIn("query_error", result.errors[0].detail)

    def test_findings_outlive_the_connection_they_were_read_from(
        self,
    ) -> None:
        """The findings are logged, sent to Sentry and printed in the report, all after the run database has been closed. Are they read off the cursor rather than left to be read from a closed one?"""
        connection = self.results([("Docket", 0)])

        result = InvalidRows().run(connection)
        connection.close()

        self.assertEqual(
            [error.detail["invalid"] for error in result.errors],
            [1],
            "Reading a finding after the database is shut is what a report "
            "does.",
        )

    def test_every_check_runs_even_after_one_fails(self) -> None:
        """An operator fixing a run database wants everything wrong with it from one attempt. Does a failing check stop the ones after it?"""

        class Failing(PreflightCheck):
            description = "a thing that is wrong"
            query = "SELECT 1"

            def evaluate(self, rows: Any) -> CheckResult:
                return self.failed([CheckError("no good")])

        class Passing(PreflightCheck):
            description = "a thing that is fine"
            query = "SELECT 1"

            def evaluate(self, rows: Any) -> CheckResult:
                return self.passed()

        results = run_checks(
            self.results([]), (Failing(), Passing(), Failing())
        )

        self.assertEqual(
            [result.outcome for result in results],
            [CheckOutcome.FAILED, CheckOutcome.PASSED, CheckOutcome.FAILED],
        )

    def test_anything_short_of_every_file_is_a_finding(self) -> None:
        """One unhashed file is a document that will be written with no file at all, so the bar is every file rather than most of them. The column is nullable and the scraper may leave it either way: is a single file with an empty or NULL hash reported, with both counts, as a finding that leaves the rest of the run still worth loading?"""
        for label, unhashed in (("empty", ""), ("NULL", None)):
            with self.subTest(label):
                result = UnhashedFiles().run(
                    self.archive(["a" * 64, unhashed, "c" * 64])
                )

                self.assertEqual(result.outcome, CheckOutcome.PARTIAL)
                self.assertEqual(
                    result.errors[0].detail,
                    {"unhashed": 1, "hashed": 2, "total": 3},
                )
                self.assertFalse(
                    result.outcome.stops_the_load,
                    "The documents still merge, they just have no file.",
                )

    def test_a_result_says_what_was_checked(self) -> None:
        """A report names what ran as well as what it found.

        Does a result carry the check's description either way?
        """
        passing = InvalidRows().run(self.results([("Docket", 1)]))
        partial = InvalidRows().run(self.results([("Docket", 0)]))

        for result in (passing, partial):
            self.assertEqual(
                result.description, "rows the scrape marked invalid"
            )
            self.assertIn("rows the scrape marked invalid", str(result))


class LoaderPreflightTest(LoaderTestCase):
    """Tests for the checks a load puts its run database through."""

    def invalidate(self, rows: int) -> None:
        """Mark the first `rows` rows of the run database invalid."""
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "UPDATE results SET is_valid = 0 WHERE id <= ?", (rows,)
            )
            connection.commit()

    def test_unhashed_files_are_reported_before_any_merge_finds_them(
        self,
    ) -> None:
        """A merge already declines to publish a file it cannot name by content, one file at a time, deep into a run. Does the load say how much of the run is like that before it dispatches anything, and go ahead anyway?"""
        _run_database(
            self.database, [{"docket_number": "A-1"}], hashes=["a" * 64, ""]
        )

        report = self.loader().load()

        self.assertEqual(report.merged, 1, "The run is still worth loading.")
        unhashed = report.preflight[1]
        self.assertEqual(unhashed.outcome, CheckOutcome.PARTIAL)
        self.assertEqual(
            unhashed.errors[0].detail,
            {"unhashed": 1, "hashed": 1, "total": 2},
        )

    def test_the_standard_checks_run_for_every_loader(self) -> None:
        """A loader that declares no checks of its own still has a run database that can be wrong, and one that does adds its checks rather than replacing the standard ones, so it cannot drop them by forgetting to repeat them. Do the standard checks run either way, with a loader's own after them?"""

        class Extra(PreflightCheck):
            description = "something only this court can get wrong"
            query = "SELECT 1"

            def evaluate(self, rows: Any) -> CheckResult:
                return self.passed()

        _run_database(self.database, [{"docket_number": "A-1"}])
        standard = [check.description for check in STANDARD_CHECKS]

        for label, extra_checks, expected in (
            ("no checks of its own", (), standard),
            ("checks of its own", (Extra(),), [*standard, Extra.description]),
        ):
            with self.subTest(label):
                report = self.loader(
                    self.loader_class(extra_checks=extra_checks)
                ).load()

                self.assertEqual(
                    [check.description for check in report.preflight],
                    expected,
                )

    def test_invalid_rows_are_reported_without_stopping_the_load(self) -> None:
        """Rows the scrape marked invalid are dropped inside the loader's own query, so nothing downstream would ever say they were there. Are they reported, with the rest of the run still loaded?"""
        _run_database(
            self.database, [{"docket_number": f"A-{n}"} for n in range(3)]
        )
        self.invalidate(1)

        report = self.loader().load()

        self.assertEqual(
            (report.seen, report.merged),
            (3, 3),
            "The query this loader runs does not filter on is_valid, so the "
            "check reports what a filtering loader would have dropped.",
        )
        self.assertEqual(
            report.preflight[0].errors[0].detail,
            {"result_type": "TestResult", "invalid": 1, "valid": 2},
        )

    def test_a_finding_reaches_sentry_with_its_fields(self) -> None:
        """A Sentry issue is read by its fields rather than by parsing the summary back apart. Does the finding's detail ride along, under the loader's own issue for a run that will land incomplete?"""
        _run_database(self.database, [{"docket_number": "A-1"}])
        self.invalidate(1)
        self.enable_logging()

        with self.assertLogs(
            "cl.corpus_importer.state.loader", "ERROR"
        ) as logs:
            self.loader().load()

        record = logs.records[0]
        self.assertEqual(
            record.fingerprint,  # type: ignore[attr-defined]
            ["test", LoadPhase.PREFLIGHT_PARTIAL],
        )
        self.assertEqual(record.result_type, "TestResult")  # type: ignore[attr-defined]
        self.assertEqual(record.invalid, 1)  # type: ignore[attr-defined]

    def test_a_check_that_passes_says_so(self) -> None:
        """A check nobody hears about is a check nobody trusts.

        Is a clean run database reported as having been checked?
        """
        _run_database(self.database, [{"docket_number": "A-1"}])
        self.enable_logging()

        with self.assertLogs(
            "cl.corpus_importer.state.loader", "INFO"
        ) as logs:
            self.loader().load()

        self.assertIn(
            "checked rows the scrape marked invalid, found none",
            "\n".join(logs.output),
        )

    def test_a_failed_check_dispatches_nothing(self) -> None:
        """A run database the loader cannot read is worse than one it will not finish. Does a failing check stop the load before anything is sent?"""

        class Failing(PreflightCheck):
            description = "a database this loader can read"
            query = "SELECT 1"

            def evaluate(self, rows: Any) -> CheckResult:
                return self.failed(
                    [CheckError("the schema is not the one expected")]
                )

        _run_database(self.database, [{"docket_number": "A-1"}])
        self.enable_logging()

        with self.assertLogs("cl.corpus_importer.state.loader", "ERROR"):
            with self.assertRaises(PreflightFailed) as raised:
                self.loader(
                    self.loader_class(extra_checks=(Failing(),))
                ).load()

        self.assertIn(
            "the schema is not the one expected", str(raised.exception)
        )
        self.assertEqual(Docket.objects.count(), 0, "Nothing was dispatched.")
        self.assertEqual(
            self.redis.hlen(f"{self.key}:pending"),
            0,
            "And nothing was written down as if it had been.",
        )


class JKentScrapeLoaderRetryTest(LoaderTestCase):
    """Tests for putting back what a load left unfinished.

    Both retry sets are drained by the retry that reads them and refilled by
    whatever fails again, so most of these check that a set holds exactly the
    work still outstanding after a retry rather than what it held before one.
    """

    def test_only_a_row_with_no_verdict_is_held_for_retry(self) -> None:
        """A merge that never reached a verdict leaves nothing in the database to find it by again, so the row has to be written down for a retry. A rejected scrape is one to go and fix, not one to re-run, and a merged row wants nothing at all. Is only the first held?"""
        ledger = self.ledger()

        ledger.dispatched(1, "A-1")
        ledger.merged(1, MergeResult())
        ledger.dispatched(2, "A-2")
        ledger.rejected(2, MergeResult(failures={"Docket": [None]}))
        ledger.dispatched(4, "A-4")
        ledger.errored(4)

        self.assertEqual(self.merge_retry(), {"4"})

    def test_a_retry_takes_what_it_reads(self) -> None:
        """Both retry sets are drained rather than pruned as their work succeeds. Does reading either take it away, so a second retry finds nothing left to do?"""
        ledger = self.ledger()
        ledger.dispatched(1, "A-1")
        ledger.errored(1)
        ledger.retry_documents([11, 12])

        for label, read, held in (
            ("rows", lambda: ledger.rows_to_retry().rows, {1}),
            ("documents", ledger.documents_to_retry, {11, 12}),
        ):
            with self.subTest(label):
                self.assertEqual(read(), held)
                self.assertEqual(read(), set(), "The first retry took them.")

    def test_a_retry_also_takes_the_rows_celery_lost(self) -> None:
        """A row that was dispatched and never reported back is the one most worth re-running, and it is still sitting in `pending` rather than in the retry set. Is it drained alongside?"""
        ledger = self.ledger()
        ledger.dispatched(7, "A-7")
        ledger.dispatched(8, "A-8")
        ledger.errored(8)

        retry = ledger.rows_to_retry()

        self.assertEqual(retry.rows, {7, 8})
        self.assertEqual(
            (retry.lost, retry.errored),
            ({7}, {8}),
            "The row celery lost is kept apart from the row that errored, "
            "which is the one carrying a count to settle.",
        )
        self.assertEqual(
            self.redis.hlen(f"{self.key}:pending"),
            0,
            "The lost row was taken too, not left to be found twice.",
        )

    def test_counting_what_is_waiting_takes_none_of_it(self) -> None:
        """The command asks how much there is to retry before it pays for the run database. Does asking leave the work where it is?"""
        ledger = self.ledger()
        ledger.dispatched(1, "A-1")
        ledger.errored(1)
        ledger.dispatched(2, "A-2")
        ledger.retry_documents([5, 6])

        self.assertEqual(ledger.retry_counts(), (2, 2))
        self.assertEqual(
            ledger.retry_counts(),
            (2, 2),
            "Counting is not draining.",
        )

    def test_a_row_that_merges_on_retry_is_settled(self) -> None:
        """Does a retry merge only the row that failed, leaving the rows that already merged alone? The ledger's counters only ever go up and nothing prunes the retry set as rows succeed, so a row that errored and then merged would otherwise go on being counted -- and alerted on -- as a failure, or as dispatched twice, for the rest of the run's life. Is the error taken back, the dispatch left counted once, and the retry set left empty?"""
        failing = {"A-2"}
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in (1, 2, 3)],
        )
        loader_class = self.raising_loader(failing)
        with patch.object(merge_state_scrape_row, "max_retries", 0):
            self.loader(loader_class).load()
        self.assertEqual(self.merge_retry(), {"2"})
        self.assertEqual(self.ledger().totals().errored, 1)
        failing.clear()

        report = self.loader(loader_class).retry()

        self.assertEqual(
            report.seen,
            1,
            "Only the row that had no verdict was read back out of the run "
            "database.",
        )
        self.assertEqual(
            set(Docket.objects.values_list("docket_number", flat=True)),
            {"A-1", "A-2", "A-3"},
        )
        self.assertEqual(
            report.errored,
            0,
            "The row merged, so it is no longer an error against the run.",
        )
        self.assertEqual(report.merged, 3, "Every row is merged now.")
        self.assertEqual(
            report.failed, 0, "So the run has nothing left to alert on."
        )
        self.assertEqual(
            (report.dispatched, self.ledger().totals().dispatched),
            (3, 3),
            "The row the retry put back was counted when it first went.",
        )
        self.assertEqual(
            self.merge_retry(),
            set(),
            "A retry that fixed everything leaves nothing behind.",
        )

    def test_a_retry_leaves_the_run_s_totals_standing(self) -> None:
        """A retry adds to what the run already did rather than replacing it, so it must not clear the ledger the way a fresh load does. Does the moment the run began survive one?"""
        _run_database(self.database, [{"docket_number": "A-1"}])
        loader = self.loader()
        loader.load()
        started = self.ledger().started()

        loader.retry()

        self.assertEqual(self.ledger().started(), started)

    def test_holding_work_for_retry_keeps_the_run_s_anchor_alive(self) -> None:
        """Every retry set has its expiry pushed out each time something is held in it, while `started` is written once and never refreshed. A run whose retries keep it alive longer than one TTL would therefore lose the moment it began -- which its extraction re-check is scoped by -- while it still had documents held to re-check. Is the anchor kept alive alongside the work that needs it?

        Redis expires keys on a clock of its own that `time_machine` cannot
        move, so this runs against a ledger whose TTL is seconds rather than
        the usual week and waits the expiry out for real.
        """
        ledger = LoadLedger(self.key, ttl=2)
        ledger.start()

        time.sleep(1.2)
        ledger.retry_documents([11, 12])
        time.sleep(1.2)

        self.assertEqual(
            self.extraction_retry(),
            {"11", "12"},
            "Holding the documents pushed their own expiry out.",
        )
        self.assertIsNotNone(
            ledger.started(),
            "And took the anchor they will be re-checked against with them.",
        )

    def test_a_row_that_errors_again_still_counts_as_an_error(self) -> None:
        """Taking the error back as the row is re-dispatched leans on the retry's own merge to count it again if it fails again. Does a row that errored twice report as the one error it still is, rather than as two or as none, and is it written back to the retry set by the same path that recorded it first?"""
        _run_database(self.database, [{"docket_number": "A-1"}])
        loader_class = self.raising_loader({"A-1"})
        with patch.object(merge_state_scrape_row, "max_retries", 0):
            self.loader(loader_class).load()

        with patch.object(merge_state_scrape_row, "max_retries", 0):
            report = self.loader(loader_class).retry()

        self.assertEqual(report.errored, 1)
        self.assertEqual(
            self.merge_retry(), {"1"}, "And is still there to be retried."
        )

    def test_a_row_the_retry_cannot_use_is_withdrawn(self) -> None:
        """A row the retry finds it can no longer use never goes back on the queue, and has been drained from the retry set, so nothing will ever settle it. Is its error taken back, rather than alerted on by every later verification of the run?"""
        unusable: set[str] = set()

        class UnusableOnRetry(self.raising_loader({"A-1"})):  # type: ignore[misc, valid-type]
            def normalize(
                self, payload: dict[str, Any], row: sqlite3.Row
            ) -> dict[str, Any] | None:
                if payload.get("docket_number") in unusable:
                    return None
                return payload

        _run_database(self.database, [{"docket_number": "A-1"}])
        with patch.object(merge_state_scrape_row, "max_retries", 0):
            self.loader(UnusableOnRetry).load()
        unusable.add("A-1")

        report = self.loader(UnusableOnRetry).retry()

        self.assertEqual(
            report.invalid, 1, "The retry could not use the row at all."
        )
        self.assertEqual(
            (report.errored, report.dispatched),
            (0, 0),
            "So it no longer counts against the run as dispatched or errored.",
        )
        self.assertEqual(self.merge_retry(), set())

    def test_a_retry_that_cannot_find_a_row_says_so(self) -> None:
        """A row held for retry that the run database does not have means the wrong database was handed over. Is that raised rather than passed over in silence? The retry drops such a row, whether celery lost it or it errored: is it withdrawn from the run's counts with it, so later verifications do not keep alerting on a row nothing can retry?"""
        _run_database(self.database, [{"docket_number": "A-1"}])
        ledger = self.ledger()
        ledger.dispatched(98, "A-98")
        ledger.dispatched(99, "A-99")
        ledger.errored(99)
        self.enable_logging()

        with self.assertLogs(
            "cl.corpus_importer.state.loader", "ERROR"
        ) as logs:
            report = self.loader().retry()

        self.assertIn(
            "2 rows held for retry are not in run.db", logs.output[0]
        )
        self.assertEqual(
            logs.records[0].fingerprint,  # type: ignore[attr-defined]
            ["test", LoadPhase.MERGE],
        )
        self.assertEqual((report.errored, report.dispatched), (0, 0))


class JKentScrapeLoaderExtractionRetryTest(ExtractionTestCase):
    """Tests for putting back the documents extraction never came back on."""

    def verified(self, outstanding: list[int], dispatched: int = 2) -> Any:
        """Run a load's verification over a stand-in document model.

        Goes through `verify` rather than `load` because what is being tested
        is what verification records, and a merger writing rows the stand-in
        model would claim is a fixture of its own.

        Args:
            outstanding: The PKs `unextracted` reports.
            dispatched: How many documents the run says it sent, since a
                run that sent none never asks the database anything.

        Returns:
            The model.
        """
        model = self.document_model(outstanding)
        ledger = self.ledger()
        ledger.start()
        ledger.extracting(dispatched)
        self.loader(self.loader_class(document_model=model)).verify(
            LoadReport()
        )
        return model

    def test_outstanding_documents_are_held_for_retry(self) -> None:
        """A run's verification already asks which of its documents are still unextracted. Are they written down while it has them, and does a run whose documents all came back extracted leave no retry set behind at all?"""
        for outstanding, expected in (([11, 12], {"11", "12"}), ([], set())):
            with self.subTest(outstanding=outstanding):
                self.clear_run_keys()

                self.verified(outstanding)

                self.assertEqual(self.extraction_retry(), expected)
                self.assertEqual(
                    self.redis.exists(f"{self.key}:extraction_retry"),
                    int(bool(expected)),
                    "An empty set costs the ledger no key at all.",
                )

    def test_a_retry_re_checks_before_dispatching(self) -> None:
        """The set is a snapshot, and by retry time a later load or a sweep may have extracted some of it. Is the batch put back through `unextracted` rather than dispatched as it stands?"""
        model = self.document_model([11, 12])
        ledger = self.ledger()
        ledger.start()
        ledger.retry_documents([11, 12, 13])
        loader = self.loader(self.loader_class(document_model=model))

        loader.retry()

        self.assertEqual(
            set(
                model.unextracted.return_value.filter.call_args.kwargs[
                    "pk__in"
                ]
            ),
            {11, 12, 13},
            "Every held document is offered to the re-check.",
        )
        self.assertEqual(
            ledger.totals().documents,
            2,
            "Only the two the database still calls unextracted were sent.",
        )

    def test_a_retry_that_lost_its_anchor_keeps_the_documents(self) -> None:
        """Without the moment the run began there is no window to ask `unextracted` about, so the retry cannot tell which of its documents are still outstanding. Are they left in the ledger for a later sweep to find, rather than drained into a retry that cannot check them?"""
        model = self.document_model([11, 12])
        ledger = self.ledger()
        # Held for retry, but nothing ever recorded when the run began.
        ledger.retry_documents([11, 12])
        self.enable_logging()

        with self.assertLogs(
            "cl.corpus_importer.state.loader", "ERROR"
        ) as logs:
            self.loader(self.loader_class(document_model=model)).retry()

        self.assertEqual(
            self.extraction_retry(),
            {"11", "12"},
            "The documents are still there to be swept up.",
        )
        self.assertIn("no longer know when the run began", logs.output[0])
        model.unextracted.return_value.filter.assert_not_called()


class JKentScrapeLoaderCheckpointTest(LoaderTestCase):
    """Tests for the position a load records so a later one can resume it."""

    def setUp(self) -> None:
        super().setUp()
        patcher = patch(
            "cl.corpus_importer.state.loader.CHECKPOINT_EVERY", new=2
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def checkpoint(self) -> int:
        """The row the checkpoint names, or 0 for no checkpoint."""
        return get_last_parent_document_id_processed(self.key)

    def test_a_load_checkpoints_the_rows_it_dispatched(self) -> None:
        """A load that dies is resumed from its last checkpoint, so the checkpoint must never name a row the load had not reached. Does it name the last row it sent?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )
        loader = self.loader()

        # Stop the load partway, as a dying process would.
        with patch.object(
            loader, "_dispatch", side_effect=[None, None, OSError("gone")]
        ):
            with self.assertRaises(OSError):
                loader.load()

        # The checkpoint was written at the top of row 2, by which point only
        # row 1 had been dispatched. Row 2 went out after it and is dispatched
        # again on resume, which merging idempotently makes harmless -- naming
        # a row the load had not reached would not be.
        self.assertEqual(self.checkpoint(), 1)

    def test_a_checkpoint_resumes_the_rows_it_left(self) -> None:
        """A checkpoint is only worth writing if it starts the next load in the right place. Does resuming from one merge exactly the rest?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )
        log_last_document_indexed(2, self.key)

        report = self.loader(start_row=self.checkpoint()).load()

        self.assertEqual((report.seen, report.merged), (3, 3))
        self.assertEqual(
            set(Docket.objects.values_list("docket_number", flat=True)),
            {"A-2", "A-3", "A-4"},
        )

    def test_a_resumed_load_keeps_the_ledger_it_is_adding_to(self) -> None:
        """The rows a load merged before it died are in its ledger, and only that ledger says so. Does resuming add to it rather than wipe it?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(4)],
        )

        self.loader(limit=2).load()
        self.loader(start_row=2).load()

        self.assertEqual(self.ledger().totals().merged, 4)

    def test_a_load_starting_over_drops_the_last_one_s_ledger(self) -> None:
        """A run from the top is a fresh pass, and last time's outcomes say nothing about it. Are they cleared before anything is dispatched?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(3)],
        )
        self.ledger().dispatched(99, "A-99-from-a-previous-load")

        report = self.loader().load()

        self.assertEqual(report.merged, 3)
        self.assertTrue(report.accounted_for, "The stale row is gone.")

    def test_a_finished_load_clears_its_checkpoint(self) -> None:
        """A checkpoint left behind by a load that finished would send the next load of the same run database straight to the end, merging nothing. Is it dropped?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        self.loader().load()

        self.assertEqual(self.checkpoint(), 0)

    def test_a_limited_run_leaves_no_checkpoint(self) -> None:
        """A limited run stops at a row that means nothing to a full load.

        Does it neither record that position nor clear a real one?
        """
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )
        log_last_document_indexed(2, self.key)

        self.loader(limit=4).load()

        self.assertEqual(self.checkpoint(), 2, "The real load's position.")

    def test_a_load_given_no_key_keys_itself_off_the_run_database(
        self,
    ) -> None:
        """Every load is worth being able to check up on and resume, whether or not anyone named it. Does a loader built without a run key derive one from the run database, keep its ledger and verify itself out of it, and checkpoint under it?"""
        # The derived key names the run database, and the suite runs in
        # parallel against one Redis, so this run needs a name of its own.
        self.database = self.database.with_name(f"{self.id()}.db")
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )
        loader = self.loader(run_key=None)
        self.addCleanup(self.clear_run_keys, loader.run_key)

        with patch(
            "cl.corpus_importer.state.loader.log_last_document_indexed"
        ) as log:
            report = loader.load()

        key = f"state_scrape_load:test:{self.database.name}"
        self.assertEqual(loader.run_key, key)
        self.assertEqual(
            (report.dispatched, report.merged),
            (5, 5),
            "Read back out of the ledger it keyed for itself.",
        )
        self.assertEqual(Docket.objects.count(), 5)
        self.assertEqual(loader.checkpointing, key)
        self.assertEqual(
            [call.args[1] for call in log.call_args_list],
            [key, key],
            "Every checkpoint went to the key the load derived for itself.",
        )

    def test_a_load_survives_a_checkpoint_it_cannot_write(self) -> None:
        """A checkpoint is a convenience, not the load.

        Does an unreachable Redis cost the run its resume point and nothing
        more?
        """
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        with patch(
            "cl.corpus_importer.state.loader.log_last_document_indexed",
            side_effect=ConnectionError("no redis"),
        ):
            report = self.loader().load()

        self.assertEqual((report.seen, report.merged), (5, 5))


class FakeBucket:
    """Stands in for the bucket `downloaded_run_database` fetches through.

    Records what was asked for so a test can assert on it, and writes
    `contents` where the real bucket would write the object.
    """

    def __init__(
        self,
        contents: bytes = b"SQLite format 3\x00",
        error: Exception | None = None,
    ) -> None:
        self.contents = contents
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def download_file(self, key: str, destination: str) -> None:
        self.calls.append((key, destination))
        if self.error is not None:
            raise self.error
        Path(destination).write_bytes(self.contents)


class FakeStorage:
    """Stands in for the storage backend the scrape bucket is reached through, which `downloaded_run_database` asks only for its bucket."""

    def __init__(self, bucket: FakeBucket) -> None:
        self.bucket = bucket


@override_settings(
    AWS_STORAGE_BUCKET_NAME="scrapes",
    AWS_ACCESS_KEY_ID="key",
    AWS_SECRET_ACCESS_KEY="secret",
)
class RunDatabaseTest(SimpleTestCase):
    """Tests for fetching a run database out of the scrape bucket."""

    @contextmanager
    def download(self, bucket: FakeBucket, key: str) -> Iterator[Path]:
        """`downloaded_run_database` with `bucket` standing in for S3.

        The patch has to outlive the download, so this wraps the whole context
        rather than handing one back.
        """
        with patch(
            "cl.corpus_importer.state.run_db.scrape_bucket_storage",
            return_value=FakeStorage(bucket),
        ):
            with downloaded_run_database(key) as database:
                yield database

    def test_downloads_the_key_to_a_temporary_file(self) -> None:
        """Does the database arrive on local disk, under its own name, from the configured bucket?"""
        bucket = FakeBucket(contents=b"a run")

        with self.download(bucket, "nycourts_gov/2026-08-08.db") as database:
            self.assertTrue(database.exists())
            self.assertEqual(database.name, "2026-08-08.db")
            self.assertEqual(database.read_bytes(), b"a run")
            self.assertEqual(
                bucket.calls,
                [("nycourts_gov/2026-08-08.db", str(database))],
            )

    def test_takes_the_download_away_afterwards(self) -> None:
        """A run database is hundreds of megabytes.

        Is the temporary copy cleaned up when the caller is done with it, even
        when the caller fails mid-load?
        """
        for label, error in (
            ("finished", None),
            ("raised", ValueError("the load blew up")),
        ):
            with self.subTest(label):
                with (
                    self.assertRaises(ValueError) if error else nullcontext(),
                    self.download(
                        FakeBucket(), "nycourts_gov/run.db"
                    ) as database,
                ):
                    self.assertTrue(database.exists())
                    if error is not None:
                        raise error

                self.assertFalse(database.exists())
                self.assertFalse(database.parent.exists())

    def test_reports_a_key_that_cannot_be_fetched(self) -> None:
        """A missing key, or credentials that cannot read it, is all an operator can act on. Is it reported with the key named?"""
        bucket = FakeBucket(
            error=ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
        )

        with self.assertRaises(RunDatabaseUnavailable) as caught:
            with self.download(bucket, "nycourts_gov/nope.db"):
                pass

        self.assertIn(
            "s3://scrapes/nycourts_gov/nope.db", str(caught.exception)
        )

    def test_rejects_a_key_that_names_no_database(self) -> None:
        """Is a prefix handed over in place of a database refused before anything is downloaded?"""
        bucket = FakeBucket()

        with self.assertRaises(RunDatabaseUnavailable):
            with self.download(bucket, "nycourts_gov/"):
                pass

        self.assertEqual(bucket.calls, [])

    def test_the_fetch_goes_through_courtlistener_storage(self) -> None:
        """A run database is fetched with Django's storage backend rather than a client of the loader's own, so that everything a deployment configures for S3 -- a session token, a role, an endpoint -- reaches the fetch too, which a client built from the key pair alone leaves off and is refused for. Is that what the fetch reaches for?"""
        self.assertIsInstance(scrape_bucket_storage(), AWSMediaStorage)


@contextmanager
def _fake_download(key: str) -> Generator[Path]:
    """Stand in for the fetch out of the scrape bucket.

    Yields a path nothing reads: the command's argument handling is what these
    tests are about, and the loader under it is a mock.
    """
    yield Path("/nonexistent") / key


class LoadStateScrapeCommandTest(SimpleTestCase):
    """Tests for how the load command reads its arguments."""

    CHECKPOINT = 120

    def setUp(self) -> None:
        self.loader = Mock()
        self.loader.return_value.load.return_value = LoadReport()
        self.output = StringIO()
        self.errors = StringIO()
        for target, replacement in (
            ("downloaded_run_database", _fake_download),
            (
                "get_last_parent_document_id_processed",
                Mock(return_value=self.CHECKPOINT),
            ),
        ):
            patcher = patch(
                "cl.corpus_importer.management.commands."
                f"load_state_scrape.{target}",
                replacement,
            )
            patcher.start()
            self.addCleanup(patcher.stop)
        registry = patch.dict(LOADERS, {"nycoa": self.loader}, clear=True)
        registry.start()
        self.addCleanup(registry.stop)

    def load(self, *arguments: str) -> None:
        """Run the command over a stand-in run database."""
        call_command(
            "load_state_scrape",
            "nycoa",
            "nycourts_gov/2026-08-08.db",
            *arguments,
            stdout=self.output,
            stderr=self.errors,
        )

    def started_at(self) -> int:
        """The row the load the command built was told to start from."""
        return self.loader.call_args.kwargs["start_row"]

    def test_contradictory_flags_are_refused(self) -> None:
        """Some flags each ask for something the other rules out: a retry works from the rows the ledger is holding, so anything that says which rows to work on instead is asking for something a retry cannot do; --start-row and --auto-resume each say to start somewhere the other says not to; and --skip-load with --skip-verification skips the whole command. Is the operator made to pick, with the flags that clash named, rather than one of them being quietly ignored or guessed at?"""
        for arguments, named in (
            (("--retry", "--start-row", "5"), ("--start-row",)),
            (("--retry", "--auto-resume"), ("--auto-resume",)),
            (("--retry", "--skip-load"), ("--skip-load",)),
            (("--retry", "--limit", "10"), ("--limit",)),
            (
                ("--auto-resume", "--start-row", "5"),
                # Quotes back the value that has to go.
                ("--start-row 5", "--auto-resume"),
            ),
            (
                ("--skip-load", "--skip-verification"),
                ("--skip-load", "--skip-verification"),
            ),
        ):
            with self.subTest(" ".join(arguments)):
                with self.assertRaises(CommandError) as raised:
                    self.load(*arguments)

                for flag in named:
                    self.assertIn(flag, str(raised.exception))
                self.loader.assert_not_called()

    def test_a_retry_fetches_the_run_database_only_for_dockets(self) -> None:
        """Run databases run to hundreds of megabytes, and a retry only wants one for a docket's payload, which has to be read back out of it because a docket held for retry is named by position. Is the fetch made when the ledger is holding dockets, and skipped -- with the loader built on the bucket path -- when it is holding only documents? Either way, is the retry loader built without the `start_row` and `limit` that would each narrow what it re-dispatches behind the ledger's back?"""
        key = "nycourts_gov/2026-08-08.db"
        for label, counts, built_on in (
            ("dockets held", (3, 0), Path("/nonexistent") / key),
            ("only documents held", (0, 12), key),
        ):
            with self.subTest(label):
                self.loader.reset_mock()
                self.loader.return_value.ledger.retry_counts.return_value = (
                    counts
                )
                self.loader.return_value.retry.return_value = LoadReport()

                self.load("--retry")

                self.loader.return_value.retry.assert_called_once_with()
                self.assertEqual(self.loader.call_args.args[0], built_on)
                self.assertNotIn("start_row", self.loader.call_args.kwargs)
                self.assertNotIn("limit", self.loader.call_args.kwargs)

    def test_a_run_database_that_fails_its_checks_is_reported(self) -> None:
        """A load that will not run is an operator's problem to act on, and a traceback buries what to act on. Is a failed check reported the way an unfetchable database is?"""
        self.loader.return_value.load.side_effect = PreflightFailed(
            "run.db failed 1 of 2 checks, so nothing was dispatched"
        )

        with self.assertRaises(CommandError) as raised:
            self.load()

        self.assertIn("nothing was dispatched", str(raised.exception))

    def test_the_report_names_what_was_checked(self) -> None:
        """A check that found nothing is still worth saying ran.

        Does the report name every check, and send the ones with findings to
        stderr?
        """
        self.loader.return_value.load.return_value = LoadReport(
            preflight=(
                CheckResult("a clean thing", CheckOutcome.PASSED),
                CheckResult(
                    "a partial thing",
                    CheckOutcome.PARTIAL,
                    (CheckError("2 rows are marked invalid"),),
                ),
            )
        )

        self.load()

        self.assertIn("Checked PASSED a clean thing", self.output.getvalue())
        self.assertIn(
            "Checked PARTIAL a partial thing: 2 rows are marked invalid",
            self.errors.getvalue(),
        )

    def test_both_queues_are_throttled_by_default(self) -> None:
        """An unthrottled load puts a whole run's dockets in the broker at once, and every other import command paces itself out of the box. Do the queues start throttled here too, at the same figure?"""
        self.load()

        kwargs = self.loader.call_args.kwargs
        self.assertEqual(kwargs["ingest_throttle"], DEFAULT_THROTTLE)
        self.assertEqual(kwargs["extraction_throttle"], DEFAULT_THROTTLE)
        self.assertEqual(
            DEFAULT_THROTTLE,
            5,
            "The figure --throttle-min-items defaults to for SCOTUS, Texas "
            "and Florida.",
        )

    def test_throttling_can_still_be_turned_off(self) -> None:
        """A backfill wants throughput over a clear queue.

        Is zero honoured rather than falling back to the default?
        """
        self.load("--ingest-throttle", "0")

        self.assertEqual(self.loader.call_args.kwargs["ingest_throttle"], 0)

    def test_the_load_starts_where_it_was_told_to(self) -> None:
        """Does --auto-resume on its own pick the load up where the last one left off, and --start-row on its own start it where it says? --start-row defaults to zero, which asks for nothing: is a zero left out of the objection to combining the two?"""
        for arguments, expected in (
            (("--auto-resume",), self.CHECKPOINT),
            (("--start-row", "5"), 5),
            (("--auto-resume", "--start-row", "0"), self.CHECKPOINT),
        ):
            with self.subTest(" ".join(arguments)):
                self.load(*arguments)

                self.assertEqual(self.started_at(), expected)

    def test_dropped_dockets_are_named(self) -> None:
        """Rows celery lost are the whole reason the load verifies itself.

        Does the command say which ones, rather than leaving them in the log?
        """
        self.loader.return_value.load.return_value = LoadReport(
            seen=2,
            dispatched=2,
            merged=1,
            missing_count=1,
            missing={7: "APL-2024-00177"},
        )

        self.load()

        # On stderr, so a scheduled run's mail catches it without the counts
        # around it.
        errors = self.errors.getvalue()
        self.assertIn("never reported back", errors)
        self.assertIn("row 7: APL-2024-00177", errors)
        self.assertNotIn("never reported back", self.output.getvalue())

    def test_skip_load_checks_a_stored_ledger_without_a_download(
        self,
    ) -> None:
        """A run that gave up while its queues were still moving has to be settleable later. Does --skip-load do that from the ledger alone, without fetching a run database that can run to hundreds of megabytes? Printing `0 invalid` for a run whose rows were never opened reads as "no bad rows" when it means "did not look": are those counts left out, and said to be left out?"""
        self.loader.return_value.verify_only.return_value = LoadReport(
            rows_read=False, dispatched=9, merged=8, rejected=1
        )

        with patch(
            "cl.corpus_importer.management.commands."
            "load_state_scrape.downloaded_run_database"
        ) as download:
            self.load("--skip-load")

        download.assert_not_called()
        self.loader.return_value.verify_only.assert_called_once_with()
        self.loader.return_value.load.assert_not_called()
        written = self.output.getvalue()
        summary = written.splitlines()[0]
        self.assertEqual(
            summary, "9 dispatched, 8 merged, 1 rejected, 0 errored, 0 missing"
        )
        self.assertNotIn("seen", summary)
        self.assertNotIn("invalid", summary)
        self.assertIn("no run database was opened", written)

    def test_counts_line_up_under_one_another(self) -> None:
        """A run touching several models is read down a column.

        Are the model names and their counts padded to a common width?
        """
        self.loader.return_value.load.return_value = LoadReport(
            seen=2,
            dispatched=2,
            merged=2,
            creates={"Docket": 2, "OpinionCluster": 11},
            updates={"Docket": 105},
        )

        self.load()

        written = self.output.getvalue().splitlines()
        self.assertEqual(
            written[1:],
            [
                "  Created Docket            2",
                "  Created OpinionCluster   11",
                "  Updated Docket          105",
            ],
        )

    def test_only_a_stalled_wait_is_reported_as_lost_work(self) -> None:
        """A queue that stopped moving is a finding, and the output should say so rather than hedging; giving up on a queue that was still coming down is not. Does the output name the timeout as the reason it stopped watching, and point only then at the flag that settles it?"""
        for merge_wait, reported, points_at_skip_load in (
            (
                WaitOutcome.TIMED_OUT,
                "never reported back yet -- timed out",
                True,
            ),
            (
                WaitOutcome.STALLED,
                "never reported back -- queue stalled",
                False,
            ),
        ):
            with self.subTest(merge_wait=merge_wait):
                self.errors = StringIO()
                self.loader.return_value.load.return_value = LoadReport(
                    seen=9,
                    dispatched=9,
                    merged=4,
                    missing_count=5,
                    missing={5: "APL-2024-00177"},
                    merge_wait=merge_wait,
                )

                self.load()

                errors = self.errors.getvalue()
                self.assertIn(reported, errors)
                self.assertEqual("--skip-load" in errors, points_at_skip_load)

    def test_the_files_a_run_moved_are_written_out(self) -> None:
        """A load that publishes files does work no row count shows.

        Is what became of them written where the model counts are?
        """
        self.loader.return_value.load.return_value = LoadReport(
            seen=2, dispatched=2, merged=2, files=FileTally(moved=17)
        )

        self.load()

        self.assertIn(
            "Files: 17 moved, 0 not found, 0 could not be moved",
            self.output.getvalue(),
        )
        self.assertEqual(
            self.errors.getvalue(),
            "",
            "Every file landed, so there is nothing to warn about.",
        )

    def test_files_that_never_reached_the_bucket_are_warned_about(
        self,
    ) -> None:
        """A document pointing at nothing serves nothing and extracts nothing, which no other count in the report shows. Does the warning say how many re-running the load would mend, and how many it would not?"""
        self.loader.return_value.load.return_value = LoadReport(
            seen=2,
            dispatched=2,
            merged=2,
            files=FileTally(moved=5, missing=2, failed=3),
        )

        self.load()

        errors = self.errors.getvalue()
        self.assertIn("5 files never reached the public bucket", errors)
        self.assertIn("the 3 the bucket refused", errors)
        self.assertIn("the 2 it could not find", errors)

    def test_a_run_that_moved_no_files_says_nothing_about_them(self) -> None:
        """Most loaders publish nothing at all.

        Is the files line held back rather than printing three zeroes on every
        load?
        """
        self.loader.return_value.load.return_value = LoadReport(
            seen=2, dispatched=2, merged=2
        )

        self.load()

        self.assertNotIn("Files:", self.output.getvalue())

    def test_an_unverified_load_does_not_claim_a_clean_run(self) -> None:
        """A load that skipped verification knows only what it dispatched.

        Does it say so instead of reporting nothing merged?
        """
        self.loader.return_value.load.return_value = LoadReport(
            seen=2, dispatched=2
        )

        self.load("--skip-verification")

        self.assertIn("Verification was skipped", self.errors.getvalue())
