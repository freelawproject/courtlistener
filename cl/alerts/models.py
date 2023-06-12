import traceback

import pghistory
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.http import QueryDict
from django.utils.crypto import get_random_string
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import RequestError, TransportError
from elasticsearch_dsl.connections import connections

from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import build_es_main_query
from cl.lib.models import AbstractDateTimeModel
from cl.lib.pghistory import AfterUpdateOrDeleteSnapshot
from cl.search.documents import AudioDocument, AudioPercolator
from cl.search.forms import SearchForm
from cl.search.models import SEARCH_TYPES, Docket


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class Alert(AbstractDateTimeModel):
    REAL_TIME = "rt"
    DAILY = "dly"
    WEEKLY = "wly"
    MONTHLY = "mly"
    OFF = "off"
    FREQUENCY = (
        (REAL_TIME, "Real Time"),
        (DAILY, "Daily"),
        (WEEKLY, "Weekly"),
        (MONTHLY, "Monthly"),
        (OFF, "Off"),
    )
    ALL_FREQUENCIES = [REAL_TIME, DAILY, WEEKLY, MONTHLY, OFF]
    user = models.ForeignKey(
        User,
        help_text="The user that created the item",
        related_name="alerts",
        on_delete=models.CASCADE,
    )
    date_last_hit = models.DateTimeField(
        verbose_name="time of last trigger", blank=True, null=True
    )
    name = models.CharField(verbose_name="a name for the alert", max_length=75)
    query = models.CharField(
        verbose_name="the text of an alert created by a user", max_length=2500
    )
    rate = models.CharField(
        verbose_name="the rate chosen by the user for the alert",
        choices=FREQUENCY,
        max_length=10,
    )
    secret_key = models.CharField(
        verbose_name="A key to be used in links to access the alert without "
        "having to log in. Can be used for a variety of "
        "purposes.",
        max_length=40,
    )
    es_id = models.CharField(
        verbose_name="The percolator query ID in Elasticsearch.",
        max_length=128,
        blank=True,
    )

    def __str__(self) -> str:
        return f"{self.pk}: {self.name}"

    class Meta:
        ordering = ["rate", "query"]
        indexes = [
            models.Index(fields=["es_id"]),
        ]

    def save(self, *args, **kwargs):
        """Ensure we get a token when we save the first time.
        Store the query in Elasticsearch percolator.
        """
        if self.pk is None:
            self.secret_key = get_random_string(length=40)
            if (
                f"type={SEARCH_TYPES.ORAL_ARGUMENT}" in self.query
                and self.rate == self.REAL_TIME
            ):
                # Make a dict from the query string.
                qd = QueryDict(self.query.encode(), mutable=True)
                cd = {}
                search_form = SearchForm(qd)
                if search_form.is_valid():
                    cd = search_form.cleaned_data
                search_query = AudioDocument.search()
                (
                    query,
                    total_query_results,
                    top_hits_limit,
                ) = build_es_main_query(search_query, cd)
                query_dict = query.to_dict()["query"]
                try:
                    percolator_query = AudioPercolator(
                        percolator_query=query_dict
                    )
                    percolator_query.save()
                    self.es_id = percolator_query.meta.id
                except (TransportError, ConnectionError, RequestError) as e:
                    logger.warning(
                        f"Error storing the query in percolator: {query_dict}"
                    )
                    logger.warning(f"Error was: {e}")
                    if settings.DEBUG is True:
                        traceback.print_exc()
        super(Alert, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Remove the query from Elasticsearch index before deleting the alert.
        if self.es_id:
            connections.create_connection(
                hosts=[
                    f"{settings.ELASTICSEARCH_DSL_HOST}:{settings.ELASTICSEARCH_DSL_PORT}"
                ],
                timeout=50,
            )
            es = Elasticsearch(
                f"{settings.ELASTICSEARCH_DSL_HOST}:{settings.ELASTICSEARCH_DSL_PORT}"
            )
            index_name = "oral_arguments_percolator"
            try:
                # Check if the document exists before deleting it
                if es.exists(index=index_name, id=self.es_id):
                    es.delete(index=index_name, id=self.es_id)
            except (TransportError, ConnectionError, RequestError) as e:
                logger.warning(
                    f"Error deleting the percolator query:{self.es_id}"
                )
                logger.warning(f"Error was: {e}")
                if settings.DEBUG is True:
                    traceback.print_exc()
        super().delete(*args, **kwargs)


class DocketAlertManager(models.Manager):
    def subscriptions(self):
        return self.filter(alert_type=DocketAlert.SUBSCRIPTION)


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class DocketAlert(AbstractDateTimeModel):
    UNSUBSCRIPTION = 0
    SUBSCRIPTION = 1
    TYPES = (
        (UNSUBSCRIPTION, "Unsubscription"),
        (SUBSCRIPTION, "Subscription"),
    )
    date_last_hit = models.DateTimeField(
        verbose_name="time of last trigger", blank=True, null=True
    )
    docket = models.ForeignKey(
        Docket,
        help_text="The docket that we are subscribed to.",
        related_name="alerts",
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        User,
        help_text="The user that is subscribed to the docket.",
        related_name="docket_alerts",
        on_delete=models.CASCADE,
    )
    secret_key = models.CharField(
        verbose_name="A key to be used in links to access the alert without "
        "having to log in. Can be used for a variety of "
        "purposes.",
        max_length=40,
    )
    alert_type = models.SmallIntegerField(
        help_text="The subscription type assigned, "
        "Unsubscription or Subscription.",
        default=SUBSCRIPTION,
        choices=TYPES,
    )
    objects = DocketAlertManager()

    class Meta:
        unique_together = ("docket", "user")

    def __str__(self) -> str:
        return f"{self.pk}: {self.docket_id}"

    def save(self, *args, **kwargs):
        """Ensure we get a token when we save the first time."""
        if self.pk is None:
            self.secret_key = get_random_string(length=40)
        super(DocketAlert, self).save(*args, **kwargs)


class RealTimeQueue(models.Model):
    """These are created any time a new item is added to our database.

    The idea here was, back in 2015, to keep a table of new items. Well, why is
    that necessary? Why can't we just keep track of the last time we ran alerts
    and then check the date_created field for the table? That'd be much easier.

    Also, this kind of thing should really use Django's contenttypes framework.

    Hindsight is 20/20, but we're here now.
    """

    date_modified = models.DateTimeField(
        help_text="the last moment when the item was modified",
        auto_now=True,
        db_index=True,
    )
    item_type = models.CharField(
        help_text="the type of item this is, one of: %s"
        % ", ".join(["%s (%s)" % (t[0], t[1]) for t in SEARCH_TYPES.NAMES]),
        max_length=3,
        choices=SEARCH_TYPES.NAMES,
        db_index=True,
    )
    item_pk = models.IntegerField(help_text="the pk of the item")
