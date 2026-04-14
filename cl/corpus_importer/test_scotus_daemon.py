from datetime import date, datetime
from http import HTTPStatus
from unittest import mock

import time_machine
from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from requests.exceptions import HTTPError

from cl.corpus_importer.management.commands import (
    probe_scotus_dockets_daemon as scotus_cmd_module,
)
from cl.corpus_importer.scotus_daemon_utils import (
    current_scotus_term_year,
    format_docket_number,
    next_term_starts_probing,
)
from cl.lib.redis_utils import get_redis_interface
from cl.search.factories import CourtFactory
from cl.search.models import Docket, ScotusDocketMetadata
from cl.tests.cases import TestCase
from cl.tests.fakes import FakeSCOTUSDocketReport

SCOTUS_DAEMON_MODULE = (
    "cl.corpus_importer.management.commands.probe_scotus_dockets_daemon"
)


class ScotusDaemonUtilsTest(SimpleTestCase):
    """Unit tests for the pure helpers in scotus_daemon_utils."""

    def test_current_term_year_before_july(self):
        self.assertEqual(current_scotus_term_year(date(2026, 1, 5)), 25)
        self.assertEqual(current_scotus_term_year(date(2026, 6, 30)), 25)

    def test_current_term_year_on_or_after_july(self):
        self.assertEqual(current_scotus_term_year(date(2025, 7, 1)), 25)
        self.assertEqual(current_scotus_term_year(date(2025, 12, 31)), 25)
        self.assertEqual(current_scotus_term_year(date(2026, 7, 2)), 26)

    def test_next_term_probing_window(self):
        self.assertFalse(next_term_starts_probing(date(2026, 6, 30)))
        self.assertTrue(next_term_starts_probing(date(2026, 7, 1)))
        self.assertTrue(next_term_starts_probing(date(2026, 7, 31)))
        self.assertFalse(next_term_starts_probing(date(2026, 8, 1)))

    def test_format_docket_number(self):
        self.assertEqual(format_docket_number(25, 150), "25-150")
        self.assertEqual(format_docket_number(3, 7), "03-7")

    def test_format_docket_number_applications(self):
        self.assertEqual(
            format_docket_number(24, 1088, "applications"), "24A1088"
        )
        self.assertEqual(format_docket_number(25, 1, "applications"), "25A1")


