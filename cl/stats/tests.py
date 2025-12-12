from datetime import datetime, timedelta

import pytest
import time_machine
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.utils.timezone import now
from waffle.testutils import override_flag, override_switch

from cl.lib.redis_utils import get_redis_interface
from cl.search.models import SEARCH_TYPES
from cl.stats.metrics import record_prometheus_metric, search_queries_total
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
