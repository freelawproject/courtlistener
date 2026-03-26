"""Tests for the TAMES poller management command."""

import json
from datetime import date, timedelta
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

import time_machine
from django.conf import settings

from cl.corpus_importer.tasks import MergeResult
from cl.scrapers.management.commands.tames_poller import (
    Command,
)
from cl.search.factories import CourtFactory
from cl.search.models import Docket
from cl.tests.cases import TestCase

MODULE = "cl.scrapers.management.commands.tames_poller"
FROZEN_DATE = "2026-03-26"
TODAY = date(2026, 3, 26)


def make_search_row(
    case_number: str,
    court_code: str = "cossup",
    date_filed: str = "03/20/2026",
) -> dict[str, str]:
    """Create a fake TamesSearchRow dict."""
    return {
        "case_url": f"https://search.txcourts.gov/Case.aspx?cn={case_number}&coa={court_code}",
        "case_number": case_number,
        "date_filed": date_filed,
        "style": f"Test v. Case {case_number}",
        "v": "v.",
        "case_type": "Petition",
        "coa_case_number": "",
        "trial_court_case_number": "",
        "trial_court_county": "",
        "trial_court": "",
        "appellate_court": "",
        "court_code": court_code,
    }


def make_search_rows(n: int, start: int = 1, **kwargs) -> list[dict[str, str]]:
    """Create n fake TamesSearchRow dicts with sequential case numbers."""
    return [
        make_search_row(f"24-{i:04d}", **kwargs)
        for i in range(start, start + n)
    ]


def make_scraper_mock(cases: list[dict[str, str]]) -> MagicMock:
    """Create a mock TAMESScraper whose backfill yields the given cases."""
    scraper = MagicMock()
    scraper.backfill.return_value = iter(cases)
    scraper.COURT_IDS = ["texas_cossup"]
    scraper.FIRST_RECORD_DATE = date(1900, 1, 1)
    return scraper


def setup_rm(MockRM: MagicMock, case_html: str = "<html></html>") -> None:
    """Set up RateLimitedRequestManager context-manager mocks.

    Configures two RM instances (search and case). The case RM's
    .get() returns a mock response with .text set to ``case_html``.
    """
    mock_rm1 = MagicMock()  # search RM (unused; TAMESScraper is mocked)
    mock_rm2 = MagicMock()  # case RM
    mock_response = MagicMock()
    mock_response.text = case_html
    mock_rm2.__enter__.return_value.get.return_value = mock_response
    MockRM.side_effect = [mock_rm1, mock_rm2]


def get_options(**overrides: object) -> dict:
    """Return default _poll_cycle options with optional overrides."""
    defaults: dict = {
        "polling_delay": 1,
        "case_backfill_count": None,
        "case_backfill_days": 3,
        "poll_window_days": 7,
        "courts": None,
        "search_rate": 10000.0,
        "case_rate": 10000.0,
        "max_backoff": 1,
    }
    defaults.update(overrides)
    return defaults


