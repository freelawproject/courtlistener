from django.contrib.auth.models import User
from django.db import models
from django.utils.crypto import get_random_string


class Alert(models.Model):
    REAL_TIME = 'rt'
    DAILY = 'dly'
    WEEKLY = 'wly'
    MONTHLY = 'mly'
    OFF = 'off'
    FREQUENCY = (
        (REAL_TIME, 'Real Time'),
        (DAILY, 'Daily'),
        (WEEKLY, 'Weekly'),
        (MONTHLY, 'Monthly'),
        (OFF, 'Off'),
    )
    ALL_FREQUENCIES = [REAL_TIME, DAILY, WEEKLY, MONTHLY, OFF]
    user = models.ForeignKey(
        User,
        help_text="The user that created the item",
        related_name="alerts",
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified. A value in year"
                  " 1750 indicates the value is unknown",
        auto_now=True,
        db_index=True,
    )
    date_last_hit = models.DateTimeField(
        verbose_name='time of last trigger',
        blank=True,
        null=True
    )
    name = models.CharField(
        verbose_name='a name for the alert',
        max_length=75
    )
    query = models.CharField(
        verbose_name='the text of an alert created by a user',
        max_length=2500
    )
    rate = models.CharField(
        verbose_name='the rate chosen by the user for the alert',
        choices=FREQUENCY,
        max_length=10
    )
    secret_key = models.CharField(
        verbose_name="A key to be used in links to access the alert without "
                     "having to log in. Can be used for a variety of "
                     "purposes.",
        max_length=40,
    )

    def __unicode__(self):
        return u'Alert %s: %s' % (self.pk, self.name)

    class Meta:
        ordering = ['rate', 'query']

    def save(self, *args, **kwargs):
        """Ensure we get a token when we save the first time."""
        if self.pk is None:
            self.secret_key = get_random_string(length=40)
        super(Alert, self).save(*args, **kwargs)


class RealTimeQueue(models.Model):
    OPINION = 'o'
    ORAL_ARGUMENT = 'oa'
    ITEM_TYPES = (
        (OPINION, 'Opinion'),
        (ORAL_ARGUMENT, 'Oral Argument'),
    )
    ALL_ITEM_TYPES = [OPINION, ORAL_ARGUMENT]
    date_modified = models.DateTimeField(
        help_text='the last moment when the item was modified',
        auto_now=True,
        db_index=True,
    )
    item_type = models.CharField(
        help_text='the type of item this is, one of: %s' %
                  ', '.join(['%s (%s)' % (t[0], t[1]) for t in ITEM_TYPES]),
        max_length=3,
        choices=ITEM_TYPES,
        db_index=True,
    )
    item_pk = models.IntegerField(
        help_text='the pk of the item',
    )
