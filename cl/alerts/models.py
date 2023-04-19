import pghistory
from django.contrib.auth.models import User
from django.db import models
from django.utils.crypto import get_random_string

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
        super(Alert, self).save(*args, **kwargs)


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
