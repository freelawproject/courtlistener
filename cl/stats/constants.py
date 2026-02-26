from enum import StrEnum


class StatMetric(StrEnum):
    """Metric names for tally_stat."""

    SEARCH_RESULTS = "search.results"
    ALERTS_SENT = "alerts.sent"
    WEBHOOKS_SENT = "webhooks.sent"


# Label names per metric (order matters for key parsing)
# Uses string keys for reliable dict lookup in collector
STAT_LABELS: dict[str, list[str]] = {
    "search.results": ["query_type", "method"],
    "alerts.sent": ["alert_type"],
    "webhooks.sent": ["event_type"],
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


class StatWebhookEventType(StrEnum):
    DOCKET_ALERT = "docket_alert"
    SEARCH_ALERT = "search_alert"
    RECAP_FETCH = "recap_fetch"
    OLD_DOCKET_ALERTS_REPORT = "old_docket_alerts_report"
    PRAY_AND_PAY = "pray_and_pay"


# For validation: allowed values per label
STAT_LABEL_VALUES: dict[str, type[StrEnum]] = {
    "query_type": StatQueryType,
    "method": StatMethod,
    "alert_type": StatAlertType,
    "event_type": StatWebhookEventType,
}

STAT_METRICS_PREFIX = "prometheus:stat:"
