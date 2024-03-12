import json
from typing import Any, Dict, List

from rest_framework.renderers import JSONRenderer

from cl.alerts.api_serializers import SearchAlertSerializerModel
from cl.alerts.models import Alert
from cl.api.models import Webhook, WebhookEvent, WebhookEventType
from cl.api.utils import generate_webhook_key_content
from cl.api.webhooks import send_webhook_event
from cl.celery_init import app
from cl.corpus_importer.api_serializers import DocketEntrySerializer
from cl.search.api_serializers import (
    OAESResultSerializer,
    OpinionClusterSerializerOffline,
    OpinionSerializerOffline,
)
from cl.search.api_utils import ResultObject
from cl.search.models import DocketEntry, Opinion, OpinionCluster


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


# -- Alert Webhook Events ----


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
def send_es_search_alert_webhook(
    results: list[dict[str, Any]],
    webhook_pk: int,
    alert: Alert,
) -> None:
    """Send a search alert webhook event containing search results from a
    search alert object.

    :param results: The search results returned by SOLR for this alert.
    :param webhook_pk: The webhook endpoint ID object to send the event to.
    :param alert: The search alert object.
    """

    webhook = Webhook.objects.get(pk=webhook_pk)
    serialized_alert = SearchAlertSerializerModel(alert).data
    es_results = []
    for result in results:
        result["snippet"] = result["text"]
        es_results.append(ResultObject(initial=result))
    serialized_results = OAESResultSerializer(es_results, many=True).data

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


# -- CRUD Webhook Events ----


@app.task()
def send_opinion_created_webhook(opinion: Opinion) -> None:
    """Send a webhook for each new opinion created

    :param opinion: The search opinion object.
    """
    for webhook in Webhook.objects.filter(
        event_type=WebhookEventType.OPINION_CREATE, enabled=True
    ):
        post_content = {
            "webhook": generate_webhook_key_content(webhook),
            "payload": OpinionSerializerOffline(opinion).data,
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
def send_opinions_deleted_webhook(ids: list[int]) -> None:
    """Send a webhook for the deleted opinion cluster

    :param ids: The list of ids deleted.
    """
    for webhook in Webhook.objects.filter(
        event_type=WebhookEventType.OPINION_DELETE, enabled=True
    ):
        post_content = {
            "webhook": generate_webhook_key_content(webhook),
            "payload": {"ids": ids},
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
def send_opinion_cluster_created_webhook(
    opinion_custer: OpinionCluster,
) -> None:
    """Send a webhook for the new opinion cluster created.

    :param opinion_custer: The opinion cluster object.
    """
    for webhook in Webhook.objects.filter(
        event_type=WebhookEventType.OPINION_CLUSTER_CREATE, enabled=True
    ):
        post_content = {
            "webhook": generate_webhook_key_content(webhook),
            "payload": OpinionClusterSerializerOffline(opinion_custer).data,
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
def send_opinion_clusters_deleted_webhook(ids: List[str]) -> None:
    """Send a webhook for deleted opinion cluster.

    :param id: The id of the deleted opinion cluster.
    """
    for webhook in Webhook.objects.filter(
        event_type=WebhookEventType.OPINION_CLUSTER_DELETE, enabled=True
    ):
        post_content = {
            "webhook": generate_webhook_key_content(webhook),
            "payload": {"ids": ids},
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
def send_opinion_cluster_updated_webhook(
    id: str, updated_fields: Dict[str, Any]
) -> None:
    """Send a webhook for updates to an opinion cluster.

    :param id: The id of the deleted opinion cluster.
    """
    for webhook in Webhook.objects.filter(
        event_type=WebhookEventType.OPINION_CLUSTER_UPDATE, enabled=True
    ):
        post_content = {
            "webhook": generate_webhook_key_content(webhook),
            "payload": {"id": id, "updated_fields": updated_fields},
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
