"""Tests for the Florida ACIS poller management command."""

import json
from collections.abc import AsyncGenerator, Mapping
from datetime import UTC, date, datetime, timedelta
from unittest import mock
from uuid import uuid4

import time_machine
from asgiref.sync import async_to_sync
from django.core.management import call_command
from juriscraper.state.florida.cases import FloridaCase
from juriscraper.state.florida.common import FloridaPaginatedResults
from juriscraper.state.florida.courts import FloridaCourt, FloridaCourtID
from juriscraper.state.florida.scraper import CourtMetadata, PaginationFailed

from cl.corpus_importer.state.florida.factories import FloridaCaseFactory
from cl.lib.redis_utils import get_redis_interface
from cl.scrapers.management.commands import fl_poller as fl_cmd_module
from cl.scrapers.management.commands.fl_poller import (
    DE_DOC_ENDPOINT,
    DOCKET_ENDPOINT,
    Command,
    FloridaDocumentPollParser,
    FloridaUpdate,
)
from cl.scrapers.management.utils import ScraperCheckpointTracker
from cl.tests.cases import SimpleTestCase

DATE_PARAM_FMT = "%Y-%m-%dT%H:%M:%S.000Z"
FROZEN_NOW = datetime(2026, 8, 20, 12, tzinfo=UTC)
START = datetime(2026, 8, 19, 12, tzinfo=UTC)

# Trackers with test-only keys so tests can't collide with a real poller's
# checkpoint in Redis.
POLL_TRACKER = ScraperCheckpointTracker("test_flacis_poll")
CMD_TRACKER = ScraperCheckpointTracker("test_flacis_cmd")


class StopPolling(Exception):
    """Raised by the mocked inter-cycle sleep to break poll's infinite loop."""


def make_court_metadata(external_id: int) -> CourtMetadata:
    """Build a CourtMetadata carrying only the fields the poller reads (the
    court's external identifier and resource UUID)."""
    return CourtMetadata(
        court=FloridaCourt.model_construct(
            external_identifier=external_id, resource_id=uuid4()
        ),
        case_party_subtypes=[],
        case_categories=[],
        docket_entry_subtypes=[],
    )


def make_update(court_external_id: int = 2) -> FloridaUpdate:
    """Build a FloridaUpdate for a fresh case UUID in the given court."""
    return FloridaUpdate.model_construct(
        case_uuid=uuid4(), court_external_id=court_external_id
    )


def make_page(
    updates: list[FloridaUpdate],
) -> FloridaPaginatedResults[FloridaUpdate]:
    """Wrap updates in one page of paginated results."""
    return FloridaPaginatedResults[FloridaUpdate].model_construct(
        results=updates
    )


class FakeFloridaScraper:
    """In-memory stand-in for FloridaScraper.

    Yields pre-seeded pages per endpoint and returns pre-seeded
    ``fetch_case_data`` results keyed by case UUID string, recording every
    request so tests can assert on query parameters. A ``case_results`` value
    may be a ``(case, errors)`` tuple, an Exception to return, or a callable
    to invoke (letting tests simulate a raising fetch).
    """

    def __init__(
        self,
        courts: dict[FloridaCourtID, CourtMetadata],
        pages: (
            dict[
                str,
                list[
                    FloridaPaginatedResults[FloridaUpdate] | PaginationFailed
                ],
            ]
            | None
        ) = None,
        case_results: dict[str, object] | None = None,
    ) -> None:
        self._courts = courts
        self.pages = pages or {}
        self.case_results = case_results or {}
        self.page_requests: list[tuple[str, dict]] = []
        self.case_requests: list[tuple[str, str]] = []

    @property
    def courts(self):
        """Mirror FloridaScraper.courts: an awaitable resolving to the dict."""

        async def get_courts() -> dict[FloridaCourtID, CourtMetadata]:
            return self._courts

        return get_courts()

    async def _enumerate_pages(
        self, endpoint: str, parser, params: Mapping | None = None
    ) -> AsyncGenerator[
        FloridaPaginatedResults[FloridaUpdate] | PaginationFailed
    ]:
        self.page_requests.append((endpoint, dict(params or {})))
        for page in self.pages.get(endpoint, []):
            yield page

    async def fetch_case_data(
        self, case_uuid: str, court_id: str
    ) -> tuple[FloridaCase, list[PaginationFailed]] | Exception:
        self.case_requests.append((case_uuid, court_id))
        result = self.case_results[case_uuid]
        if callable(result):
            result = result()
        return result


