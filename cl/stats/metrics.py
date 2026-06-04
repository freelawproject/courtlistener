import logging

from django.conf import settings
from prometheus_client import Counter, Histogram
from prometheus_client.core import (
    REGISTRY,
    CounterMetricFamily,
    GaugeMetricFamily,
)
from sentry_sdk import capture_exception

from cl.lib.celery_utils import get_queue_length
from cl.lib.redis_utils import get_redis_interface
from cl.stats.constants import STAT_LABELS, get_stat_metrics_prefix

logger = logging.getLogger(__name__)

# Search metrics
search_duration_seconds = Histogram(
    "cl_search_duration_seconds",
    "Duration of search query execution in seconds",
    ["query_type", "method"],
)
"""
Usage:
    search_duration_seconds.labels(query_type='keyword', method='web').observe(0.5)

Labels:
    query_type: 'keyword' | 'semantic'
    method: 'web' | 'api'
"""

# Account metrics
accounts_created_total = Counter(
    "cl_accounts_created_total",
    "Total number of accounts created",
)
"""
Usage:
    accounts_created_total.inc()
"""

accounts_deleted_total = Counter(
    "cl_accounts_deleted_total",
    "Total number of accounts deleted",
)
"""
Usage:
    accounts_deleted_total.inc()
"""


# Celery queue metrics (custom collector for multi-worker compatibility)
class CeleryQueueCollector:
    """Custom Prometheus collector for Celery queue lengths.

    This collector computes queue lengths at scrape time by querying Redis
    directly. This approach works correctly with multiple gunicorn workers
    since the values are fetched fresh on each scrape rather than stored
    in process-local memory.
    """

    def collect(self):
        gauge = GaugeMetricFamily(
            "cl_celery_queue_length",
            "Number of tasks in Celery queue",
            labels=["queue"],
        )
        for queue in settings.CELERY_QUEUES:
            try:
                length = get_queue_length(queue)
                gauge.add_metric([queue], length)
            except Exception as e:
                capture_exception(e)
        yield gauge


class StatMetricsCollector:
    """Collects tally_stat metrics from Redis for Prometheus."""

    def describe(self):
        return []

    def collect(self):
        r = get_redis_interface("STATS")

        # Collect all keys first, then fetch values in a single pipeline
        prefix = get_stat_metrics_prefix()
        keys = []
        parsed: list[tuple[str, list[str]]] = []
        for key in r.scan_iter(f"{prefix}*"):
            if isinstance(key, bytes):
                key = key.decode()
            parts = key.removeprefix(prefix).split(":")
            keys.append(key)
            parsed.append((parts[0], parts[1:] if len(parts) > 1 else []))

        if not keys:
            return

        values = r.mget(keys)

        # Group metrics by name
        metrics_data: dict[str, list[tuple[list[str], int]]] = {}
        for (metric_name, label_values), raw_value in zip(parsed, values):
            if metric_name not in metrics_data:
                metrics_data[metric_name] = []
            metrics_data[metric_name].append(
                (label_values, int(raw_value or 0))
            )

        # Yield a CounterMetricFamily for each metric
        for metric_name, data in metrics_data.items():
            label_names = STAT_LABELS.get(metric_name, [])

            # Convert dot notation to prometheus naming
            prom_name = f"cl_{metric_name.replace('.', '_')}_total"

            counter = CounterMetricFamily(
                prom_name,
                f"Total count of {metric_name}",
                labels=label_names,
            )

            for label_values, value in data:
                counter.add_metric(label_values, value)

            yield counter


def register_stat_metrics_collector(registry=REGISTRY) -> bool:
    """Register StatMetricsCollector once per registry."""
    if getattr(registry, "_cl_stat_metrics_collector_registered", False):
        return False
    registry.register(StatMetricsCollector())
    registry._cl_stat_metrics_collector_registered = True
    return True


def register_celery_queue_collector(registry=REGISTRY) -> bool:
    """Register CeleryQueueCollector once per registry."""
    if getattr(registry, "_cl_celery_queue_collector_registered", False):
        return False
    registry.register(CeleryQueueCollector())
    registry._cl_celery_queue_collector_registered = True
    return True


register_stat_metrics_collector()
register_celery_queue_collector()


def record_search_duration(
    duration_seconds: float, query_type: str, method: str
):
    """Record search query duration to the histogram.

    :param duration_seconds: The duration of the search query in seconds.
    :param query_type: The type of query ("semantic" or "keyword").
    :param method: The method of access ("web" or "api").
    """
    search_duration_seconds.labels(
        query_type=query_type, method=method
    ).observe(duration_seconds)
