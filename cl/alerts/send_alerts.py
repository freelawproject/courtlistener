import traceback
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.http import QueryDict
from django.template import loader
from django.utils.timezone import now
from elasticsearch.exceptions import RequestError, TransportError
from elasticsearch_dsl import Q, Search
from elasticsearch_dsl.response import Response

from cl.alerts.models import (
    Alert,
    ParentAlert,
    ScheduledAlertHit,
    UserRateAlert,
)
from cl.api.models import WebhookEventType
from cl.api.webhooks import send_es_search_alert_webhook
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import (
    add_es_highlighting,
    merge_highlights_into_result,
)
from cl.search.constants import ALERTS_HL_TAG
from cl.search.models import SEARCH_TYPES
from cl.users.models import UserProfile


def send_alert_email(
    user_email: str, hits: list[list[Alert | str | list[dict[str, Any]] | int]]
) -> None:
    """Send an alert email to a specified user when there are new hits.

    :param user_email: The recipient's email address.
    :param hits: A list of hits to be included in the alert email.
    :return: None
    """
    subject = "New hits for your alerts"

    txt_template = loader.get_template("alert_email_es.txt")
    html_template = loader.get_template("alert_email_es.html")
    context = {"hits": hits}
    txt = txt_template.render(context)
    html = html_template.render(context)
    msg = EmailMultiAlternatives(
        subject, txt, settings.DEFAULT_ALERTS_EMAIL, [user_email]
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)


def percolate_document(
    document_id: str, document_index: str
) -> Response | list:
    """Percolate a document against a defined Elasticsearch Percolator query.

    :param document_id: The document ID in ES index to be percolated.
    :param document_index: The ES document index where the document lives.
    :return: The response from the Elasticsearch query or an empty list if an
    error occurred.
    """

    try:
        s = Search(index="oral_arguments_percolator")
        percolate_query = Q(
            "percolate",
            field="percolator_query",
            index=document_index,
            id=document_id,
        )
        s = s.query(percolate_query)
        s = add_es_highlighting(
            s, {"type": SEARCH_TYPES.ORAL_ARGUMENT}, alerts=True
        )
        # execute the percolator query.
        return s.execute()
    except (TransportError, ConnectionError, RequestError) as e:
        logger.warning(
            f"Error percolating a document id {document_id} from index {document_index}"
        )
        logger.warning(f"Error was: {e}")
        if settings.DEBUG is True:
            traceback.print_exc()
        return []


def send_search_alert_and_webhooks(user, hits):
    alert_user: UserProfile.user = user

    for alert, search_type, documents, num_docs in hits:
        user_webhooks = alert_user.webhooks.filter(
            event_type=WebhookEventType.SEARCH_ALERT, enabled=True
        )
        for user_webhook in user_webhooks:
            send_es_search_alert_webhook(
                documents,
                user_webhook,
                alert,
            )
    if len(hits) > 0:
        send_alert_email(alert_user.email, hits)


def send_or_schedule_alerts(
    response: Response, document_content: dict[str, Any]
) -> None:
    """Send real-time alerts based on the Elasticsearch search response.

    Or schedule other rates alerts to send them later.

    Iterates through each hit in the search response, checks if the alert rate
    is real-time, and if the user has donated enough.If so it sends an email
    alert and triggers webhooks.

    :param response: The response from the Elasticsearch percolate query.
    :param document_content: The document data that triggered the alert.
    :return: None
    """

    for hit in response:
        alert_triggered = (
            Alert.objects.filter(pk=hit.meta.id)
            .select_related(
                "user",
            )
            .first()
        )
        if not alert_triggered:
            continue

        # Schedule no RT Alerts.
        scheduled_rates = [Alert.DAILY, Alert.WEEKLY, Alert.MONTHLY]
        if alert_triggered.rate in scheduled_rates:
            with transaction.atomic():
                (
                    user_rate,
                    created,
                ) = UserRateAlert.objects.select_for_update().get_or_create(
                    user=alert_triggered.user, rate=alert_triggered.rate
                )
                parent_alert, created = ParentAlert.objects.get_or_create(
                    alert=alert_triggered, user_rate=user_rate
                )
                ScheduledAlertHit.objects.create(
                    parent_alert=parent_alert,
                    document_content=document_content,
                    highlighted_fields=hit.meta["highlight"].to_dict(),
                )

        # Send RT Alerts
        if alert_triggered.rate == Alert.REAL_TIME:
            # Set highlight if available in response.
            if hasattr(hit.meta, "highlight"):
                merge_highlights_into_result(
                    hit.meta.highlight.to_dict(),
                    document_content,
                    ALERTS_HL_TAG,
                )

            alert_user: UserProfile.user = alert_triggered.user
            qd = QueryDict(alert_triggered.query.encode(), mutable=True)
            hits = []
            search_type = qd.get("type", SEARCH_TYPES.OPINION)
            hits.append(
                [
                    alert_triggered,
                    search_type,
                    [document_content],
                    1,
                ]
            )
            alert_triggered.date_last_hit = now()
            alert_triggered.save()
            send_search_alert_and_webhooks(alert_user, hits)
