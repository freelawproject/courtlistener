import requests
from rest_framework.renderers import JSONRenderer
from scorched.response import SolrResponse

from cl.alerts.api_serializers import (
    DocketAlertSerializer,
    SearchAlertSerializerModel,
)
from cl.alerts.models import Alert
from cl.alerts.utils import OldAlertReport
from cl.api.models import Webhook, WebhookEvent
from cl.api.utils import (
    generate_webhook_key_content,
    update_webhook_event_after_request,
)
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.string_utils import trunc
from cl.recap.api_serializers import PacerFetchQueueSerializer
from cl.recap.models import PacerFetchQueue
from cl.search.api_serializers import SearchResultSerializer
from cl.search.api_utils import SolrObject


def send_webhook_event(
    webhook_event: WebhookEvent, content_bytes: bytes | None = None
) -> None:
    """Send the webhook POST request.

    :param webhook_event: An WebhookEvent to send.
    :param content_bytes: Optional, the bytes JSON content to send the first time
    the webhook is sent.
    """
    headers = {
        "Content-type": "application/json",
        "Idempotency-Key": str(webhook_event.event_id),
    }
    if content_bytes:
        json_bytes = content_bytes
    else:
        renderer = JSONRenderer()
        json_bytes = renderer.render(
            webhook_event.content,
            accepted_media_type="application/json;",
        )
    try:
        response = requests.post(
            webhook_event.webhook.url,
            data=json_bytes,
            timeout=(1, 1),
            stream=True,
            headers=headers,
            allow_redirects=False,
        )
        update_webhook_event_after_request(webhook_event, response)
    except (requests.ConnectionError, requests.Timeout) as exc:
        error_str = f"{type(exc).__name__}: {exc}"
        trunc(error_str, 500)
        update_webhook_event_after_request(webhook_event, error=error_str)


def send_old_alerts_webhook_event(
    webhook: Webhook, report: OldAlertReport
) -> None:
    """Send webhook event for old alerts

    :param webhook:The Webhook object to send the event to.
    :param report: A dict containing information about old alerts
    :return None
    """

    serialized_very_old_alerts = []
    serialized_disabled_alerts = []

    for very_old_alert in report.very_old_alerts:
        serialized_very_old_alerts.append(
            DocketAlertSerializer(very_old_alert.da_alert).data
        )

    for disabled_alert in report.disabled_alerts:
        serialized_disabled_alerts.append(
            DocketAlertSerializer(disabled_alert.da_alert).data
        )

    post_content = {
        "webhook": generate_webhook_key_content(webhook),
        "payload": {
            "old_alerts": serialized_very_old_alerts,
            "disabled_alerts": serialized_disabled_alerts,
        },
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
        "webhook": generate_webhook_key_content(webhook),
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


def send_search_alert_webhook(
    solr_interface: ExtraSolrInterface,
    results: SolrResponse,
    webhook: Webhook,
    alert: Alert,
) -> None:
    """Send a search alert webhook event containing search results from a
    search alert object.

    :param solr_interface: The ExtraSolrInterface object.
    :param results: The search results returned by SOLR for this alert.
    :param webhook: The webhook endpoint object to send the event to.
    :param alert: The search alert object.
    """

    serialized_alert = SearchAlertSerializerModel(alert).data
    solr_results = []
    for result in results.result.docs:
        # Pull the text snippet up a level
        result["snippet"] = "&hellip;".join(result["solr_highlights"]["text"])
        # This transformation is required before serialization so that null
        # fields are shown in the results, as in Search API.
        solr_results.append(SolrObject(initial=result))

    serialized_results = SearchResultSerializer(
        solr_results,
        many=True,
        context={"schema": solr_interface.schema},
    ).data

    post_content = {
        "webhook": generate_webhook_key_content(webhook),
        "payload": {
            "results": serialized_results,
            "alert": serialized_alert,
        },
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
