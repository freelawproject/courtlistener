import traceback
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
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
from cl.search.documents import AudioPercolator
from cl.search.models import SEARCH_TYPES
from cl.stats.utils import tally_stat
from cl.users.models import UserProfile


def send_alert_email(
    user_email: str, hits: list[tuple[Alert, str, list[dict[str, Any]], int]]
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
    document_id: str,
    document_index: str,
    from_index: int = 0,
) -> Response | None:
    """Percolate a document against a defined Elasticsearch Percolator query.

    :param document_id: The document ID in ES index to be percolated.
    :param document_index: The ES document index where the document lives.
    :param from_index: The ES from_ param for pagination.
    :return: The response from the Elasticsearch query or an empty list if an
    error occurred.
    """

    try:
        s = Search(index=AudioPercolator._index._name)
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
        s = s.source(excludes=["percolator_query"])
        s = s.extra(from_=from_index, size=settings.PERCOLATOR_PAGE_SIZE)
        # execute the percolator query.
        return s.execute()
    except (TransportError, ConnectionError, RequestError) as e:
        logger.warning(
            f"Error percolating a document id {document_id} from index {document_index}"
        )
        logger.warning(f"Error was: {e}")
        if settings.DEBUG is True:
            traceback.print_exc()
        return None


def send_search_alert_and_webhooks(
    user: User, hits: list[tuple[Alert, str, list[dict[str, Any]], int]]
) -> None:
    """Send alert emails and webhooks for a user.

    One email is sent per User and one webhook event is sent for every Alert
    per User.

    :param user: The user to whom the alerts should be sent.
    :param hits: A list of tuples containing the Alert, search type,
    documents, and number of documents.
    :return: None
    """

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


def process_percolator_response(
    percolator_response: Response, document_content: dict[str, Any]
) -> None:
    """Process the response from the percolator and handle alerts triggered by
     the percolator query.

    :param percolator_response: The response from the Elasticsearch percolator.
    :param document_content: The content of the document that triggered the
    alert.
    :return: None
    """

    for hit in percolator_response:
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
            with transaction.atomic(savepoint=True):
                try:
                    (
                        user_rate,
                        created,
                    ) = UserRateAlert.objects.select_for_update().get_or_create(
                        user=alert_triggered.user, rate=alert_triggered.rate
                    )
                except IntegrityError:
                    user_rate = UserRateAlert.objects.get(
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
            alert_user: UserProfile.user = alert_triggered.user
            not_donated_enough = (
                alert_user.profile.total_donated_last_year
                < settings.MIN_DONATION["rt_alerts"]
            )
            if not_donated_enough and alert_triggered.rate == Alert.REAL_TIME:
                logger.info(
                    "User: %s has not donated enough for their "
                    "RT alerts to be sent.\n" % alert_user
                )
                continue

            # Set highlight if available in response.
            if hasattr(hit.meta, "highlight"):
                merge_highlights_into_result(
                    hit.meta.highlight.to_dict(),
                    document_content,
                    ALERTS_HL_TAG,
                )
            qd = QueryDict(alert_triggered.query.encode(), mutable=True)
            hits = []
            search_type = qd.get("type", SEARCH_TYPES.OPINION)
            hits.append(
                (
                    alert_triggered,
                    search_type,
                    [document_content],
                    1,
                )
            )
            alert_triggered.date_last_hit = now()
            alert_triggered.save()
            send_search_alert_and_webhooks(alert_user, hits)

            tally_stat(f"alerts.sent.{Alert.REAL_TIME}", inc=1)
            logger.info(f"Sent {1} {Alert.REAL_TIME} email alerts.")


def send_or_schedule_alerts(
    document_id: str, document_index: str, document_content: dict[str, Any]
) -> None:
    """Send real-time alerts based on the Elasticsearch search response.

    Or schedule other rates alerts to send them later.

    Iterates through each hit in the search response, checks if the alert rate
    is real-time, and if the user has donated enough.If so it sends an email
    alert and triggers webhooks.

    :param document_id: The document ID in ES index to be percolated.
    :param document_index: The ES document index where the document lives.
    :param document_content: The document data that triggered the alert.
    :return: None
    """

    # Perform an initial percolator query and process its response.
    percolator_response = percolate_document(document_id, document_index)
    if not percolator_response:
        return
    process_percolator_response(percolator_response, document_content)
    # Check if the query contains more documents than PERCOLATOR_PAGE_SIZE.
    # If so, return additional results until there are not more.
    batch_size = settings.PERCOLATOR_PAGE_SIZE
    total_hits = percolator_response.hits.total.value
    results_returned = len(percolator_response.hits.hits)
    if total_hits > batch_size:
        documents_retrieved = results_returned
        from_index = batch_size
        while True:
            percolator_response = percolate_document(
                document_id, document_index, from_index=from_index
            )
            process_percolator_response(percolator_response, document_content)
            results_returned = len(percolator_response.hits.hits)
            documents_retrieved += results_returned
            # Check if all results have been retrieved. If so break the loop
            # Otherwise, increase from_index.
            if documents_retrieved >= total_hits or results_returned == 0:
                break
            else:
                from_index += batch_size
