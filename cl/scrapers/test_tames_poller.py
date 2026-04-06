"""Tests for the TAMES poller management command."""

import json
from datetime import date, timedelta
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

import responses
import time_machine
from django.conf import settings

from cl.corpus_importer.tasks import MergeResult
from cl.scrapers.management.commands.tames_poller import (
    CASEMAIL_CASE_ADD_URL,
    CASEMAIL_LOGIN_URL,
    TAMES_PENDING_SUBSCRIPTIONS_KEY,
    Command,
    subscribe_pending_cases,
)
from cl.scrapers.models import AccountSubscription, Scraper
from cl.search.factories import CourtFactory
from cl.search.models import Docket
from cl.tests.cases import TestCase

MODULE = "cl.scrapers.management.commands.tames_poller"
FROZEN_DATE = "2026-03-26"
TODAY = date(2026, 3, 26)

TAMES_ASSET_DIR = (
    Path(settings.INSTALL_ROOT)
    / "cl"
    / "scrapers"
    / "test_assets"
    / "tames_subscription"
)
TAMES_USER = {
    "username": "testuser",
    "password": "testpass",
    "email": "test@example.com",
}


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
        mock.patch(f"{MODULE}.subscribe_pending_cases").start()
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

        self.cmd._poll_cycle(get_options(), self._empty_redis(), None, TAMES_USER)

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

        self.cmd._poll_cycle(get_options(), self._primed_redis(cases), None, TAMES_USER)

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
            TAMES_USER,
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
            TAMES_USER,
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

        with open(
            self.test_asset_dir / "cossup_case.html", encoding="utf-8"
        ) as f:
            case_html = f.read()

        target = make_search_row("24-0340", court_code="cossup")
        fresh_cases = [target] + make_search_rows(24, start=100)
        backfill_cases = [target]

        MockTAMES.side_effect = [
            make_scraper_mock(fresh_cases),
            make_scraper_mock(backfill_cases),
        ]
        setup_rm(MockRM, case_html=case_html)

        self.cmd._poll_cycle(get_options(), self._empty_redis(), None, TAMES_USER)

        self.assertTrue(
            Docket.objects.filter(docket_number="24-0340").exists(),
            "Docket 24-0340 should exist in the database",
        )

    # ------------------------------------------------------------------
    # 6. New cases are added to Redis pending set
    # ------------------------------------------------------------------
    @mock.patch(f"{MODULE}.parse_and_merge_texas_docket")
    @mock.patch(f"{MODULE}.RateLimitedRequestManager")
    @mock.patch(f"{MODULE}.TAMESScraper")
    def test_new_cases_added_to_redis_set(
        self,
        MockTAMES: MagicMock,
        MockRM: MagicMock,
        mock_parse_merge: MagicMock,
    ) -> None:
        """When a case is newly created, it should be sadd-ed to the
        pending subscriptions Redis SET."""
        fresh_cases = make_search_rows(25)
        backfill_cases = make_search_rows(2)

        MockTAMES.side_effect = [
            make_scraper_mock(fresh_cases),
            make_scraper_mock(backfill_cases),
        ]
        setup_rm(MockRM)
        mock_parse_merge.return_value = MergeResult.created(1)

        redis = self._empty_redis()
        self.cmd._poll_cycle(get_options(), redis, None, TAMES_USER)

        self.assertEqual(
            redis.sadd.call_count,
            2,
            "Each newly created case should be sadd-ed to Redis",
        )
        # Verify the key used
        first_call_key = redis.sadd.call_args_list[0][0][0]
        self.assertEqual(first_call_key, TAMES_PENDING_SUBSCRIPTIONS_KEY)


