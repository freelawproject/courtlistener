from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import time_machine
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now
from waffle.testutils import override_flag, override_switch

from cl.lib.redis_utils import get_redis_interface
from cl.search.models import SEARCH_TYPES
from cl.stats.metrics import (
    CeleryQueueCollector,
    accounts_created_total,
    accounts_deleted_total,
    alerts_sent_total,
    record_prometheus_metric,
    search_queries_total,
    webhooks_sent_total,
)
from cl.stats.models import Event
from cl.stats.utils import get_milestone_range, tally_stat
from cl.tests.cases import ESIndexTestCase, TestCase
from cl.tests.utils import AsyncAPIClient
from cl.users.factories import UserFactory, UserProfileWithParentsFactory


class MilestoneTests(TestCase):
    def test_milestone_ranges(self) -> None:
        numbers = get_milestone_range("XS", "SM")
        self.assertEqual(numbers[0], 1e1)
        self.assertEqual(numbers[-1], 5e4)


class PartnershipEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.api_user = UserFactory()
        cls.webhook_user = UserFactory()

    def test_command_can_filter_user_api_events(self) -> None:
        with time_machine.travel(
            datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
            tick=False,
        ):
            global_v4_api_event = Event.objects.create(
                description="API v4 has logged 1000 total requests."
            )
            global_v3_api_event = Event.objects.create(
                description="API v3 has logged 1000 total requests."
            )
            global_webhook_event = Event.objects.create(
                description="Webhooks have logged 1000 total successful events."
            )
            v4_api_user_event = Event.objects.create(
                description=f"User '{self.api_user.username}' has placed their 3rd API v4 request.",
                user=self.api_user,
            )
            v3_api_user_event = Event.objects.create(
                description=f"User '{self.api_user.username}' has placed their 3rd API v3 request.",
                user=self.api_user,
            )
            webhook_user_event = Event.objects.create(
                description=f"User '{self.api_user.username}' has placed their 3rd webhook event.",
                user=self.webhook_user,
            )
            call_command("send_events_email")

        # Assert an email was sent
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        email = mail.outbox[0]

        # Extract email content
        body = email.body

        # Should include global and webhook user events
        self.assertIn(global_v3_api_event.description, body)
        self.assertIn(global_v4_api_event.description, body)
        self.assertIn(v3_api_user_event.description, body)
        self.assertIn(global_webhook_event.description, body)
        self.assertIn(webhook_user_event.description, body)

        # Should exclude v4 API user-specific event
        self.assertNotIn(v4_api_user_event.description, body)


@pytest.mark.django_db
@override_switch("increment-stats", active=True)
class StatTests(TestCase):
    def setUp(self):
        self.r = get_redis_interface("STATS")
        key = self.r.keys("test*")
        if key:
            self.r.delete(*key)

    def test_tally_a_stat(self) -> None:
        count = tally_stat("test")
        self.assertEqual(count, 1)

    def test_increment_a_stat(self) -> None:
        count = tally_stat("test2")
        self.assertEqual(count, 1)
        count = tally_stat("test2")
        self.assertEqual(count, 2)

    def test_increment_by_two(self) -> None:
        count = tally_stat("test3", inc=2)
        self.assertEqual(count, 2)
        count = tally_stat("test3", inc=2)
        self.assertEqual(count, 4)

    def test_stat_expires_in_10_days(self) -> None:
        mock_date = datetime.combine(
            now().date(), datetime.min.time()
        ) - timedelta(days=10)
        # Create the stat 10 days in the past
        with time_machine.travel(mock_date, tick=False):
            tally_stat("test4")

        # Compute the expiration timestamp
        key_ttl = self.r.ttl("test4." + mock_date.date().isoformat())
        expired_at = mock_date + timedelta(seconds=key_ttl)

        # The key should still be valid today
        self.assertGreater(expired_at.date(), now().date())

        # But it must expire no later than tomorrow
        tomorrow = now() + timedelta(days=1)
        self.assertLessEqual(expired_at.date(), tomorrow.date())