class FloridaDocumentPollParserTest(SimpleTestCase):
    """Unit test for the poll-endpoint results parser."""

    def test_parse_full_extracts_case_identifiers(self):
        """The parser must pull the case UUID and court external ID out of
        each result's caseHeader."""
        case_uuid = uuid4()
        payload = json.dumps(
            {
                "_embedded": {
                    "results": [
                        {
                            "caseHeader": {
                                "caseInstanceUUID": str(case_uuid),
                                "courtID": 2,
                            }
                        }
                    ]
                },
                "page": {
                    "size": 50,
                    "totalElements": 1,
                    "totalPages": 1,
                    "number": 0,
                },
            }
        )

        parsed = FloridaDocumentPollParser(court_id="fl").parse_full(payload)

        self.assertEqual(
            parsed.results,
            [
                FloridaUpdate.model_construct(
                    case_uuid=case_uuid, court_external_id=2
                )
            ],
        )


@time_machine.travel(FROZEN_NOW, tick=False)
@mock.patch.object(Command, "checkpoint_tracker", POLL_TRACKER)
class FlPollerPollTest(SimpleTestCase):
    """Coverage for Command.poll against a fake scraper.

    The checkpoint tracker is patched so tests operate on an isolated Redis
    key and cannot collide with a real poller's checkpoint.
    """

    def setUp(self):
        super().setUp()
        self.r = get_redis_interface("CACHE")
        self.r.delete(POLL_TRACKER.autoresume_key)
        self.court_metadata = make_court_metadata(2)
        self.courts = {FloridaCourtID.FIRST_COA: self.court_metadata}
        self.throttle = mock.MagicMock()
        self.mock_save = mock.patch.object(
            fl_cmd_module, "save_case_to_s3"
        ).start()
        self.mock_save.return_value = "test"
        self.mock_ingest = mock.patch.object(
            fl_cmd_module, "fl_ingest_docket_task"
        ).start()
        self.addCleanup(mock.patch.stopall)

    def tearDown(self):
        self.r.delete(POLL_TRACKER.autoresume_key)
        super().tearDown()

    def run_poll(
        self,
        scraper: FakeFloridaScraper,
        *,
        iterations: int = 1,
        download_attachments: bool = True,
    ) -> None:
        """Run poll for the given number of cycles. The inter-cycle sleep is
        mocked to raise after the last cycle since the loop has no other
        exit."""
        sleep = mock.AsyncMock(
            side_effect=[None] * (iterations - 1) + [StopPolling()]
        )
        with (
            mock.patch.object(fl_cmd_module.asyncio, "sleep", sleep),
            self.assertRaises(StopPolling),
        ):
            async_to_sync(Command().poll)(
                self.throttle,
                scraper,
                [FloridaCourtID.FIRST_COA],
                0,
                START,
                "test_queue",
                download_attachments,
            )

    def test_new_cases_are_archived_and_dispatched(self):
        """Every discovered case must be archived to S3, handed to the Celery
        ingestion task on the requested queue, and advance the checkpoint."""
        case_a = FloridaCaseFactory()
        case_b = FloridaCaseFactory()
        update_a = make_update()
        update_b = make_update()
        scraper = FakeFloridaScraper(
            self.courts,
            pages={DOCKET_ENDPOINT: [make_page([update_a, update_b])]},
            case_results={
                str(update_a.case_uuid): (case_a, []),
                str(update_b.case_uuid): (case_b, []),
            },
        )

        self.run_poll(scraper)

        self.assertEqual(
            [c.args for c in self.mock_save.call_args_list],
            [
                (
                    FloridaCourtID.FIRST_COA,
                    case_a,
                    self.throttle,
                    "test_queue",
                ),
                (
                    FloridaCourtID.FIRST_COA,
                    case_b,
                    self.throttle,
                    "test_queue",
                ),
            ],
        )
        self.assertEqual(
            [c.args for c in self.mock_ingest.si.call_args_list],
            [
                (
                    (
                        case_a,
                        "",
                        self.mock_save.return_value,
                    ),
                    True,
                ),
                (
                    (
                        case_b,
                        "",
                        self.mock_save.return_value,
                    ),
                    True,
                ),
            ],
        )
        self.mock_ingest.si.return_value.set.assert_called_with(
            queue="test_queue"
        )
        self.assertEqual(
            self.mock_ingest.si.return_value.set.return_value.apply_async.call_count,
            2,
        )
        self.assertEqual(POLL_TRACKER.get(), case_b.date_filed)

    def test_duplicate_updates_are_ingested_once(self):
        """An update surfaced by both the docket-entry and new-case endpoints
        must be fetched and ingested only once per cycle."""
        case = FloridaCaseFactory()
        update = make_update()
        scraper = FakeFloridaScraper(
            self.courts,
            pages={
                DE_DOC_ENDPOINT: [make_page([update])],
                DOCKET_ENDPOINT: [make_page([update])],
            },
            case_results={str(update.case_uuid): (case, [])},
        )

        self.run_poll(scraper)

        self.assertEqual(
            scraper.case_requests,
            [(str(update.case_uuid), FloridaCourtID.FIRST_COA.value)],
        )
        self.mock_ingest.si.assert_called_once_with(
            (
                case,
                "",
                self.mock_save.return_value,
            ),
            True,
        )

    def test_fetch_failures_are_skipped(self):
        """A fetch that raises, returns an Exception, or returns errors must
        be skipped without aborting the cycle; later updates still ingest."""
        raising = make_update()
        returns_exc = make_update()
        has_errors = make_update()
        good = make_update()
        good_case = FloridaCaseFactory()

        def boom() -> tuple[FloridaCase, list[PaginationFailed]]:
            raise RuntimeError("boom")

        scraper = FakeFloridaScraper(
            self.courts,
            pages={
                DOCKET_ENDPOINT: [
                    make_page([raising, returns_exc, has_errors, good])
                ]
            },
            case_results={
                str(raising.case_uuid): boom,
                str(returns_exc.case_uuid): ValueError("bad court"),
                str(has_errors.case_uuid): (
                    FloridaCaseFactory(),
                    [PaginationFailed(0, "network", DOCKET_ENDPOINT, {})],
                ),
                str(good.case_uuid): (good_case, []),
            },
        )

        self.run_poll(scraper)

        self.mock_save.assert_called_once()
        self.mock_ingest.si.assert_called_once_with(
            (
                good_case,
                "",
                self.mock_save.return_value,
            ),
            True,
        )

    def test_pagination_failure_is_logged_and_polling_continues(self):
        """A PaginationFailed page must be logged as an error while updates
        from surviving pages are still processed."""
        case = FloridaCaseFactory()
        update = make_update()
        scraper = FakeFloridaScraper(
            self.courts,
            pages={
                DOCKET_ENDPOINT: [
                    PaginationFailed(0, "network", DOCKET_ENDPOINT, {}),
                    make_page([update]),
                ]
            },
            case_results={str(update.case_uuid): (case, [])},
        )

        with mock.patch.object(fl_cmd_module.logger, "error") as mock_error:
            self.run_poll(scraper)

        self.assertTrue(mock_error.called)
        self.mock_ingest.si.assert_called_once_with(
            (
                case,
                "",
                self.mock_save.return_value,
            ),
            True,
        )

    def test_poll_queries_both_endpoints_and_advances_window(self):
        """Each cycle must query both poll endpoints for the court, starting
        from the provided start date and, on later cycles, from one minute
        before the previous cycle's poll time."""
        scraper = FakeFloridaScraper(self.courts)

        self.run_poll(scraper, iterations=2)

        de_doc_requests = [
            p for e, p in scraper.page_requests if e == DE_DOC_ENDPOINT
        ]
        docket_requests = [
            p for e, p in scraper.page_requests if e == DOCKET_ENDPOINT
        ]
        self.assertEqual(len(de_doc_requests), 2)
        self.assertEqual(len(docket_requests), 2)

        court_uuid = str(self.court_metadata.court.resource_id)
        self.assertEqual(docket_requests[0]["caseHeader.courtID"], court_uuid)
        self.assertEqual(de_doc_requests[0]["caseHeader.courtID"], court_uuid)

        start_param = START.strftime(DATE_PARAM_FMT)
        self.assertEqual(
            docket_requests[0]["caseHeader.filedDateFrom"], start_param
        )
        self.assertEqual(
            de_doc_requests[0]["docketEntryHeader.docketEntryFiledDateFrom"],
            start_param,
        )
        overlap_param = (FROZEN_NOW - timedelta(minutes=1)).strftime(
            DATE_PARAM_FMT
        )
        self.assertEqual(
            docket_requests[1]["caseHeader.filedDateFrom"], overlap_param
        )
        self.assertEqual(
            de_doc_requests[1]["docketEntryHeader.docketEntryFiledDateFrom"],
            overlap_param,
        )

    def test_download_attachments_flag_reaches_ingestion_task(self):
        """The download_attachments flag must be forwarded to the ingestion
        task."""
        case = FloridaCaseFactory()
        update = make_update()
        scraper = FakeFloridaScraper(
            self.courts,
            pages={DOCKET_ENDPOINT: [make_page([update])]},
            case_results={str(update.case_uuid): (case, [])},
        )

        self.run_poll(scraper, download_attachments=False)

        self.mock_ingest.si.assert_called_once_with(
            (
                case,
                "",
                self.mock_save.return_value,
            ),
            False,
        )


