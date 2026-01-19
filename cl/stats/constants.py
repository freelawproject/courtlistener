from enum import StrEnum


class StatMetric(StrEnum):
    """Metric names for tally_stat."""

    SEARCH_RESULTS = "search.results"
    ALERTS_SENT = "alerts.sent"


# Label names per metric (order matters for key parsing)
# Uses string keys for reliable dict lookup in collector
STAT_LABELS: dict[str, list[str]] = {
    "search.results": ["query_type", "method"],
    "alerts.sent": ["alert_type"],
}


class StatQueryType(StrEnum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"


class StatMethod(StrEnum):
    WEB = "web"
    API = "api"


class StatAlertType(StrEnum):
    DOCKET = "docket"
    RECAP = "recap"
    SCHEDULED = "scheduled"


# For validation: allowed values per label
STAT_LABEL_VALUES: dict[str, type[StrEnum]] = {
    "query_type": StatQueryType,
    "method": StatMethod,
    "alert_type": StatAlertType,
}

STAT_METRICS_PREFIX = "prometheus:stat:"