class PrometheusMetricsTests(TestCase):
    def setUp(self):
        search_queries_total._metrics.clear()
        alerts_sent_total._metrics.clear()
        webhooks_sent_total._metrics.clear()
        accounts_created_total._value.set(0)
        accounts_deleted_total._value.set(0)

    def test_record_prometheus_metric(self) -> None:
        """Test recording metrics with different handler keys and labels"""
        test_cases = [
            {
                "name": "keyword_web",
                "handler_key": "search.queries.keyword.web",
                "query_type": "keyword",
                "method": "web",
                "increments": [1],
            },
            {
                "name": "semantic_api",
                "handler_key": "search.queries.semantic.api",
                "query_type": "semantic",
                "method": "api",
                "increments": [1],
            },
            {
                "name": "accumulation",
                "handler_key": "search.queries.keyword.api",
                "query_type": "keyword",
                "method": "api",
                "increments": [1, 2, 3],
            },
        ]

        for test_case in test_cases:
            with self.subTest(case=test_case["name"]):
                initial = search_queries_total.labels(
                    query_type=test_case["query_type"],
                    method=test_case["method"],
                )._value.get()

                for inc in test_case["increments"]:
                    record_prometheus_metric(test_case["handler_key"], inc)

                final = search_queries_total.labels(
                    query_type=test_case["query_type"],
                    method=test_case["method"],
                )._value.get()
                expected_total = sum(test_case["increments"])
                self.assertEqual(final, initial + expected_total)

    def test_alert_metrics(self) -> None:
        """Test recording alert metrics with different alert types"""
        test_cases = [
            {
                "name": "search_alert",
                "handler_key": "alerts.sent.search",
                "alert_type": "search_alert",
                "increments": [1],
            },
            {
                "name": "docket_alert",
                "handler_key": "alerts.sent.docket",
                "alert_type": "docket_alert",
                "increments": [1, 2],
            },
        ]

        for test_case in test_cases:
            with self.subTest(case=test_case["name"]):
                initial = alerts_sent_total.labels(
                    alert_type=test_case["alert_type"],
                )._value.get()

                for inc in test_case["increments"]:
                    record_prometheus_metric(test_case["handler_key"], inc)

                final = alerts_sent_total.labels(
                    alert_type=test_case["alert_type"],
                )._value.get()
                expected_total = sum(test_case["increments"])
                self.assertEqual(final, initial + expected_total)

    def test_webhook_metrics(self) -> None:
        """Test recording webhook metrics with different event types"""
        test_cases = [
            {
                "name": "docket_alert",
                "handler_key": "webhooks.sent.docket_alert",
                "event_type": "docket_alert",
                "increments": [1],
            },
            {
                "name": "search_alert",
                "handler_key": "webhooks.sent.search_alert",
                "event_type": "search_alert",
                "increments": [1],
            },
            {
                "name": "recap_fetch",
                "handler_key": "webhooks.sent.recap_fetch",
                "event_type": "recap_fetch",
                "increments": [1, 1],
            },
            {
                "name": "old_docket_alerts_report",
                "handler_key": "webhooks.sent.old_docket_alerts_report",
                "event_type": "old_docket_alerts_report",
                "increments": [1],
            },
            {
                "name": "pray_and_pay",
                "handler_key": "webhooks.sent.pray_and_pay",
                "event_type": "pray_and_pay",
                "increments": [1],
            },
        ]

        for test_case in test_cases:
            with self.subTest(case=test_case["name"]):
                initial = webhooks_sent_total.labels(
                    event_type=test_case["event_type"],
                )._value.get()

                for inc in test_case["increments"]:
                    record_prometheus_metric(test_case["handler_key"], inc)

                final = webhooks_sent_total.labels(
                    event_type=test_case["event_type"],
                )._value.get()
                expected_total = sum(test_case["increments"])
                self.assertEqual(final, initial + expected_total)

    def test_account_metrics(self) -> None:
        """Test recording account creation and deletion metrics"""
        # Test accounts created
        initial_created = accounts_created_total._value.get()
        record_prometheus_metric("accounts.created", 1)
        record_prometheus_metric("accounts.created", 2)
        final_created = accounts_created_total._value.get()
        self.assertEqual(final_created, initial_created + 3)

        # Test accounts deleted
        initial_deleted = accounts_deleted_total._value.get()
        record_prometheus_metric("accounts.deleted", 1)
        final_deleted = accounts_deleted_total._value.get()
        self.assertEqual(final_deleted, initial_deleted + 1)


def parse_prometheus_metrics(metrics_text: str) -> dict[str, float]:
    """Parse Prometheus text format into dict of metric names to values."""
    metrics = {}
    for line in metrics_text.split("\n"):
        if line.startswith("#") or not line.strip():
            continue
        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            continue
        metric_name, value = parts
        try:
            metrics[metric_name] = float(value)
        except ValueError:
            continue
    return metrics


@override_flag("semantic-search", active=True)
@override_switch("increment-stats", active=True)
class PrometheusIntegrationTestBase(ESIndexTestCase, TestCase):
    """Base class for Prometheus integration tests"""

    def setUp(self):
        search_queries_total._metrics.clear()
        self.async_client = AsyncAPIClient()

    async def _get_metric_count(self, query_type: str, method: str) -> float:
        """Helper to fetch and parse a specific Prometheus metric count"""
        response = await self.async_client.get(
            "/monitoring/prometheus/metrics"
        )
        self.assertEqual(response.status_code, 200)
        metrics = parse_prometheus_metrics(response.content.decode("utf-8"))
        return metrics.get(
            f'cl_search_queries_total{{method="{method}",query_type="{query_type}"}}',
            0.0,
        )


