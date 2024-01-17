from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.http import QueryDict
from elasticsearch_dsl import Q, Search
from elasticsearch_dsl.response import Response

from cl.alerts.models import (
    SCHEDULED_ALERT_HIT_STATUS,
    Alert,
    DocketAlert,
    ScheduledAlertHit,
)
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import add_es_highlighting
from cl.search.documents import AudioPercolator
from cl.search.models import SEARCH_TYPES, Docket
from cl.users.models import UserProfile


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
    exclude_rate_off = Q("term", rate=Alert.OFF)
    final_query = Q(
        "bool",
        must=[percolate_query],
        must_not=[exclude_rate_off],
    )
    s = s.query(final_query)
    s = add_es_highlighting(
        s, {"type": SEARCH_TYPES.ORAL_ARGUMENT}, alerts=True
    )
    s = s.source(excludes=["percolator_query"])
    s = s.sort("date_created")
    s = s[: settings.ELASTICSEARCH_PAGINATION_BATCH_SIZE]
    if search_after:
        s = s.extra(search_after=search_after)
    return s.execute()


def user_has_donated_enough(
    alert_user: UserProfile.user, alerts_count: int
) -> bool:
    """Check if a user has donated enough to receive real-time alerts.

    :param alert_user: The user object associated with the alerts.
    :param alerts_count: The number of real-time alerts triggered for the user.
    :return: True if the user has donated enough, otherwise False.
    """

    not_donated_enough = (
        alert_user.profile.total_donated_last_year
        < settings.MIN_DONATION["rt_alerts"]
    )
    if not_donated_enough:
        logger.info(
            "User: %s has not donated enough for their %s "
            "RT alerts to be sent.\n" % (alert_user, alerts_count)
        )
        return False
    return True


def override_alert_query(
    alert: Alert, cut_off_date: date | None = None
) -> QueryDict:
    """Override the query parameters for a given alert based on its type and an
     optional cut-off date.

    :param alert: The Alert object for which the query will be overridden.
    :param cut_off_date: An optional date used to set a threshold in the query.
    :return: A QueryDict object containing the modified query parameters.
    """

    qd = QueryDict(alert.query.encode(), mutable=True)
    if alert.alert_type == SEARCH_TYPES.ORAL_ARGUMENT:
        qd["order_by"] = "dateArgued desc"
        if cut_off_date:
            qd["argued_after"] = cut_off_date.strftime("%m/%d/%Y")
    else:
        qd["order_by"] = "dateFiled desc"
        if cut_off_date:
            qd["filed_after"] = cut_off_date.strftime("%m/%d/%Y")

    return qd


def alert_hits_limit_reached(alert_pk: int, user_pk: int) -> bool:
    """Check if the alert hits limit has been reached for a specific alert-user
     combination.

    :param alert_pk: The alert_id.
    :param user_pk: The user_id.
    :return: True if the limit has been reached, otherwise False.
    """

    stored_hits = ScheduledAlertHit.objects.filter(
        alert_id=alert_pk,
        user_id=user_pk,
        hit_status=SCHEDULED_ALERT_HIT_STATUS.SCHEDULED,
    )
    hits_count = stored_hits.count()
    if hits_count >= settings.SCHEDULED_ALERT_HITS_LIMIT:
        logger.info(
            f"Skipping hit for Alert ID: {alert_pk}, there are {hits_count} hits stored for this alert."
        )
        return True
    return False