@mock.patch(
    f"{SCOTUS_DAEMON_MODULE}.HIGHEST_SCOTUS_KNOWN_SERIAL",
    "test:daemon:highest_known",
)
@mock.patch(
    f"{SCOTUS_DAEMON_MODULE}.scotus_empty_probe_attempts_key",
    return_value="test:daemon:empty_probes",
)
@mock.patch(
    f"{SCOTUS_DAEMON_MODULE}.scotus_blocked_attempts_key",
    return_value="test:daemon:blocked",
)
@mock.patch(
    f"{SCOTUS_DAEMON_MODULE}.scotus_court_wait_key",
    return_value="test:daemon:court_wait",
)
class ScotusDaemonTest(SimpleTestCase):
    """Coverage for the synchronous SCOTUS probing daemon.

    Exercises both the probe-iteration function and the management command
    against real Redis. Redis key functions are mocked so each test class
    operates on isolated keys and cannot collide with other classes.
    """

    HIGHEST_KNOWN_KEY = "test:daemon:highest_known"
    COURT_WAIT_KEY = "test:daemon:court_wait"
    BLOCKED_KEY = "test:daemon:blocked"
    EMPTY_KEY = "test:daemon:empty_probes"
    REDIS_KEYS = (
        HIGHEST_KNOWN_KEY,
        COURT_WAIT_KEY,
        BLOCKED_KEY,
        EMPTY_KEY,
    )

    def setUp(self):
        super().setUp()
        self.r = get_redis_interface("CACHE")
        for key in self.REDIS_KEYS:
            self.r.delete(key)

    def tearDown(self):
        for key in self.REDIS_KEYS:
            self.r.delete(key)
        super().tearDown()

    def _seed_current_term(
        self, term: int, low: int = 0, high: int = 5000, applications: int = 0
    ):
        self.r.hset(self.HIGHEST_KNOWN_KEY, f"low:{term:02d}", low)
        self.r.hset(self.HIGHEST_KNOWN_KEY, f"high:{term:02d}", high)
        self.r.hset(
            self.HIGHEST_KNOWN_KEY, f"applications:{term:02d}", applications
        )

    # ------------------------------------------------------------------ #
    # run_scotus_probe_iteration
    # ------------------------------------------------------------------ #

    def test_missing_seed_aborts(self, *_mocks):
        """If Redis has no seeds, the iteration logs error and does NOT hit
        HTTP."""
        with (
            mock.patch.object(
                scotus_cmd_module, "fetch_scotus_docket_json"
            ) as mock_fetch,
            mock.patch.object(scotus_cmd_module.logger, "error") as mock_error,
            time_machine.travel(datetime(2026, 3, 15, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)
        mock_fetch.assert_not_called()
        self.assertTrue(mock_error.called)

    def test_probe_finds_new_cases_and_backfills_inline(self, *_mocks):
        """Probe must advance the watermark, ingest each direct hit, and
        synchronously backfill serials skipped by the geometric probe.
        Every hit (probe + backfill) must be archived to S3 and handed to
        the Celery ingestion task."""
        self._seed_current_term(25, low=99, high=20000)

        valid_low = {f"25-{n}" for n in range(100, 116)}

        def fake_fetch(docket_number):
            if docket_number in valid_low:
                return (
                    f'{{"docket_number":"{docket_number}"}}'
                ), HTTPStatus.OK
            return None, HTTPStatus.NOT_FOUND

        with (
            mock.patch.object(
                scotus_cmd_module,
                "fetch_scotus_docket_json",
                side_effect=fake_fetch,
            ),
            mock.patch.object(
                scotus_cmd_module, "save_scotus_raw_to_s3"
            ) as mock_save,
            mock.patch.object(
                scotus_cmd_module,
                "SCOTUSDocketReport",
                new=FakeSCOTUSDocketReport,
            ),
            mock.patch.object(
                scotus_cmd_module, "process_scotus_docket"
            ) as mock_proc,
            mock.patch.object(scotus_cmd_module.time, "sleep"),
            time_machine.travel(datetime(2026, 3, 15, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)

        self.assertEqual(self.r.hget(self.HIGHEST_KNOWN_KEY, "low:25"), "115")
        self.assertEqual(mock_save.call_count, 16)
        self.assertEqual(mock_proc.delay.call_count, 16)
        enqueued_docket_numbers = {
            call_args.args[0]["docket_number"]
            for call_args in mock_proc.delay.call_args_list
        }
        self.assertEqual(enqueued_docket_numbers, valid_low)

    def test_http_error_triggers_backoff(self, *_mocks):
        """An HTTPError during probing must set court_wait with TTL."""
        self._seed_current_term(25, low=100, high=20000)

        def raising_fetch(_):
            raise HTTPError("403")

        with (
            mock.patch.object(
                scotus_cmd_module,
                "fetch_scotus_docket_json",
                side_effect=raising_fetch,
            ),
            time_machine.travel(datetime(2026, 3, 15, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)

        self.assertEqual(self.r.get(self.BLOCKED_KEY), "1")
        self.assertTrue(self.r.exists(self.COURT_WAIT_KEY))

    def test_empty_probe_alert_on_persistent_silence(self, *_mocks):
        """Enough empty probes must raise a logger.error and set a 1h wait."""
        self._seed_current_term(25, low=100, high=20000)
        attempts_needed = max(
            1,
            int(
                settings.SCOTUS_EMPTY_PROBES_LIMIT_HOURS
                * 3600
                / max(1, settings.SCOTUS_PROBE_WAIT)
            ),
        )
        self.r.set(self.EMPTY_KEY, attempts_needed - 1)

        with (
            mock.patch.object(
                scotus_cmd_module,
                "fetch_scotus_docket_json",
                return_value=(None, HTTPStatus.NOT_FOUND),
            ),
            mock.patch.object(scotus_cmd_module.logger, "error") as mock_error,
            time_machine.travel(datetime(2026, 3, 15, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)

        self.assertTrue(mock_error.called)
        self.assertEqual(self.r.get(self.COURT_WAIT_KEY), "3600")

    def test_term_rollover_persists_new_term_watermark(self, *_mocks):
        """During the July-onward rollover window, a hit in the new term
        must persist ``low:26``."""
        self._seed_current_term(25, low=3000, high=20000)

        def fake_fetch(docket_number):
            if docket_number == "26-1":
                return '{"docket_number":"26-1"}', HTTPStatus.OK
            return None, HTTPStatus.NOT_FOUND

        with (
            mock.patch.object(
                scotus_cmd_module,
                "fetch_scotus_docket_json",
                side_effect=fake_fetch,
            ),
            mock.patch.object(scotus_cmd_module, "save_scotus_raw_to_s3"),
            mock.patch.object(
                scotus_cmd_module,
                "SCOTUSDocketReport",
                new=FakeSCOTUSDocketReport,
            ),
            mock.patch.object(scotus_cmd_module, "process_scotus_docket"),
            mock.patch.object(scotus_cmd_module.time, "sleep"),
            time_machine.travel(datetime(2025, 7, 2, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)

        self.assertEqual(self.r.hget(self.HIGHEST_KNOWN_KEY, "low:26"), "1")

    def test_applications_sequence_uses_a_format(self, *_mocks):
        """The applications sequence must format docket numbers as YYA{serial}
        and advance the ``applications:YY`` watermark on hits."""
        self._seed_current_term(25, low=3000, high=20000, applications=99)

        def fake_fetch(docket_number):
            if docket_number == "25A100":
                return '{"docket_number":"25A100"}', HTTPStatus.OK
            return None, HTTPStatus.NOT_FOUND

        with (
            mock.patch.object(
                scotus_cmd_module,
                "fetch_scotus_docket_json",
                side_effect=fake_fetch,
            ),
            mock.patch.object(scotus_cmd_module, "save_scotus_raw_to_s3"),
            mock.patch.object(
                scotus_cmd_module,
                "SCOTUSDocketReport",
                new=FakeSCOTUSDocketReport,
            ),
            mock.patch.object(scotus_cmd_module, "process_scotus_docket"),
            mock.patch.object(scotus_cmd_module.time, "sleep"),
            time_machine.travel(datetime(2026, 3, 15, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)

        self.assertEqual(
            self.r.hget(self.HIGHEST_KNOWN_KEY, "applications:25"), "100"
        )

    # ------------------------------------------------------------------ #
    # management command
    # ------------------------------------------------------------------ #

    def test_daemon_runs_probe_iteration_when_enabled(self, *_mocks):
        """The daemon must call ``run_scotus_probe_iteration`` synchronously
        on each tick (no Celery apply_async for probing anymore)."""
        with (
            override_settings(SCOTUS_PROBE_DAEMON_ENABLED=True),
            mock.patch.object(
                scotus_cmd_module, "run_scotus_probe_iteration"
            ) as mock_run,
            mock.patch.object(scotus_cmd_module.time, "sleep"),
        ):
            call_command("probe_scotus_dockets_daemon", testing_iterations=2)

        self.assertEqual(mock_run.call_count, 2)

    def test_daemon_skips_probing_when_court_wait_is_set(self, *_mocks):
        """When ``court_wait`` is active, the daemon must skip
        probing entirely for that tick."""
        self.r.set(self.COURT_WAIT_KEY, "blocked")

        with (
            override_settings(SCOTUS_PROBE_DAEMON_ENABLED=True),
            mock.patch.object(
                scotus_cmd_module, "run_scotus_probe_iteration"
            ) as mock_run,
            mock.patch.object(scotus_cmd_module.time, "sleep"),
        ):
            call_command("probe_scotus_dockets_daemon", testing_iterations=1)

        mock_run.assert_not_called()


@mock.patch(
    f"{SCOTUS_DAEMON_MODULE}.HIGHEST_SCOTUS_KNOWN_SERIAL",
    "test:integration:highest_known",
)
@mock.patch(
    f"{SCOTUS_DAEMON_MODULE}.scotus_empty_probe_attempts_key",
    return_value="test:integration:empty_probes",
)
@mock.patch(
    f"{SCOTUS_DAEMON_MODULE}.scotus_blocked_attempts_key",
    return_value="test:integration:blocked",
)
@mock.patch(
    f"{SCOTUS_DAEMON_MODULE}.scotus_court_wait_key",
    return_value="test:integration:court_wait",
)
class ScotusDaemonIntegrationTest(TestCase):
    """Integration test that exercises the full probe-to-DB pipeline.

    Unlike ScotusDaemonTest (which mocks the Celery task), this test lets
    ``process_scotus_hit`` call ``merge_scotus_docket`` against a real
    database so we can assert that Docket and ScotusDocketMetadata rows
    are actually created.
    """

    HIGHEST_KNOWN_KEY = "test:integration:highest_known"
    COURT_WAIT_KEY = "test:integration:court_wait"
    BLOCKED_KEY = "test:integration:blocked"
    EMPTY_KEY = "test:integration:empty_probes"
    REDIS_KEYS = (
        HIGHEST_KNOWN_KEY,
        COURT_WAIT_KEY,
        BLOCKED_KEY,
        EMPTY_KEY,
    )

    def setUp(self):
        super().setUp()
        self.r = get_redis_interface("CACHE")
        for key in self.REDIS_KEYS:
            self.r.delete(key)
        CourtFactory(id="scotus", jurisdiction="F")

    def tearDown(self):
        for key in self.REDIS_KEYS:
            self.r.delete(key)
        super().tearDown()

    def _seed_current_term(
        self, term: int, low: int = 0, high: int = 5000, applications: int = 0
    ):
        self.r.hset(self.HIGHEST_KNOWN_KEY, f"low:{term:02d}", low)
        self.r.hset(self.HIGHEST_KNOWN_KEY, f"high:{term:02d}", high)
        self.r.hset(
            self.HIGHEST_KNOWN_KEY, f"applications:{term:02d}", applications
        )

    def test_probe_creates_docket_and_metadata(self, *_mocks):
        """The geometric probe must create Docket + ScotusDocketMetadata
        rows for every hit, including serials discovered via backfill.

        With testing=True (jitter=0) and watermark=99 the probe visits:
          iter 1 -> 100 (2^0), iter 2 -> 101 (2^1), iter 3 -> 103 (2^2),
          iter 4 -> 107 (2^3, miss -> boundary).
        Cases 100-103 exist, so 102 is skipped by the probe and must be
        backfilled. The high sequence (watermark=20000) finds nothing.
        """
        self._seed_current_term(25, low=99, high=20000)

        scotus_hit_pattern = {
            "25-100",  # probe hit (2^0)
            "25-101",  # probe hit (2^1)
            "25-102",  # skipped by probe, backfilled
            "25-103",  # probe hit (2^2)
        }

        def fake_fetch(dn):
            if dn in scotus_hit_pattern:
                return f'{{"docket_number":"{dn}"}}', HTTPStatus.OK
            return None, HTTPStatus.NOT_FOUND

        with (
            mock.patch.object(
                scotus_cmd_module,
                "fetch_scotus_docket_json",
                side_effect=fake_fetch,
            ),
            mock.patch.object(
                scotus_cmd_module,
                "SCOTUSDocketReport",
                new=FakeSCOTUSDocketReport,
            ),
            mock.patch.object(scotus_cmd_module, "save_scotus_raw_to_s3"),
            mock.patch.object(scotus_cmd_module.time, "sleep"),
            time_machine.travel(datetime(2026, 3, 15, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)

        created_dockets = Docket.objects.filter(court_id="scotus")
        created_numbers = set(
            created_dockets.values_list("docket_number", flat=True)
        )
        self.assertEqual(created_numbers, scotus_hit_pattern)

        for docket in created_dockets:
            with self.subTest(docket_number=docket.docket_number):
                self.assertEqual(docket.source, Docket.SCRAPER)
                self.assertTrue(
                    ScotusDocketMetadata.objects.filter(docket=docket).exists()
                )

        self.assertEqual(self.r.hget(self.HIGHEST_KNOWN_KEY, "low:25"), "103")
        empty_attempts = self.r.get(self.EMPTY_KEY)
        self.assertIn(empty_attempts, (None, "0"))

    def test_empty_probe_increments_counter(self, *_mocks):
        """When no cases are found across all sequences, the empty-probe
        counter in Redis must be incremented."""
        self._seed_current_term(25, low=99, high=20000)

        def fake_fetch(_dn):
            return None, HTTPStatus.NOT_FOUND

        with (
            mock.patch.object(
                scotus_cmd_module,
                "fetch_scotus_docket_json",
                side_effect=fake_fetch,
            ),
            mock.patch.object(scotus_cmd_module.time, "sleep"),
            time_machine.travel(datetime(2026, 3, 15, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)

        self.assertEqual(self.r.get(self.EMPTY_KEY), "1")

    def test_blocked_logger_after_max_attempts(self, *_mocks):
        """After exceeding SCOTUS_COURT_BLOCKED_MAX_ATTEMPTS, the daemon
        must log an error about prolonged blocking."""
        self._seed_current_term(25, low=99, high=20000)
        self.r.set(
            self.BLOCKED_KEY,
            settings.SCOTUS_COURT_BLOCKED_MAX_ATTEMPTS,
        )

        def raising_fetch(_dn):
            raise HTTPError("403")

        with (
            mock.patch.object(
                scotus_cmd_module,
                "fetch_scotus_docket_json",
                side_effect=raising_fetch,
            ),
            mock.patch.object(scotus_cmd_module.logger, "error") as mock_error,
            mock.patch.object(scotus_cmd_module.time, "sleep"),
            time_machine.travel(datetime(2026, 3, 15, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)

        mock_error.assert_any_call(
            "SCOTUS probing has been blocked for around %s hours.",
            mock.ANY,
        )
        self.assertEqual(self.r.get(self.BLOCKED_KEY), "0")

    def test_empty_probes_limit_logger(self, *_mocks):
        """When SCOTUS_EMPTY_PROBES_LIMIT_HOURS is reached, the daemon
        must log an error about persistent silence."""
        self._seed_current_term(25, low=99, high=20000)
        attempts_needed = max(
            1,
            int(
                settings.SCOTUS_EMPTY_PROBES_LIMIT_HOURS
                * 3600
                / max(1, settings.SCOTUS_PROBE_WAIT)
            ),
        )
        self.r.set(self.EMPTY_KEY, attempts_needed - 1)

        def fake_fetch(_dn):
            return None, HTTPStatus.NOT_FOUND

        with (
            mock.patch.object(
                scotus_cmd_module,
                "fetch_scotus_docket_json",
                side_effect=fake_fetch,
            ),
            mock.patch.object(scotus_cmd_module.logger, "error") as mock_error,
            mock.patch.object(scotus_cmd_module.time, "sleep"),
            time_machine.travel(datetime(2026, 3, 15, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)

        mock_error.assert_any_call(
            "SCOTUS probe has found no new cases for ~%s hours. "
            "Manual intervention may be required.",
            settings.SCOTUS_EMPTY_PROBES_LIMIT_HOURS,
        )
        self.assertEqual(self.r.get(self.EMPTY_KEY), "0")
        self.assertTrue(self.r.exists(self.COURT_WAIT_KEY))
