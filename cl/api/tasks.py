import json

from elasticsearch.dsl.response import Hit
from rest_framework.renderers import JSONRenderer

from cl.alerts.api_serializers import SearchAlertSerializerModel
from cl.alerts.docket_alert_sources import RECAP_ALERT_SOURCE
from cl.alerts.models import Alert
from cl.api.models import (
    Webhook,
    WebhookEvent,
    WebhookEventType,
    WebhookVersions,
)
from cl.api.utils import generate_webhook_key_content
from cl.api.webhooks import send_webhook_event
from cl.celery_init import app
from cl.favorites.api_serializers import PrayerSerializer
from cl.favorites.models import Prayer
from cl.lib.elasticsearch_utils import set_child_docs_and_score
from cl.search.api_serializers import (
    OpinionClusterWebhookResultSerializer,
    RECAPESWebhookResultSerializer,
    V3OAESResultSerializer,
    V3OpinionESResultSerializer,
)
from cl.search.api_utils import ResultObject
from cl.search.models import SEARCH_TYPES, Docket
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
    d_pk: int | None = None,
) -> None:
    """POST the docket-alert payload to each recipient's enabled webhook.

    Entry pks are resolved through the docket's alert source so SCOTUS (and
    later state) rows are not looked up on DocketEntry, whose pks can collide.

    :param des_pks: Primary keys of the new docket entries to include.
    :param webhook_recipients_pks: User pks whose DOCKET_ALERT webhooks should
        receive the event.
    :param d_pk: Docket primary key used to select the alert source. None keeps
        the RECAP lookup so Celery messages queued before this argument existed
        still serialize correctly.
    :return: None
    """

    webhooks = Webhook.objects.filter(
        event_type=WebhookEventType.DOCKET_ALERT,
        user_id__in=webhook_recipients_pks,
        enabled=True,
    )
    source = (
        RECAP_ALERT_SOURCE
        if d_pk is None
        else Docket.objects.get(pk=d_pk).get_alert_source()
    )
    serialized_docket_entries = [
        source.webhook_serializer(de).data
        for de in source.entries_by_pk(des_pks)
    ]

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
def send_pray_and_pay_webhooks(prayer_pk: int, webhook_pk: int) -> None:
    """Send webhook event when a pray-and-pay request is granted.

    :param prayer_id: Primary key of the granted Prayer instance.
    :param webhook_id: Primary key of the Webhook to send the event to.
    :return: None
    """

    prayer = Prayer.objects.get(pk=prayer_pk)
    webhook = Webhook.objects.get(pk=webhook_pk)
    # Only send webhook for granted prayers
    if prayer.status != Prayer.GRANTED:
        return

    payload = PrayerSerializer(prayer).data
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
        case SEARCH_TYPES.OPINION:
            set_child_docs_and_score(results, merge_highlights=True)
            serializer_class = (
                V3OpinionESResultSerializer
                if webhook.version == WebhookVersions.v1
                else OpinionClusterWebhookResultSerializer
            )
            serialized_results = serializer_class(results, many=True).data
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
