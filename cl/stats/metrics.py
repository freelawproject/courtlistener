import logging
from collections.abc import Callable

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

search_duration_seconds = Histogram(
    "cl_search_duration_seconds",
    "Duration of search query execution in seconds",
    ["query_type", "method"],
)

# Alert metrics
alerts_sent_total = Counter(
    "cl_alerts_sent_total",
    "Total number of alerts sent",
    ["alert_type"],
)

# Webhook metrics
webhooks_sent_total = Counter(
    "cl_webhooks_sent_total",
    "Total number of webhooks sent",
    ["event_type"],
)

# Account metrics
accounts_created_total = Counter(
    "cl_accounts_created_total",
    "Total number of accounts created",
)

accounts_deleted_total = Counter(
    "cl_accounts_deleted_total",
    "Total number of accounts deleted",
)


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


def _inc(metric: Counter, inc: int, **kwargs):
    """Increment a Counter metric with labels."""
    metric.labels(**kwargs).inc(inc)


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


def record_prometheus_metric(key, *args):
    PROMETHEUS_STAT_HANDLERS[key](*args)


PROMETHEUS_STAT_HANDLERS: dict[str, Callable[[int], None]] = {
    # Search query metrics
    "search.queries.semantic.web": lambda inc: _inc(
        search_queries_total, inc, query_type="semantic", method="web"
    ),
    "search.queries.keyword.web": lambda inc: _inc(
        search_queries_total, inc, query_type="keyword", method="web"
    ),
    "search.queries.semantic.api": lambda inc: _inc(
        search_queries_total, inc, query_type="semantic", method="api"
    ),
    "search.queries.keyword.api": lambda inc: _inc(
        search_queries_total, inc, query_type="keyword", method="api"
    ),
    # Alert metrics
    "alerts.sent.search": lambda inc: _inc(
        alerts_sent_total, inc, alert_type="search_alert"
    ),
    "alerts.sent.docket": lambda inc: _inc(
        alerts_sent_total, inc, alert_type="docket_alert"
    ),
    # Webhook metrics
    "webhooks.sent.docket_alert": lambda inc: _inc(
        webhooks_sent_total, inc, event_type="docket_alert"
    ),
    "webhooks.sent.search_alert": lambda inc: _inc(
        webhooks_sent_total, inc, event_type="search_alert"
    ),
    "webhooks.sent.recap_fetch": lambda inc: _inc(
        webhooks_sent_total, inc, event_type="recap_fetch"
    ),
    "webhooks.sent.old_docket_alerts_report": lambda inc: _inc(
        webhooks_sent_total, inc, event_type="old_docket_alerts_report"
    ),
    "webhooks.sent.pray_and_pay": lambda inc: _inc(
        webhooks_sent_total, inc, event_type="pray_and_pay"
    ),
    # Account metrics
    "accounts.created": lambda inc: accounts_created_total.inc(inc),
    "accounts.deleted": lambda inc: accounts_deleted_total.inc(inc),
}
