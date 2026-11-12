"""Filters for a user's webhook events."""

from cl.api.models import WebhookEvent
from cl.api.utils import NoEmptyFilterSet


class WebhookEventViewFilter(NoEmptyFilterSet):
    """Filter webhook events by debug flag, status, and event type."""

    class Meta:
        model = WebhookEvent
        fields = {
            "debug": ["exact"],
            "event_status": ["exact"],
            "webhook__event_type": ["exact"],
        }
