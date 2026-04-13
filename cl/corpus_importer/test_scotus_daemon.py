import re
from datetime import date, datetime
from unittest import mock

import time_machine
from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from requests.exceptions import HTTPError

from cl.corpus_importer import tasks as scotus_tasks_module
from cl.corpus_importer.management.commands import (
    probe_scotus_dockets_daemon as scotus_cmd_module,
)
from cl.corpus_importer.scotus_daemon_utils import (
    HIGHEST_KNOWN_HASH,
    current_scotus_term_year,
    format_docket_number,
    next_term_starts_probing,
    parse_docket_number,
    scotus_blocked_attempts_key,
    scotus_court_wait_key,
    scotus_empty_probe_attempts_key,
    scotus_raw_s3_key,
)
from cl.lib.redis_utils import get_redis_interface

SCOTUS_REDIS_KEYS_TO_CLEAN = (
    HIGHEST_KNOWN_HASH,
    scotus_court_wait_key(),
    scotus_blocked_attempts_key(),
    scotus_empty_probe_attempts_key(),
)


def _clean_scotus_redis_keys(r) -> None:
    """Delete all SCOTUS daemon keys from Redis."""
    for key in SCOTUS_REDIS_KEYS_TO_CLEAN:
        r.delete(key)


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
        self.assertTrue(next_term_starts_probing(date(2026, 12, 31)))

    def test_parse_and_format_docket_number(self):
        self.assertEqual(parse_docket_number("25-150"), (25, 150))
        self.assertEqual(parse_docket_number("25-5200"), (25, 5200))
        self.assertEqual(format_docket_number(25, 150), "25-150")
        self.assertEqual(format_docket_number(3, 7), "03-7")
        with self.assertRaises(ValueError):
            parse_docket_number("garbage")

    def test_s3_key_layout(self):
        self.assertEqual(
            scotus_raw_s3_key("25-150"),
            "responses/dockets/scotus/25-150.json",
        )


class _FakeSCOTUSReport:
    """Minimal stand-in for juriscraper.scotus.SCOTUSDocketReport.

    ``_parse_text`` stashes whatever ``docket_number`` the JSON body
    advertises into ``self.data`` so ``process_scotus_hit`` can pass it
    downstream.
    """

    def __init__(self):
        self.data: dict = {}

    def _parse_text(self, content: str) -> None:
        match = re.search(r'"docket_number"\s*:\s*"([^"]+)"', content)
        self.data = {
            "docket_number": match.group(1) if match else "",
            "parties": [],
            "docket_entries": [],
        }


