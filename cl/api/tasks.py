import json
from collections import defaultdict
from typing import Any

from elasticsearch_dsl.response import Hit
from rest_framework.renderers import JSONRenderer

from cl.alerts.api_serializers import SearchAlertSerializerModel
from cl.alerts.models import Alert
from cl.api.models import Webhook, WebhookEvent, WebhookEventType
from cl.api.utils import generate_webhook_key_content
from cl.api.webhooks import send_webhook_event
from cl.celery_init import app
from cl.corpus_importer.api_serializers import DocketEntrySerializer
from cl.lib.elasticsearch_utils import merge_highlights_into_result
from cl.search.api_serializers import (
    RECAPESResultSerializer,
    V3OAESResultSerializer,
)
from cl.search.api_utils import ResultObject
from cl.search.models import SEARCH_TYPES, DocketEntry


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
def send_es_search_alert_webhook(
    results: list[dict[str, Any]] | list[Hit],
    webhook_pk: int,
    alert_pk: int,
) -> None:
    """Send a search alert webhook event containing search results from a
    search alert object.

    :param results: The search results returned by SOLR for this alert.
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
        case SEARCH_TYPES.RECAP:
            for result in results:
                child_result_objects = []
                child_docs = None
                if isinstance(result, dict):
                    child_docs = result.get("child_docs")
                elif hasattr(result, "child_docs"):
                    child_docs = result.child_docs

                if child_docs:
                    for child_doc in child_docs:
                        if isinstance(result, dict):
                            child_result_objects.append(child_doc)
                        else:
                            child_result_objects.append(
                                defaultdict(
                                    lambda: None,
                                    child_doc["_source"].to_dict(),
                                )
                            )

                result["child_docs"] = child_result_objects
                # Merge HL into the parent document from percolator response.
                if isinstance(result, dict):
                    meta_hl = result.get("meta", {}).get("highlight", {})
                    merge_highlights_into_result(
                        meta_hl,
                        result,
                    )
            serialized_results = RECAPESResultSerializer(
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
