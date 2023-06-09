import traceback
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.http import QueryDict
from django.template import loader
from django.utils.timezone import now
from elasticsearch.exceptions import RequestError, TransportError
from elasticsearch_dsl import Search
from elasticsearch_dsl.response import Response
from elasticsearch_dsl.utils import AttrDict

from cl.alerts.models import Alert
from cl.api.models import WebhookEventType
from cl.api.webhooks import send_es_search_alert_webhook
from cl.lib.command_utils import logger
from cl.search.documents import AudioDocument
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


def percolate_document(document_data: AttrDict) -> Response | list:
    """Percolate a document against a defined Elasticsearch Percolator query.

    :param document_data: The document data to be used for the percolate query.
    :return: The response from the Elasticsearch query or an empty list if an
    error occurred.
    """

    try:
        s = Search(index="oral_arguments")
        s = s.query(
            "percolate", field="percolator_query", document=document_data
        )
        # execute the search
        return s.execute()
    except (TransportError, ConnectionError, RequestError) as e:
        logger.warning(
            f"Error percolating a document: {document_data.to_dict()}"
        )
        logger.warning(f"Error was: {e}")
        if settings.DEBUG is True:
            traceback.print_exc()
        return []


def send_rt_alerts(response: Response, document_data: AttrDict) -> None:
    """Send real-time alerts based on the Elasticsearch search response.

    Iterates through each hit in the search response, checks if the alert rate
    is real-time, and if the user has donated enough.If so it sends an email
    alert and triggers webhooks.

    :param response: The response from the Elasticsearch percolate query.
    :param document_data: The document data that triggered the alert.
    :return: None
    """

    for hit in response:
        es_id = hit.meta.id
        alert_triggered = (
            Alert.objects.filter(es_id=es_id)
            .select_related(
                "user",
            )
            .first()
        )
        if not alert_triggered:
            continue

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
        qd = QueryDict(alert_triggered.query.encode(), mutable=True)
        if alert_triggered.rate == Alert.REAL_TIME:
            hits = []
            search_type = qd.get("type", SEARCH_TYPES.OPINION)
            hits.append(
                [
                    alert_triggered,
                    search_type,
                    [document_data.to_dict()],
                    len([document_data.to_dict()]),
                ]
            )
            alert_triggered.date_last_hit = now()
            alert_triggered.save()

            user_webhooks = alert_user.webhooks.filter(
                event_type=WebhookEventType.SEARCH_ALERT, enabled=True
            )
            for user_webhook in user_webhooks:
                send_es_search_alert_webhook(
                    AudioDocument._index.get_mapping(),
                    [document_data],
                    user_webhook,
                    alert_triggered,
                )
            if len(hits) > 0:
                send_alert_email(alert_user.email, hits)
