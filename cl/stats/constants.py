"""Metric names, labels, and allowed label values for stats."""

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
    """Values of the ``query_type`` label."""

    KEYWORD = "keyword"
    SEMANTIC = "semantic"


class StatMethod(StrEnum):
    """Values of the ``method`` label."""

    WEB = "web"
    API = "api"


class StatAlertType(StrEnum):
    """Values of the ``alert_type`` label."""

    DOCKET = "docket"
    RECAP = "recap"
    SCHEDULED = "scheduled"


class StatWebhookEventType(StrEnum):
    """Values of the ``event_type`` label."""

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


def get_stat_metrics_prefix() -> str:
    """Get the prefix for stat metric keys from settings."""
    from django.conf import settings

    return settings.STAT_METRICS_PREFIX
