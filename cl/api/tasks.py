import json

from elasticsearch_dsl.response import Hit
from rest_framework.renderers import JSONRenderer

from cl.alerts.api_serializers import SearchAlertSerializerModel
from cl.alerts.models import Alert
from cl.api.models import Webhook, WebhookEvent, WebhookEventType
from cl.api.utils import generate_webhook_key_content
from cl.api.webhooks import send_webhook_event
from cl.celery_init import app
from cl.corpus_importer.api_serializers import DocketEntrySerializer
from cl.lib.elasticsearch_utils import set_child_docs_and_score
from cl.search.api_serializers import (
    RECAPESWebhookResultSerializer,
    V3OAESResultSerializer,
)
from cl.search.api_utils import ResultObject
from cl.search.models import SEARCH_TYPES, DocketEntry
from cl.search.types import ESDictDocument


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

    webhook = Webhook.objects.get(pk=webhook_pk)
    json_obj = json.loads(content_str)
    webhook_event = WebhookEvent.objects.create(
        webhook=webhook, content=json_obj, debug=True
    )
    send_webhook_event(webhook_event, content_str.encode("utf-8"))


@app.task()
def send_docket_alert_webhook_events(
    des_pks: list[int],
    webhook_recipients_pks: list[int],
) -> None:
    """POSTS the DocketAlert to the recipients webhook(s)

    :param des_pks: The list of docket entries primary keys.
    :param webhook_recipients_pks: A list of User pks to send the webhook to.
    :return: None
    """

    webhooks = Webhook.objects.filter(
        event_type=WebhookEventType.DOCKET_ALERT,
        user_id__in=webhook_recipients_pks,
        enabled=True,
    )
    docket_entries = DocketEntry.objects.filter(pk__in=des_pks)
    serialized_docket_entries = []
    for de in docket_entries:
        serialized_docket_entries.append(DocketEntrySerializer(de).data)

    for webhook in webhooks:
        post_content = {
            "webhook": generate_webhook_key_content(webhook),
            "payload": {
                "results": serialized_docket_entries,
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


@app.task()
def send_search_alert_webhook_es(
    results: list[ESDictDocument] | list[Hit],
    webhook_pk: int,
    alert_pk: int,
) -> None:
    """Send a search alert webhook event containing search results from a
    search alert object.

    :param results: The search results returned for this alert.
    :param webhook_pk: The webhook endpoint ID object to send the event to.
    :param alert_pk: The search alert ID.
    """

    webhook = Webhook.objects.get(pk=webhook_pk)
    alert = Alert.objects.get(pk=alert_pk)
    serialized_alert = SearchAlertSerializerModel(alert).data
    match alert.alert_type:
        case SEARCH_TYPES.ORAL_ARGUMENT:
            es_results = []
            for result in results:
                result["snippet"] = result["text"]
                es_results.append(ResultObject(initial=result))
            serialized_results = V3OAESResultSerializer(
                es_results, many=True
            ).data
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            set_child_docs_and_score(results, merge_highlights=True)
            serialized_results = RECAPESWebhookResultSerializer(
                results, many=True
            ).data
        case _:
            # No implemented alert type.
            return None

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