class ScotusDaemonTest(SimpleTestCase):
    """End-to-end coverage for the synchronous SCOTUS probing daemon.

    Exercises both the probe-iteration function and the management command
    against real Redis. All SCOTUS daemon keys are cleaned before and
    after each test to prevent intra-worker contamination; co-locating
    these tests in a single class also prevents cross-worker races from
    the parallel test runner.
    """

    def setUp(self):
        super().setUp()
        self.r = get_redis_interface("CACHE")
        _clean_scotus_redis_keys(self.r)

    def tearDown(self):
        _clean_scotus_redis_keys(self.r)
        super().tearDown()

    def _seed_current_term(self, term: int, low: int = 0, high: int = 5000):
        self.r.hset(HIGHEST_KNOWN_HASH, f"low:{term:02d}", low)
        self.r.hset(HIGHEST_KNOWN_HASH, f"high:{term:02d}", high)

    # ------------------------------------------------------------------ #
    # run_scotus_probe_iteration
    # ------------------------------------------------------------------ #

    def test_missing_seed_aborts(self):
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

    def test_probe_finds_new_cases_and_backfills_inline(self):
        """Probe must advance the watermark, ingest each direct hit, and
        synchronously backfill serials skipped by the geometric probe.
        Every hit (probe + backfill) must be archived to S3 and handed to
        the Celery ingestion task."""
        # Seed watermark for term 25: low=99, high=20000 (sentinel-high so
        # the high-range sequence probes and finds nothing, isolating the
        # low-range signal).
        self._seed_current_term(25, low=99, high=20000)

        # Contiguous run of valid low-range serials starting at 100. With
        # testing=True (jitter=0) the geometric probe will hit
        # 100, 101, 103, 107, 115, then miss 131 and break. That skips
        # 102, 104, 105, 106, 108..114 — which must get backfilled inline.
        valid_low = {f"25-{n}" for n in range(100, 116)}

        def fake_fetch(docket_number):
            if docket_number in valid_low:
                return ('{"docket_number":"%s"}' % docket_number), 200
            return None, 404

        with (
            mock.patch.object(
                scotus_cmd_module,
                "fetch_scotus_docket_json",
                side_effect=fake_fetch,
            ),
            mock.patch.object(
                scotus_tasks_module, "save_scotus_raw_to_s3"
            ) as mock_save,
            mock.patch.object(
                scotus_tasks_module,
                "SCOTUSDocketReport",
                new=_FakeSCOTUSReport,
            ),
            mock.patch.object(
                scotus_tasks_module, "process_scotus_docket"
            ) as mock_proc,
            mock.patch.object(scotus_cmd_module.time, "sleep"),
            # 2026-03-15 is inside the 2025 term but OUTSIDE the rollover
            # window, so only current-term probing runs.
            time_machine.travel(datetime(2026, 3, 15, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)

        # Final low-range watermark should be the last direct hit: 115.
        self.assertEqual(self.r.hget(HIGHEST_KNOWN_HASH, "low:25"), "115")
        # Every valid low-range serial (100..115 = 16 dockets) must have
        # been archived to S3 and handed to the Celery ingestion task: 5
        # from direct probe hits + 11 from inline backfill.
        self.assertEqual(mock_save.call_count, 16)
        self.assertEqual(mock_proc.delay.call_count, 16)
        enqueued_docket_numbers = {
            call_args.args[0]["docket_number"]
            for call_args in mock_proc.delay.call_args_list
        }
        self.assertEqual(enqueued_docket_numbers, valid_low)

    def test_http_error_triggers_backoff(self):
        """An HTTPError during probing must set scotus:court_wait with TTL."""
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

        self.assertEqual(self.r.get(scotus_blocked_attempts_key()), "1")
        self.assertTrue(self.r.exists(scotus_court_wait_key()))

    def test_empty_probe_alert_on_persistent_silence(self):
        """Enough empty probes must raise a logger.error and set a 1h wait."""
        self._seed_current_term(25, low=100, high=20000)
        # Pre-populate the counter so this single run trips the threshold.
        attempts_needed = max(
            1,
            int(
                settings.SCOTUS_EMPTY_PROBES_LIMIT_HOURS
                * 3600
                / max(1, settings.SCOTUS_PROBE_WAIT)
            ),
        )
        self.r.set(scotus_empty_probe_attempts_key(), attempts_needed - 1)

        with (
            mock.patch.object(
                scotus_cmd_module,
                "fetch_scotus_docket_json",
                return_value=(None, 404),
            ),
            mock.patch.object(scotus_cmd_module.logger, "error") as mock_error,
            time_machine.travel(datetime(2026, 3, 15, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)

        self.assertTrue(mock_error.called)
        self.assertEqual(self.r.get(scotus_court_wait_key()), "3600")

    def test_term_rollover_persists_new_term_watermark(self):
        """During the July-onward rollover window, a hit in the new term
        must persist ``low:26``."""
        # 2025-07-02 sits in the current term 25 (term 25 begins
        # 2025-07-01) and activates next-term probing for term 26.
        self._seed_current_term(25, low=3000, high=20000)

        def fake_fetch(docket_number):
            # No more cases in term 25; a single 26-1 in the new term.
            if docket_number == "26-1":
                return '{"docket_number":"26-1"}', 200
            return None, 404

        with (
            mock.patch.object(
                scotus_cmd_module,
                "fetch_scotus_docket_json",
                side_effect=fake_fetch,
            ),
            mock.patch.object(scotus_tasks_module, "save_scotus_raw_to_s3"),
            mock.patch.object(
                scotus_tasks_module,
                "SCOTUSDocketReport",
                new=_FakeSCOTUSReport,
            ),
            mock.patch.object(scotus_tasks_module, "process_scotus_docket"),
            mock.patch.object(scotus_cmd_module.time, "sleep"),
            time_machine.travel(datetime(2025, 7, 2, 12), tick=False),
        ):
            scotus_cmd_module.run_scotus_probe_iteration(self.r, testing=True)

        self.assertEqual(self.r.hget(HIGHEST_KNOWN_HASH, "low:26"), "1")

    # ------------------------------------------------------------------ #
    # management command
    # ------------------------------------------------------------------ #

    def test_daemon_runs_probe_iteration_when_enabled(self):
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

    def test_daemon_skips_probing_when_court_wait_is_set(self):
        """When ``scotus:court_wait`` is active, the daemon must skip
        probing entirely for that tick."""
        self.r.set(scotus_court_wait_key(), "blocked")

        with (
            override_settings(SCOTUS_PROBE_DAEMON_ENABLED=True),
            mock.patch.object(
                scotus_cmd_module, "run_scotus_probe_iteration"
            ) as mock_run,
            mock.patch.object(scotus_cmd_module.time, "sleep"),
        ):
            call_command("probe_scotus_dockets_daemon", testing_iterations=1)

        mock_run.assert_not_called()