class SubscribePendingCasesTest(TestCase):
    """Tests for the subscribe_pending_cases function."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.login_get_html = (TAMES_ASSET_DIR / "login_get.html").read_text()
        cls.login_post_html = (
            TAMES_ASSET_DIR / "login_post.html"
        ).read_text()
        cls.case_add_success_html = (
            TAMES_ASSET_DIR / "case_add_success.html"
        ).read_text()

    def setUp(self) -> None:
        self.mock_redis = MagicMock()
        self.tracker = AccountSubscription.objects.create(
            scraper=Scraper.TAMES,
            email="test@example.com",
            user_name="testuser",
            first_subscription=date(2025, 1, 15),
            last_subscription=date(2025, 1, 15),
        )

    def _add_login_responses(self, count: int = 1) -> None:
        for _ in range(count):
            responses.add(
                responses.GET,
                CASEMAIL_LOGIN_URL,
                body=self.login_get_html,
                status=200,
            )
            responses.add(
                responses.POST,
                CASEMAIL_LOGIN_URL,
                body=self.login_post_html,
                status=200,
            )

    def _add_case_add_response(
        self, status: int = 200, body: str | None = None
    ) -> None:
        responses.add(
            responses.GET,
            CASEMAIL_CASE_ADD_URL,
            body=body or self.case_add_success_html,
            status=status,
        )

    def test_empty_set_is_noop(self) -> None:
        """When the pending set is empty, no login or requests are made."""
        self.mock_redis.smembers.return_value = set()
        subscribe_pending_cases(self.mock_redis, TAMES_USER)
        self.mock_redis.srem.assert_not_called()

    @responses.activate
    def test_successful_cases_removed_from_redis(self) -> None:
        """Successful subscriptions are srem-ed and tracker is updated."""
        case1 = json.dumps(
            {"court": "cossup", "case": "24-0001", "date_filed": "01/15/2025"},
            sort_keys=True,
        )
        case2 = json.dumps(
            {"court": "cossup", "case": "24-0002", "date_filed": "02/20/2025"},
            sort_keys=True,
        )
        self.mock_redis.smembers.return_value = {case1, case2}

        self._add_login_responses()
        self._add_case_add_response()
        self._add_case_add_response()

        subscribe_pending_cases(self.mock_redis, TAMES_USER)

        self.mock_redis.srem.assert_called_once()
        call_args = self.mock_redis.srem.call_args
        self.assertEqual(call_args[0][0], TAMES_PENDING_SUBSCRIPTIONS_KEY)
        self.assertEqual(set(call_args[0][1:]), {case1, case2})
        self.tracker.refresh_from_db()
        self.assertEqual(self.tracker.first_subscription, date(2025, 1, 15))
        self.assertEqual(self.tracker.last_subscription, date(2025, 2, 20))

    @responses.activate
    def test_login_failure_leaves_cases_pending(self) -> None:
        """When login fails, no cases are removed from the set."""
        case = json.dumps(
            {"court": "cossup", "case": "24-0001", "date_filed": "01/15/2025"},
            sort_keys=True,
        )
        self.mock_redis.smembers.return_value = {case}

        # Return a page that doesn't have the expected login-success marker
        responses.add(
            responses.GET, CASEMAIL_LOGIN_URL, body="<html></html>"
        )
        responses.add(
            responses.POST, CASEMAIL_LOGIN_URL, body="<html>bad</html>"
        )

        subscribe_pending_cases(self.mock_redis, TAMES_USER)

        self.mock_redis.srem.assert_not_called()

    @responses.activate
    def test_partial_failure_removes_only_succeeded(self) -> None:
        """When some cases fail, only succeeded cases are srem-ed."""
        good = json.dumps(
            {"court": "cossup", "case": "24-0001", "date_filed": "01/15/2025"},
            sort_keys=True,
        )
        bad = json.dumps(
            {"court": "cossup", "case": "24-0002", "date_filed": "03/01/2025"},
            sort_keys=True,
        )
        self.mock_redis.smembers.return_value = {good, bad}

        self._add_login_responses()

        def case_add_callback(request):
            """Return 500 for the bad case, 200 for everything else."""
            if "24-0002" in request.url:
                return (500, {}, "Server Error")
            return (200, {}, self.case_add_success_html)

        responses.add_callback(
            responses.GET,
            CASEMAIL_CASE_ADD_URL,
            callback=case_add_callback,
        )

        subscribe_pending_cases(self.mock_redis, TAMES_USER)

        self.mock_redis.srem.assert_called_once_with(
            TAMES_PENDING_SUBSCRIPTIONS_KEY, good
        )

    @responses.activate
    @time_machine.travel("2026-03-31", tick=False)
    def test_new_tracker_uses_case_dates_not_today(self) -> None:
        """When no tracker exists, dates should reflect the case dates."""
        self.tracker.delete()

        case = json.dumps(
            {"court": "cossup", "case": "24-0001", "date_filed": "01/15/2025"},
            sort_keys=True,
        )
        self.mock_redis.smembers.return_value = {case}

        self._add_login_responses()
        self._add_case_add_response()

        subscribe_pending_cases(self.mock_redis, TAMES_USER)

        tracker = AccountSubscription.objects.get(
            scraper=Scraper.TAMES, user_name="testuser"
        )
        self.assertEqual(tracker.first_subscription, date(2025, 1, 15))
        self.assertEqual(tracker.last_subscription, date(2025, 1, 15))
