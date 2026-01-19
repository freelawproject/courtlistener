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
from cl.stats.celery_metrics import METRICS_PREFIX
from cl.stats.constants import STAT_LABELS, STAT_METRICS_PREFIX

logger = logging.getLogger(__name__)

# Search metrics
search_queries_total = Counter(
    "cl_search_queries_total",
    "Total number of search queries",
    ["query_type", "method"],
)
"""
Usage:
    search_queries_total.labels(query_type='keyword', method='web').inc()
    search_queries_total.labels(query_type='semantic', method='api').inc()

Labels:
    query_type: 'keyword' | 'semantic'
    method: 'web' | 'api'
"""

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


class CeleryTaskMetricsCollector:
    """Collects Celery task metrics from Redis at scrape time.

    Works across multiple Celery workers since values are stored in
    Redis rather than process-local memory.
    """

    def describe(self):
        return []

    def collect(self):
        r = get_redis_interface("STATS")

        # Task execution counts by status
        counter = CounterMetricFamily(
            "cl_celery_task_executions_total",
            "Total Celery task executions",
            labels=["task", "status"],
        )
        for key in r.scan_iter(f"{METRICS_PREFIX}task_total:*"):
            # Key format: prometheus:celery:task_total:{task_name}:{status}
            parts = key.rsplit(":", 2)
            task_name, status = parts[1], parts[2]
            count = int(r.get(key) or 0)
            counter.add_metric([task_name, status], count)
        yield counter

        # Task duration (sum and count for computing averages in Prometheus)
        duration_sum = GaugeMetricFamily(
            "cl_celery_task_duration_seconds_sum",
            "Sum of task execution durations in seconds",
            labels=["task"],
        )
        duration_count = CounterMetricFamily(
            "cl_celery_task_duration_seconds_count",
            "Count of task executions (for duration averaging)",
            labels=["task"],
        )
        for key in r.scan_iter(f"{METRICS_PREFIX}task_duration_sum:*"):
            task_name = key.split(":")[-1]
            sum_val = float(r.get(key) or 0)
            count_key = f"{METRICS_PREFIX}task_duration_count:{task_name}"
            count_val = int(r.get(count_key) or 0)
            duration_sum.add_metric([task_name], sum_val)
            duration_count.add_metric([task_name], count_val)
        yield duration_sum
        yield duration_count


class StatMetricsCollector:
    """Collects tally_stat metrics from Redis for Prometheus."""

    def describe(self):
        return []

    def collect(self):
        r = get_redis_interface("STATS")

        # Group metrics by name
        metrics_data: dict[str, list[tuple[list[str], int]]] = {}

        for key in r.scan_iter(f"{STAT_METRICS_PREFIX}*"):
            # Handle bytes if redis returns them
            if isinstance(key, bytes):
                key = key.decode()
            # Parse: prometheus:stat:{name}:{label1}:{label2}...
            parts = key.removeprefix(STAT_METRICS_PREFIX).split(":")
            metric_name = parts[0]
            label_values = parts[1:] if len(parts) > 1 else []

            value = int(r.get(key) or 0)

            if metric_name not in metrics_data:
                metrics_data[metric_name] = []
            metrics_data[metric_name].append((label_values, value))

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
REGISTRY.register(CeleryTaskMetricsCollector())


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
