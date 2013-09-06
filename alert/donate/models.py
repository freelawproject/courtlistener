from django.db import models
from datetime import date

PROVIDERS = (
    ('dwolla', 'Dwolla'),
    ('paypal', 'PayPal'),
    ('cc', 'Credit Card'),
    ('check', 'Check'),
)
PAYMENT_STATUSES = (
    (0, 'AWAITING_PAYMENT'),
    (1, 'UNKNOWN_ERROR'),
    (2, 'COMPLETED'),  # This does not mean we get the money, must await "PROCESSED" for that.
    (3, 'CANCELLED'),
    (4, 'PROCESSED'),
    (5, 'PENDING'),
    (6, 'FAILED'),
    (7, 'RECLAIMED'),
)


class Donation(models.Model):
    date_modified = models.DateTimeField(
        auto_now=True,
        editable=False,
        db_index=True,
    )
    date_created = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        db_index=True
    )
    clearing_date = models.DateTimeField(
        null=True,
        blank=True,
    )
    send_annual_reminder = models.BooleanField(
        'Send me a reminder to donate again in one year',
        default=False,
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=None,
    )
    payment_provider = models.CharField(
        max_length=50,
        choices=PROVIDERS,
        default=None,
    )
    payment_id = models.CharField(
        'Internal ID used during a transaction',
        max_length=64,
    )
    transaction_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
    )
    status = models.SmallIntegerField(
        max_length=2,
        choices=PAYMENT_STATUSES,
    )
    referrer = models.TextField(
        'GET or HTTP referrer',
        blank=True,
    )

    def __unicode__(self):
        return '%s: $%s, %s' % (self.get_payment_provider_display(), self.amount, self.get_status_display())