@override_flag("store-search-api-queries", active=True)
@override_settings(WAFFLE_CACHE_PREFIX="test_prometheus_integration")
class PrometheusIntegrationAPITests(PrometheusIntegrationTestBase):
    """Integration tests for Prometheus metrics with API searches"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user_profile = UserProfileWithParentsFactory()

    async def test_api_keyword_search_increments_metric(self) -> None:
        """Verify keyword API searches increment the Prometheus counter"""
        initial_count = await self._get_metric_count("keyword", "api")

        search_url = reverse("search-list", kwargs={"version": "v4"})
        await self.async_client.get(
            search_url, {"q": "test query", "type": SEARCH_TYPES.OPINION}
        )

        final_count = await self._get_metric_count("keyword", "api")
        self.assertEqual(final_count, initial_count + 1)

    async def test_api_semantic_search_increments_metric(self) -> None:
        """Verify semantic API searches increment the Prometheus counter"""
        initial_count = await self._get_metric_count("semantic", "api")

        search_url = reverse("search-list", kwargs={"version": "v4"})
        await self.async_client.get(
            search_url,
            {
                "q": "test query",
                "type": SEARCH_TYPES.OPINION,
                "semantic": True,
            },
        )

        final_count = await self._get_metric_count("semantic", "api")
        self.assertEqual(final_count, initial_count + 1)


class PrometheusIntegrationWebTests(PrometheusIntegrationTestBase):
    """Integration tests for Prometheus metrics with web searches"""

    async def test_web_keyword_searches_accumulate(self) -> None:
        """Verify multiple web searches accumulate correctly in Prometheus"""
        initial_count = await self._get_metric_count("keyword", "web")

        search_url = reverse("show_results")
        for i in range(3):
            await self.async_client.get(
                search_url,
                {"q": f"test query {i}", "type": SEARCH_TYPES.OPINION},
            )

        final_count = await self._get_metric_count("keyword", "web")
        self.assertEqual(final_count, initial_count + 3)


class CeleryQueueCollectorTests(TestCase):
    """Unit tests for CeleryQueueCollector"""

    @patch("cl.stats.metrics.get_queue_length")
    @patch("cl.stats.metrics.settings")
    def test_collector_returns_queue_lengths(
        self, mock_settings, mock_get_queue_length
    ) -> None:
        """Test that collector returns correct gauge metrics for each queue"""
        mock_settings.CELERY_QUEUES = ["celery", "batch0", "recap_fetch"]
        mock_get_queue_length.side_effect = [10, 5, 0]

        collector = CeleryQueueCollector()
        metrics = list(collector.collect())

        self.assertEqual(len(metrics), 1)
        gauge = metrics[0]
        self.assertEqual(gauge.name, "cl_celery_queue_length")
        self.assertEqual(len(gauge.samples), 3)

        # Check each sample has correct queue label and value
        samples_by_queue = {s.labels["queue"]: s.value for s in gauge.samples}
        self.assertEqual(samples_by_queue["celery"], 10)
        self.assertEqual(samples_by_queue["batch0"], 5)
        self.assertEqual(samples_by_queue["recap_fetch"], 0)

    @patch("cl.stats.metrics.get_queue_length")
    @patch("cl.stats.metrics.settings")
    def test_collector_handles_errors_gracefully(
        self, mock_settings, mock_get_queue_length
    ) -> None:
        """Test that collector continues collecting when one queue fails"""
        mock_settings.CELERY_QUEUES = ["celery", "bad_queue", "batch0"]

        def side_effect(queue):
            if queue == "bad_queue":
                raise ConnectionError("Redis unavailable")
            return 10 if queue == "celery" else 5

        mock_get_queue_length.side_effect = side_effect

        collector = CeleryQueueCollector()
        metrics = list(collector.collect())

        gauge = metrics[0]
        # Should only have 2 samples (bad_queue was skipped)
        self.assertEqual(len(gauge.samples), 2)

        samples_by_queue = {s.labels["queue"]: s.value for s in gauge.samples}
        self.assertIn("celery", samples_by_queue)
        self.assertIn("batch0", samples_by_queue)
        self.assertNotIn("bad_queue", samples_by_queue)


class CeleryQueueCollectorIntegrationTests(TestCase):
    """Integration test for CeleryQueueCollector via prometheus endpoint"""

    async def test_celery_queue_metrics_in_prometheus_output(self) -> None:
        """Verify celery queue metrics appear in prometheus endpoint"""
        client = AsyncAPIClient()
        response = await client.get("/monitoring/prometheus/metrics")
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("cl_celery_queue_length", content)
        # Check for at least one queue label
        self.assertIn('queue="celery"', content)