@time_machine.travel(FROZEN_DATE)
class TamesPollerTest(TestCase):
    """Integration tests for the TAMES poller _poll_cycle method."""

    def setUp(self) -> None:
        self.test_asset_dir = (
            Path(settings.INSTALL_ROOT)
            / "cl"
            / "scrapers"
            / "test_assets"
            / "tames_poller"
        )
        self.cmd = Command()
        mock.patch(f"{MODULE}.save_docket_response").start()
        mock.patch(f"{MODULE}.subscribe_to_tames_cases").start()
        self.addCleanup(mock.patch.stopall)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _empty_redis() -> MagicMock:
        redis = MagicMock()
        redis.get.return_value = None
        return redis

    @staticmethod
    def _primed_redis(cases: list[dict[str, str]]) -> MagicMock:
        """Return a mock Redis pre-loaded with the URLs from *cases*."""
        redis = MagicMock()
        redis.get.return_value = json.dumps([c["case_url"] for c in cases])
        return redis

    # ------------------------------------------------------------------
    # 1. Novel results → merge attempted
    # ------------------------------------------------------------------
    @mock.patch(f"{MODULE}.parse_and_merge_texas_docket")
    @mock.patch(f"{MODULE}.RateLimitedRequestManager")
    @mock.patch(f"{MODULE}.TAMESScraper")
    def test_novel_results_trigger_merge(
        self,
        MockTAMES: MagicMock,
        MockRM: MagicMock,
        mock_parse_merge: MagicMock,
    ) -> None:
        """When fresh URLs are not in the Redis cache, the poller should
        backfill and attempt to merge every returned case."""
        fresh_cases = make_search_rows(25)
        backfill_cases = make_search_rows(5)

        MockTAMES.side_effect = [
            make_scraper_mock(fresh_cases),
            make_scraper_mock(backfill_cases),
        ]
        setup_rm(MockRM)
        mock_parse_merge.return_value = MergeResult.created(1)

        self.cmd._poll_cycle(get_options(), self._empty_redis(), None)

        self.assertEqual(
            mock_parse_merge.call_count,
            5,
            "Should attempt to merge each backfill case",
        )

    # ------------------------------------------------------------------
    # 2. Fully-cached results → merge skipped
    # ------------------------------------------------------------------
    @mock.patch(f"{MODULE}.parse_and_merge_texas_docket")
    @mock.patch(f"{MODULE}.RateLimitedRequestManager")
    @mock.patch(f"{MODULE}.TAMESScraper")
    def test_cached_results_skip_merge(
        self,
        MockTAMES: MagicMock,
        MockRM: MagicMock,
        mock_parse_merge: MagicMock,
    ) -> None:
        """When every fresh URL already exists in the Redis cache, the
        poller should skip backfill entirely."""
        cases = make_search_rows(25)

        # Only the freshness-check scraper is needed (no backfill).
        MockTAMES.side_effect = [make_scraper_mock(cases)]
        setup_rm(MockRM)

        self.cmd._poll_cycle(get_options(), self._primed_redis(cases), None)

        mock_parse_merge.assert_not_called()
        self.assertEqual(
            MockTAMES.call_count,
            1,
            "Only the freshness-check scraper should be created",
        )

    # ------------------------------------------------------------------
    # 3. Backfill by date range
    # ------------------------------------------------------------------
    @mock.patch(f"{MODULE}.parse_and_merge_texas_docket")
    @mock.patch(f"{MODULE}.RateLimitedRequestManager")
    @mock.patch(f"{MODULE}.TAMESScraper")
    def test_backfill_by_date(
        self,
        MockTAMES: MagicMock,
        MockRM: MagicMock,
        mock_parse_merge: MagicMock,
    ) -> None:
        """With --case-backfill-days the backfill scraper should receive
        a date range spanning that many days from today, and every case
        yielded within that window should be processed."""
        backfill_days = 5
        fresh_cases = make_search_rows(25)
        backfill_cases = make_search_rows(3)
        backfill_scraper = make_scraper_mock(backfill_cases)

        MockTAMES.side_effect = [
            make_scraper_mock(fresh_cases),
            backfill_scraper,
        ]
        setup_rm(MockRM)
        mock_parse_merge.return_value = MergeResult.created(1)

        self.cmd._poll_cycle(
            get_options(case_backfill_days=backfill_days),
            self._empty_redis(),
            None,
        )

        _, (start, end) = backfill_scraper.backfill.call_args[0]
        self.assertEqual(start, TODAY - timedelta(days=backfill_days))
        self.assertEqual(end, TODAY)
        self.assertEqual(
            mock_parse_merge.call_count,
            3,
            "All cases within the date window should be processed",
        )

    # ------------------------------------------------------------------
    # 4. Backfill by count
    # ------------------------------------------------------------------
    @mock.patch(f"{MODULE}.parse_and_merge_texas_docket")
    @mock.patch(f"{MODULE}.RateLimitedRequestManager")
    @mock.patch(f"{MODULE}.TAMESScraper")
    def test_backfill_by_count(
        self,
        MockTAMES: MagicMock,
        MockRM: MagicMock,
        mock_parse_merge: MagicMock,
    ) -> None:
        """With --case-backfill-count the poller should stop processing
        after exactly that many cases, even when more are available."""
        fresh_cases = make_search_rows(25)
        backfill_cases = make_search_rows(10)

        MockTAMES.side_effect = [
            make_scraper_mock(fresh_cases),
            make_scraper_mock(backfill_cases),
        ]
        setup_rm(MockRM)
        mock_parse_merge.return_value = MergeResult.created(1)

        self.cmd._poll_cycle(
            get_options(case_backfill_count=5, case_backfill_days=None),
            self._empty_redis(),
            None,
        )

        self.assertEqual(
            mock_parse_merge.call_count,
            5,
            "Should stop after processing exactly 5 cases",
        )

    # ------------------------------------------------------------------
    # 5. New cases appear in the database
    # ------------------------------------------------------------------
    @mock.patch(f"{MODULE}.RateLimitedRequestManager")
    @mock.patch(f"{MODULE}.TAMESScraper")
    def test_new_cases_appear_in_db(
        self,
        MockTAMES: MagicMock,
        MockRM: MagicMock,
    ) -> None:
        """After a successful poll cycle the parsed case should exist as
        a Docket row in the database.  Uses the real parser and merge
        pipeline — only external I/O (S3, Celery, TAMES HTTP) is mocked.
        Attachment downloads are scheduled via on_commit and never fire
        inside TestCase's always-rolled-back transaction."""
        # Court required by merge_texas_docket (hard lookup at line 4720)
        CourtFactory.create(id="tex")

        with open(self.test_asset_dir / "cossup_case.html", encoding="utf-8") as f:
            case_html = f.read()

        target = make_search_row("24-0340", court_code="cossup")
        fresh_cases = [target] + make_search_rows(24, start=100)
        backfill_cases = [target]

        MockTAMES.side_effect = [
            make_scraper_mock(fresh_cases),
            make_scraper_mock(backfill_cases),
        ]
        setup_rm(MockRM, case_html=case_html)

        self.cmd._poll_cycle(get_options(), self._empty_redis(), None)

        self.assertTrue(
            Docket.objects.filter(docket_number="24-0340").exists(),
            "Docket 24-0340 should exist in the database",
        )
