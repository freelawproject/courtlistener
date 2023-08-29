import traceback
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from elasticsearch.exceptions import RequestError, TransportError
from elasticsearch_dsl import Q, Search
from elasticsearch_dsl.response import Response

from cl.alerts.models import Alert, DocketAlert
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import add_es_highlighting
from cl.search.documents import AudioPercolator
from cl.search.models import SEARCH_TYPES, Docket


@dataclass
class DocketAlertReportObject:
    da_alert: DocketAlert
    docket: Docket


class OldAlertReport:
    def __init__(self):
        self.old_alerts = []
        self.very_old_alerts = []
        self.disabled_alerts = []

    @property
    def old_dockets(self):
        return [obj.docket for obj in self.old_alerts]

    @property
    def very_old_dockets(self):
        return [obj.docket for obj in self.very_old_alerts]

    @property
    def disabled_dockets(self):
        return [obj.docket for obj in self.disabled_alerts]

    def total_count(self):
        return (
            len(self.old_alerts)
            + len(self.very_old_alerts)
            + len(self.disabled_alerts)
        )


class InvalidDateError(Exception):
    pass


def index_alert_document(
    alert: Alert, es_document=AudioPercolator
) -> bool | None:
    """Helper method to prepare and index an Alert object into Elasticsearch.

    :param alert: The Alert instance to be indexed.
    :param es_document: The Elasticsearch document percolator used for indexing
    the Alert instance.
    :return: Bool, True if document was properly indexed, otherwise None.
    """

    document = es_document()
    doc = document.prepare(alert)
    if not doc["percolator_query"]:
        return None
    doc_indexed = es_document(meta={"id": alert.pk}, **doc).save(
        skip_empty=True, refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH
    )
    if doc_indexed in ["created", "updated"]:
        return True
    return None


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
    search_after: int = 0,
) -> Response:
    """Percolate a document against a defined Elasticsearch Percolator query.

    :param document_id: The document ID in ES index to be percolated.
    :param document_index: The ES document index where the document lives.
    :param search_after: The ES search_after param for deep pagination.
    :return: The response from the Elasticsearch query.
    """

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
    s = s.sort("date_created")
    s = s[: settings.PERCOLATOR_PAGE_SIZE]
    if search_after:
        s = s.extra(search_after=search_after)
    return s.execute()
