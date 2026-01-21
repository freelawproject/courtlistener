from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import time_machine
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now
from prometheus_client import CollectorRegistry
from waffle.testutils import override_flag, override_switch

from cl.lib.redis_utils import get_redis_interface
from cl.search.models import SEARCH_TYPES
from cl.stats.constants import (
    STAT_METRICS_PREFIX,
    StatAlertType,
    StatMethod,
    StatMetric,
    StatQueryType,
)
from cl.stats.metrics import (
    CeleryQueueCollector,
    CeleryTaskMetricsCollector,
    StatMetricsCollector,
    accounts_created_total,
    accounts_deleted_total,
    record_search_duration,
    register_celery_queue_collector,
    register_stat_metrics_collector,
    search_duration_seconds,
    search_queries_total,
)
from cl.stats.models import Event
from cl.stats.utils import (
    _update_prometheus_stat,
    _validate_labels,
    get_milestone_range,
    tally_stat,
)
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
@override_settings(WAFFLE_CACHE_PREFIX="StatTests")
class StatTests(TestCase):
    def setUp(self):
        self.r = get_redis_interface("STATS")
        # Clean up date-based test keys
        keys = self.r.keys("test*")
        if keys:
            self.r.delete(*keys)
        # Clean up prometheus test keys
        for key in self.r.scan_iter(f"{STAT_METRICS_PREFIX}test*"):
            self.r.delete(key)

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
        search_duration_seconds._metrics.clear()
        accounts_created_total._value.set(0)
        accounts_deleted_total._value.set(0)

    def test_search_queries_metric(self) -> None:
        """Test recording search query metrics with different labels"""
        test_cases = [
            {
                "name": "keyword_web",
                "query_type": "keyword",
                "method": "web",
                "increments": [1],
            },
            {
                "name": "semantic_api",
                "query_type": "semantic",
                "method": "api",
                "increments": [1],
            },
            {
                "name": "accumulation",
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
                    search_queries_total.labels(
                        query_type=test_case["query_type"],
                        method=test_case["method"],
                    ).inc(inc)

                final = search_queries_total.labels(
                    query_type=test_case["query_type"],
                    method=test_case["method"],
                )._value.get()
                expected_total = sum(test_case["increments"])
                self.assertEqual(final, initial + expected_total)

    def test_account_metrics(self) -> None:
        """Test recording account creation and deletion metrics"""
        # Test accounts created
        initial_created = accounts_created_total._value.get()
        accounts_created_total.inc()
        accounts_created_total.inc(2)
        final_created = accounts_created_total._value.get()
        self.assertEqual(final_created, initial_created + 3)

        # Test accounts deleted
        initial_deleted = accounts_deleted_total._value.get()
        accounts_deleted_total.inc()
        final_deleted = accounts_deleted_total._value.get()
        self.assertEqual(final_deleted, initial_deleted + 1)

    def test_search_duration_histogram(self) -> None:
        """Test recording search duration histogram metrics"""
        test_cases = [
            {
                "name": "keyword_web",
                "query_type": "keyword",
                "method": "web",
                "durations": [0.1, 0.2, 0.15],
            },
            {
                "name": "semantic_api",
                "query_type": "semantic",
                "method": "api",
                "durations": [0.5, 0.3],
            },
            {
                "name": "keyword_api",
                "query_type": "keyword",
                "method": "api",
                "durations": [0.05],
            },
        ]

        for test_case in test_cases:
            with self.subTest(case=test_case["name"]):
                # Get initial sum
                initial_sum = search_duration_seconds.labels(
                    query_type=test_case["query_type"],
                    method=test_case["method"],
                )._sum.get()

                # Record durations
                for duration in test_case["durations"]:
                    record_search_duration(
                        duration,
                        query_type=test_case["query_type"],
                        method=test_case["method"],
                    )

                # Check that sum increased by total of durations
                final_sum = search_duration_seconds.labels(
                    query_type=test_case["query_type"],
                    method=test_case["method"],
                )._sum.get()
                expected_sum = initial_sum + sum(test_case["durations"])
                self.assertAlmostEqual(final_sum, expected_sum, places=5)

    def test_celery_queue_collector_registration_idempotent(self) -> None:
        """Ensure collector registration is idempotent without collecting."""
        registry = CollectorRegistry()
        self.assertTrue(register_celery_queue_collector(registry))
        self.assertFalse(register_celery_queue_collector(registry))


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
@override_settings(WAFFLE_CACHE_PREFIX="PrometheusIntegrationTestBase")
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


class CeleryTaskMetricsCollectorTests(TestCase):
    """Unit tests for CeleryTaskMetricsCollector

    Each test uses a unique prefix to avoid collisions when tests run in
    parallel. The prefix is patched via decorator on each test method.
    """

    def setUp(self):
        self.r = get_redis_interface("STATS")

    def _cleanup_keys(self, prefix: str) -> None:
        """Clean up Redis keys with the given prefix"""
        for key in self.r.scan_iter(f"{prefix}*"):
            self.r.delete(key)

    @patch(
        "cl.stats.metrics.METRICS_PREFIX",
        "test:collects_counters:prometheus:celery:",
    )
    def test_collects_task_execution_counters(self) -> None:
        """Test that collector reads task execution counters from Redis"""
        prefix = "test:collects_counters:prometheus:celery:"
        try:
            # Set up test data in Redis
            self.r.set(f"{prefix}task_total:my.task.name:success", 10)
            self.r.set(f"{prefix}task_total:my.task.name:failure", 2)
            self.r.set(f"{prefix}task_total:another.task:success", 5)

            collector = CeleryTaskMetricsCollector()
            metrics = list(collector.collect())

            # First yielded metric should be the counter
            counter = metrics[0]
            self.assertEqual(counter.name, "cl_celery_task_executions")

            # Check samples have correct labels and values
            samples_by_labels = {
                (s.labels["task"], s.labels["status"]): s.value
                for s in counter.samples
            }
            self.assertEqual(
                samples_by_labels[("my.task.name", "success")], 10
            )
            self.assertEqual(samples_by_labels[("my.task.name", "failure")], 2)
            self.assertEqual(samples_by_labels[("another.task", "success")], 5)
        finally:
            self._cleanup_keys(prefix)

    @patch(
        "cl.stats.metrics.METRICS_PREFIX",
        "test:collects_duration:prometheus:celery:",
    )
    def test_collects_task_duration_metrics(self) -> None:
        """Test that collector reads duration sum and count from Redis"""
        prefix = "test:collects_duration:prometheus:celery:"
        try:
            self.r.set(f"{prefix}task_duration_sum:my.task", "12.5")
            self.r.set(f"{prefix}task_duration_count:my.task", 5)
            self.r.set(f"{prefix}task_duration_sum:other.task", "3.25")
            self.r.set(f"{prefix}task_duration_count:other.task", 2)

            collector = CeleryTaskMetricsCollector()
            metrics = list(collector.collect())

            # Should yield 3 metrics: counter, duration_sum, duration_count
            self.assertEqual(len(metrics), 3)

            duration_sum = metrics[1]
            duration_count = metrics[2]

            self.assertEqual(
                duration_sum.name, "cl_celery_task_duration_seconds_sum"
            )
            self.assertEqual(
                duration_count.name, "cl_celery_task_duration_seconds_count"
            )

            # Check duration sum samples
            sum_by_task = {
                s.labels["task"]: s.value for s in duration_sum.samples
            }
            self.assertAlmostEqual(sum_by_task["my.task"], 12.5)
            self.assertAlmostEqual(sum_by_task["other.task"], 3.25)

            # Check duration count samples
            count_by_task = {
                s.labels["task"]: s.value for s in duration_count.samples
            }
            self.assertEqual(count_by_task["my.task"], 5)
            self.assertEqual(count_by_task["other.task"], 2)
        finally:
            self._cleanup_keys(prefix)

    @patch(
        "cl.stats.metrics.METRICS_PREFIX",
        "test:handles_bytes:prometheus:celery:",
    )
    def test_handles_byte_values_from_redis(self) -> None:
        """Test that collector handles bytes returned by Redis correctly.

        Python's int() and float() can handle byte strings like b"5" and
        b"1.5", so the collector works regardless of decode_responses setting.
        """
        prefix = "test:handles_bytes:prometheus:celery:"
        try:
            self.r.set(f"{prefix}task_total:byte.test:success", "42")
            self.r.set(f"{prefix}task_duration_sum:byte.test", "7.5")
            self.r.set(f"{prefix}task_duration_count:byte.test", "3")

            collector = CeleryTaskMetricsCollector()
            metrics = list(collector.collect())

            # Counter should have the correct value
            counter = metrics[0]
            sample = next(
                s for s in counter.samples if s.labels["task"] == "byte.test"
            )
            self.assertEqual(sample.value, 42)

            # Duration sum should have correct float value
            duration_sum = metrics[1]
            sum_sample = next(
                s
                for s in duration_sum.samples
                if s.labels["task"] == "byte.test"
            )
            self.assertAlmostEqual(sum_sample.value, 7.5)
        finally:
            self._cleanup_keys(prefix)

    @patch(
        "cl.stats.metrics.METRICS_PREFIX",
        "test:key_parsing:prometheus:celery:",
    )
    def test_key_parsing_extracts_task_name_and_status(self) -> None:
        """Test that rsplit correctly parses keys with colons in task names.

        Key format: {prefix}task_total:{task}:{status}
        Task names can contain colons (e.g., cl.audio.tasks:process_audio),
        so rsplit(":", 2) is used to only split the last two segments.
        """
        prefix = "test:key_parsing:prometheus:celery:"
        try:
            # Task name with a colon (simulating module path notation)
            self.r.set(
                f"{prefix}task_total:cl.audio.tasks:process_audio:success",
                15,
            )

            collector = CeleryTaskMetricsCollector()
            metrics = list(collector.collect())

            counter = metrics[0]
            # rsplit(":", 2) gives parts where parts[1]=task, parts[2]=status
            samples_by_labels = {
                (s.labels["task"], s.labels["status"]): s.value
                for s in counter.samples
            }
            self.assertEqual(
                samples_by_labels[("process_audio", "success")], 15
            )
        finally:
            self._cleanup_keys(prefix)

    @patch(
        "cl.stats.metrics.METRICS_PREFIX",
        "test:missing_count:prometheus:celery:",
    )
    def test_handles_missing_duration_count_key(self) -> None:
        """Test that collector handles missing duration count key gracefully.

        If task_duration_sum exists but task_duration_count doesn't,
        the collector should use 0 for the count.
        """
        prefix = "test:missing_count:prometheus:celery:"
        try:
            self.r.set(f"{prefix}task_duration_sum:orphan.task", "5.0")
            # Deliberately not setting task_duration_count:orphan.task

            collector = CeleryTaskMetricsCollector()
            metrics = list(collector.collect())

            duration_count = metrics[2]
            count_sample = next(
                (
                    s
                    for s in duration_count.samples
                    if s.labels["task"] == "orphan.task"
                ),
                None,
            )
            self.assertIsNotNone(count_sample)
            self.assertEqual(count_sample.value, 0)
        finally:
            self._cleanup_keys(prefix)

    @patch(
        "cl.stats.metrics.METRICS_PREFIX",
        "test:empty_redis:prometheus:celery:",
    )
    def test_handles_empty_redis(self) -> None:
        """Test that collector handles empty Redis gracefully"""
        prefix = "test:empty_redis:prometheus:celery:"
        try:
            # Ensure no keys exist with this prefix
            self._cleanup_keys(prefix)

            collector = CeleryTaskMetricsCollector()
            metrics = list(collector.collect())

            # Should still yield 3 metric families, but with no samples
            self.assertEqual(len(metrics), 3)
            for metric in metrics:
                self.assertEqual(len(metric.samples), 0)
        finally:
            self._cleanup_keys(prefix)

    @patch(
        "cl.stats.metrics.METRICS_PREFIX",
        "test:none_values:prometheus:celery:",
    )
    def test_handles_none_values(self) -> None:
        """Test that collector handles None/missing values with 'or 0'.

        The implementation uses `int(r.get(key) or 0)` and
        `float(r.get(key) or 0)` to handle cases where keys exist but have
        None values.
        """
        prefix = "test:none_values:prometheus:celery:"
        try:
            # Ensure no keys exist - r.get() will return None
            self._cleanup_keys(prefix)

            collector = CeleryTaskMetricsCollector()
            metrics = list(collector.collect())

            # Should not raise any errors
            self.assertEqual(len(metrics), 3)
        finally:
            self._cleanup_keys(prefix)

    def test_describe_returns_empty_list(self) -> None:
        """Test that describe() returns empty list for dynamic collector.

        Collectors that generate metrics dynamically at scrape time
        should return an empty list from describe() to avoid registration
        issues.
        """
        collector = CeleryTaskMetricsCollector()
        description = collector.describe()
        self.assertEqual(description, [])


class ValidateLabelsTests(TestCase):
    """Unit tests for _validate_labels helper function"""

    def test_valid_labels_pass(self) -> None:
        """Test that valid labels don't raise an error"""
        # Valid search.results labels
        _validate_labels(
            StatMetric.SEARCH_RESULTS,
            {"query_type": StatQueryType.KEYWORD, "method": StatMethod.WEB},
        )
        _validate_labels(
            StatMetric.SEARCH_RESULTS,
            {"query_type": StatQueryType.SEMANTIC, "method": StatMethod.API},
        )
        # Valid alerts.sent labels
        _validate_labels(
            StatMetric.ALERTS_SENT,
            {"alert_type": StatAlertType.DOCKET},
        )
        _validate_labels(
            StatMetric.ALERTS_SENT,
            {"alert_type": StatAlertType.RECAP},
        )

    def test_missing_labels_raise(self) -> None:
        """Test that missing labels raise ValueError"""
        with self.assertRaises(ValueError) as ctx:
            _validate_labels(
                StatMetric.SEARCH_RESULTS, {"query_type": "keyword"}
            )
        self.assertIn("must be", str(ctx.exception))

    def test_extra_labels_raise(self) -> None:
        """Test that extra labels raise ValueError"""
        with self.assertRaises(ValueError) as ctx:
            _validate_labels(
                StatMetric.SEARCH_RESULTS,
                {
                    "query_type": "keyword",
                    "method": "web",
                    "extra": "value",
                },
            )
        self.assertIn("must be", str(ctx.exception))

    def test_invalid_values_raise(self) -> None:
        """Test that invalid label values raise ValueError"""
        with self.assertRaises(ValueError) as ctx:
            _validate_labels(
                StatMetric.SEARCH_RESULTS,
                {"query_type": "invalid", "method": "web"},
            )
        self.assertIn("Invalid value", str(ctx.exception))
        self.assertIn("invalid", str(ctx.exception))


@pytest.mark.django_db
@override_switch("increment-stats", active=True)
class UpdatePrometheusStatTests(TestCase):
    """Unit tests for _update_prometheus_stat helper function"""

    def setUp(self):
        self.r = get_redis_interface("STATS")
        # Clean up any prometheus:stat: keys
        for key in self.r.scan_iter(f"{STAT_METRICS_PREFIX}*"):
            self.r.delete(key)

    def test_writes_key_without_labels(self) -> None:
        """Test that keys are written correctly without labels"""
        _update_prometheus_stat("test.metric", 5, None)

        key = f"{STAT_METRICS_PREFIX}test.metric"
        value = int(self.r.get(key) or 0)
        self.assertEqual(value, 5)

    def test_writes_key_with_labels(self) -> None:
        """Test that keys are written correctly with labels"""
        _update_prometheus_stat(
            StatMetric.SEARCH_RESULTS,
            3,
            {"query_type": "keyword", "method": "web"},
        )

        # Key should include label values in the order defined in STAT_LABELS
        key = f"{STAT_METRICS_PREFIX}search.results:keyword:web"
        value = int(self.r.get(key) or 0)
        self.assertEqual(value, 3)

    def test_increments_existing_key(self) -> None:
        """Test that the stat increments correctly"""
        _update_prometheus_stat(
            StatMetric.ALERTS_SENT,
            2,
            {"alert_type": "docket"},
        )
        _update_prometheus_stat(
            StatMetric.ALERTS_SENT,
            3,
            {"alert_type": "docket"},
        )

        key = f"{STAT_METRICS_PREFIX}alerts.sent:docket"
        value = int(self.r.get(key) or 0)
        self.assertEqual(value, 5)


@pytest.mark.django_db
@override_switch("increment-stats", active=True)
class StatMetricsCollectorTests(TestCase):
    """Unit tests for StatMetricsCollector"""

    def setUp(self):
        self.r = get_redis_interface("STATS")
        # Clean up any prometheus:stat: keys
        for key in self.r.scan_iter(f"{STAT_METRICS_PREFIX}*"):
            self.r.delete(key)

    def test_collects_metrics_from_redis(self) -> None:
        """Test that collector reads and formats metrics from Redis"""
        # Set up some test data in Redis
        key1 = f"{STAT_METRICS_PREFIX}search.results:keyword:web"
        key2 = f"{STAT_METRICS_PREFIX}search.results:semantic:api"
        key3 = f"{STAT_METRICS_PREFIX}alerts.sent:docket"
        self.r.set(key1, 10)
        self.r.set(key2, 5)
        self.r.set(key3, 20)

        # Verify keys were written
        self.assertEqual(int(self.r.get(key1)), 10)

        # Verify scan_iter finds the keys
        found_keys = list(self.r.scan_iter(f"{STAT_METRICS_PREFIX}*"))
        self.assertGreaterEqual(
            len(found_keys), 3, f"Expected 3+ keys, found: {found_keys}"
        )

        collector = StatMetricsCollector()
        metrics = list(collector.collect())

        # Find the search.results metric
        search_metric = next(
            (m for m in metrics if m.name == "cl_search_results"), None
        )
        self.assertIsNotNone(search_metric)

        # Should have at least 2 samples for search.results
        self.assertGreaterEqual(len(search_metric.samples), 2)

        # Check that our test values are present
        sample_values = {
            tuple(s.labels.values()): s.value for s in search_metric.samples
        }
        self.assertEqual(sample_values.get(("keyword", "web")), 10)
        self.assertEqual(sample_values.get(("semantic", "api")), 5)

        # Find the alerts.sent metric
        alerts_metric = next(
            (m for m in metrics if m.name == "cl_alerts_sent"), None
        )
        self.assertIsNotNone(alerts_metric)

        # Check that our test value is present
        alert_values = {
            tuple(s.labels.values()): s.value for s in alerts_metric.samples
        }
        self.assertEqual(alert_values.get(("docket",)), 20)

    def test_handles_empty_redis(self) -> None:
        """Test that collector handles empty Redis gracefully"""
        collector = StatMetricsCollector()
        metrics = list(collector.collect())
        self.assertEqual(len(metrics), 0)

    def test_registration_idempotent(self) -> None:
        """Ensure StatMetricsCollector registration is idempotent"""
        registry = CollectorRegistry()
        self.assertTrue(register_stat_metrics_collector(registry))
        self.assertFalse(register_stat_metrics_collector(registry))


@pytest.mark.django_db
@override_switch("increment-stats", active=True)
class TallyStatWithLabelsTests(TestCase):
    """Integration tests for tally_stat with labels"""

    def setUp(self):
        self.r = get_redis_interface("STATS")
        # Clean up test keys and search.results keys
        for pattern in ["test*", "search.results*", "alerts.sent*"]:
            keys = self.r.keys(pattern)
            if keys:
                self.r.delete(*keys)
        # Clean up prometheus keys
        for key in self.r.scan_iter(f"{STAT_METRICS_PREFIX}*"):
            self.r.delete(key)

    def test_tally_stat_with_labels_writes_both_keys(self) -> None:
        """Test that tally_stat writes both the date-based key and prometheus key"""
        tally_stat(
            StatMetric.SEARCH_RESULTS,
            labels={
                "query_type": StatQueryType.KEYWORD,
                "method": StatMethod.WEB,
            },
        )

        # Check date-based key exists (legacy format)
        date_key = f"{StatMetric.SEARCH_RESULTS}.{now().date().isoformat()}"
        date_value = int(self.r.get(date_key) or 0)
        self.assertEqual(date_value, 1)

        # Check prometheus key exists
        prom_key = f"{STAT_METRICS_PREFIX}search.results:keyword:web"
        prom_value = int(self.r.get(prom_key) or 0)
        self.assertEqual(prom_value, 1)

    def test_tally_stat_validates_labels(self) -> None:
        """Test that tally_stat validates labels before writing"""
        with self.assertRaises(ValueError):
            tally_stat(
                StatMetric.SEARCH_RESULTS,
                labels={"query_type": "invalid", "method": "web"},
            )
