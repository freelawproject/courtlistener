from rest_framework.renderers import JSONRenderer

from cl.api.models import Webhook, WebhookEvent
from cl.api.utils import send_webhook_event
from cl.recap.api_serializers import PacerFetchQueueSerializer
from cl.recap.models import PacerFetchQueue


def send_recap_fetch_webhook_event(
    webhook: Webhook, fq: PacerFetchQueue
) -> None:
    """Send webhook event for processed PacerFetchQueue objects.

    :param webhook: The Webhook object to send the event to.
    :param fq: The PacerFetchQueue object related to the event.
    :return None
    """

    payload = PacerFetchQueueSerializer(fq).data
    post_content = {
        "webhook": {
            "event_type": webhook.event_type,
            "version": webhook.version,
            "date_created": webhook.date_created.isoformat(),
            "deprecation_date": None,
        },
        "payload": payload,
    }
    renderer = JSONRenderer()
    json_bytes = renderer.render(
        post_content,
        accepted_media_type="application/json;",
    )
    webhook_event = WebhookEvent.objects.create(
        webhook=webhook,
        content=post_content,
    )
    send_webhook_event(webhook_event, json_bytes)
