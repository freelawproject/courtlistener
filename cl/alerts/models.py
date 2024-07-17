from datetime import datetime

import pghistory
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.http import QueryDict
from django.utils.crypto import get_random_string
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from cl.lib.models import AbstractDateTimeModel
from cl.lib.pghistory import AfterUpdateOrDeleteSnapshot
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
    alert_type = models.CharField(
        help_text="The type of search alert this is, one of: %s"
        % ", ".join(f"{t[0]} ({t[1]})" for t in SEARCH_TYPES.NAMES),
        max_length=3,
        choices=SEARCH_TYPES.NAMES,
        default=SEARCH_TYPES.OPINION,
    )
    secret_key = models.CharField(
        verbose_name="A key to be used in links to access the alert without "
        "having to log in. Can be used for a variety of "
        "purposes.",
        max_length=40,
    )

    def __str__(self) -> str:
        return f"{self.pk}: {self.name}"

    class Meta:
        ordering = ["rate", "query"]

    def save(self, *args, **kwargs):
        """Ensure we get a token when we save the first time."""
        if self.pk is None:
            self.secret_key = get_random_string(length=40)

        # Set the search type based on the provided query.
        qd = QueryDict(self.query.encode(), mutable=True)
        self.alert_type = qd.get("type", SEARCH_TYPES.OPINION)
        super().save(*args, **kwargs)


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
        super().save(*args, **kwargs)


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
        % ", ".join(f"{t[0]} ({t[1]})" for t in SEARCH_TYPES.NAMES),
        max_length=3,
        choices=SEARCH_TYPES.NAMES,
        db_index=True,
    )
    item_pk = models.IntegerField(help_text="the pk of the item")


class DateJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class SCHEDULED_ALERT_HIT_STATUS:
    """ScheduledAlertHit Status Types"""

    SCHEDULED = 0
    SENT = 1
    STATUS = (
        (SCHEDULED, "Alert Hit Scheduled"),
        (SENT, "Alert Hit Sent"),
    )


class ScheduledAlertHit(AbstractDateTimeModel):
    """Store alert hits triggered by a percolated document in Elasticsearch,to
    be sent later according to the user-defined rate.
    """

    alert = models.ForeignKey(
        Alert,
        help_text="The related Alert object.",
        related_name="scheduled_alert_hits",
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        User,
        help_text="The related User object.",
        related_name="scheduled_alert_hits",
        on_delete=models.CASCADE,
    )
    document_content = models.JSONField(  # type: ignore
        encoder=DateJSONEncoder,
        help_text="The content of the document at the moment it was added.",
    )
    hit_status = models.SmallIntegerField(
        help_text="The Scheduled Alert hit status.",
        default=SCHEDULED_ALERT_HIT_STATUS.SCHEDULED,
        choices=SCHEDULED_ALERT_HIT_STATUS.STATUS,
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveIntegerField(null=True)
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]