@time_machine.travel(FROZEN_NOW, tick=False)
@mock.patch.object(Command, "checkpoint_tracker", CMD_TRACKER)
@mock.patch.object(Command, "poll", new_callable=mock.AsyncMock)
class FlPollerCommandTest(SimpleTestCase):
    """Coverage for handle(): court parsing, start-date resolution, and
    checkpoint auto-resume. poll itself is mocked out."""

    def setUp(self):
        super().setUp()
        self.r = get_redis_interface("CACHE")
        self.r.delete(CMD_TRACKER.autoresume_key)

    def tearDown(self):
        self.r.delete(CMD_TRACKER.autoresume_key)
        super().tearDown()

    def test_start_defaults_to_backfill_window(self, mock_poll):
        """Without auto-resume, polling must start --case-backfill-days ago
        and only the requested courts must be polled."""
        call_command("fl_poller", courts="fla", case_backfill_days=3)

        (
            _throttle,
            _scraper,
            court_ids,
            polling_delay,
            start,
            queue,
            download_attachments,
        ) = mock_poll.call_args.args
        self.assertEqual(court_ids, [FloridaCourtID.SUPREME_COURT])
        self.assertEqual(start, FROZEN_NOW - timedelta(days=3))
        self.assertEqual(queue, "batch1")
        self.assertTrue(download_attachments)

    def test_auto_resume_starts_from_checkpoint(self, mock_poll):
        """With --auto-resume and a stored checkpoint, polling must start at
        the checkpoint date."""
        CMD_TRACKER.set(date(2026, 8, 1))

        call_command("fl_poller", auto_resume=True)

        self.assertEqual(mock_poll.call_args.args[4], datetime(2026, 8, 1))

    def test_auto_resume_without_checkpoint_falls_back(self, mock_poll):
        """With --auto-resume but no stored checkpoint, the command must warn
        and fall back to the --case-backfill-days window."""
        with mock.patch.object(fl_cmd_module.logger, "warning") as mock_warn:
            call_command("fl_poller", auto_resume=True, case_backfill_days=2)

        mock_warn.assert_any_call(
            "No checkpoint found. Falling back to --case-backfill-days=%d",
            2,
        )
        self.assertEqual(
            mock_poll.call_args.args[4], FROZEN_NOW - timedelta(days=2)
        )

    def test_no_download_attachments_option(self, mock_poll):
        """--no-download-attachments must disable attachment downloads in the
        dispatched ingestion tasks."""
        call_command("fl_poller", no_download_attachments=True)

        self.assertFalse(mock_poll.call_args.args[6])
