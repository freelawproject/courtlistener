import logging

from django.conf import settings
from prometheus_client import Counter, Histogram
from prometheus_client.core import REGISTRY, GaugeMetricFamily

from cl.lib.celery_utils import get_queue_length

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

# Alert metrics
alerts_sent_total = Counter(
    "cl_alerts_sent_total",
    "Total number of alerts sent",
    ["alert_type"],
)
"""
Usage:
    alerts_sent_total.labels(alert_type='search_alert').inc()
    alerts_sent_total.labels(alert_type='docket_alert').inc(5)

Labels:
    alert_type: 'search_alert' | 'docket_alert'
"""

# Webhook metrics
webhooks_sent_total = Counter(
    "cl_webhooks_sent_total",
    "Total number of webhooks sent",
    ["event_type"],
)
"""
Usage:
    webhooks_sent_total.labels(event_type='docket_alert').inc()

Labels:
    event_type: 'docket_alert' | 'search_alert' | 'recap_fetch' |
                'old_docket_alerts_report' | 'pray_and_pay'
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
            except Exception:
                logger.exception(
                    "Failed to get queue length for %s",
                    queue,
                )
        yield gauge


def register_celery_queue_collector(registry=REGISTRY) -> bool:
    """Register CeleryQueueCollector once per registry."""
    if getattr(registry, "_cl_celery_queue_collector_registered", False):
        return False
    registry.register(CeleryQueueCollector())
    registry._cl_celery_queue_collector_registered = True
    return True


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
