import json

from cl.api.models import Webhook, WebhookEvent
from cl.api.utils import send_webhook_event
from cl.celery_init import app


@app.task()
def send_test_webhook_event(
    webhook_pk: int,
    content_str: str,
) -> None:
    """POSTS the test webhook event.

    :param webhook_pk: The webhook primary key.
    :param content_str: The str content to POST.
    :return: None
    """

    # Only send the webhook event to users for whom this isn't their first
    # notification for the case or if it's, only sends it if auto_subscribe is
    # turned on.

    webhook = Webhook.objects.get(pk=webhook_pk)
    json_obj = json.loads(content_str)
    webhook_event = WebhookEvent.objects.create(
        webhook=webhook, content=json_obj, debug=True
    )
    send_webhook_event(webhook_event, content_str)
