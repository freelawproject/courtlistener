from django.contrib.auth.models import User
from django.db import models

FREQUENCY = (
    ('rt',  'Real Time'),
    ('dly', 'Daily'),
    ('wly', 'Weekly'),
    ('mly', 'Monthly'),
    ('off', 'Off'),
)

ITEM_TYPES = (
    ('o', 'Opinion'),
    ('oa', 'Oral Argument'),
)


class Alert(models.Model):
    user = models.ForeignKey(
        User,
        help_text="The user that created the item",
        related_name="alerts",
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        # auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified. A value in year"
                  " 1750 indicates the value is unknown",
        # auto_now=True,
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
    always_send_email = models.BooleanField(
        verbose_name='Always send an alert?',
        default=False
    )

    def __unicode__(self):
        return u'Alert %s: %s' % (self.pk, self.name)

    class Meta:
        ordering = ['rate', 'query']


class RealTimeQueue(models.Model):
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
