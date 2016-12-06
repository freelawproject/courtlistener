from django.contrib.auth.models import User
from django.db import models


class Donation(models.Model):
    # These statuses are shown on the profile page. Be warned.
    AWAITING_PAYMENT = 0
    UNKNOWN_ERROR = 1
    COMPLETED_AWAITING_PROCESSING = 2
    CANCELLED = 3
    PROCESSED = 4
    PENDING = 5
    FAILED = 6
    RECLAIMED_REFUNDED = 7
    CAPTURED = 8
    PAYMENT_STATUSES = (
        (AWAITING_PAYMENT, 'Awaiting Payment'),
        (UNKNOWN_ERROR, 'Unknown Error'),
        # This does not mean we get the money; must await "PROCESSED" for that.
        (COMPLETED_AWAITING_PROCESSING, 'Completed, but awaiting processing'),
        (CANCELLED, 'Cancelled'),
        (PROCESSED, 'Processed'),  # Gold standard.
        (PENDING, 'Pending'),
        (FAILED, 'Failed'),
        (RECLAIMED_REFUNDED, 'Reclaimed/Refunded'),
        (CAPTURED, 'Captured'),
    )
    DWOLLA = 'dwolla'
    PAYPAL = 'paypal'
    CREDIT_CARD = 'cc'
    CHECK = 'check'
    PROVIDERS = (
        (DWOLLA, 'Dwolla'),
        (PAYPAL, 'PayPal'),
        (CREDIT_CARD, 'Credit Card'),
        (CHECK, 'Check'),
    )
    donor = models.ForeignKey(
        User,
        help_text="The user that made the donation",
        related_name="donations",
    )
    date_modified = models.DateTimeField(
        auto_now=True,
        db_index=True,
    )
    date_created = models.DateTimeField(
        auto_now_add=True,
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
        choices=PAYMENT_STATUSES,
    )
    referrer = models.TextField(
        'GET or HTTP referrer',
        blank=True,
    )

    def __unicode__(self):
        return u'%s: $%s, %s' % (
            self.get_payment_provider_display(),
            self.amount,
            self.get_status_display()
        )

    class Meta:
        ordering = ['-date_created']
