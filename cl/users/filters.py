from cl.api.models import WebhookEvent
from cl.api.utils import NoEmptyFilterSet


class WebhookEventViewFilter(NoEmptyFilterSet):
    class Meta:
        model = WebhookEvent
        fields = {
            "debug": ["exact"],
            "event_status": ["exact"],
            "webhook__event_type": ["exact"],
        }
