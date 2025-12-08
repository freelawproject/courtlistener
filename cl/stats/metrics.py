from collections.abc import Callable

from prometheus_client import Counter

search_queries_total = Counter(
    "cl_search_queries_total",
    "Total number of search queries",
    ["query_type", "method"],
)


def _inc(metric: Counter, inc: int, **kwargs):
    metric.labels(**kwargs).inc(inc)


def record_prometheus_metric(key, *args):
    PROMETHEUS_STAT_HANDLERS[key](*args)


PROMETHEUS_STAT_HANDLERS: dict[str, Callable[[int], None]] = {
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
}
