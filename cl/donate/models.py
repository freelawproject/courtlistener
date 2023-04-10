import pghistory
from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models

from cl.lib.models import AbstractDateTimeModel
from cl.lib.pghistory import AfterUpdateOrDeleteSnapshot


class PAYMENT_TYPES(object):
    DONATION = "donation"
    PAYMENT = "payment"
    BADGE_SIGNUP = "badge_signup"


class FREQUENCIES(object):
    ONCE = "once"
    MONTHLY = "monthly"
    NAMES = (
        (MONTHLY, "Monthly"),
        (ONCE, "Once"),
    )


class PROVIDERS(object):
    DWOLLA = "dwolla"
    PAYPAL = "paypal"
    CREDIT_CARD = "cc"
    CHECK = "check"
    BITCOIN = "bitcoin"
    NAMES = (
        (DWOLLA, "Dwolla"),
        (PAYPAL, "PayPal"),
        (CREDIT_CARD, "Credit Card"),
        (CHECK, "Check"),
        (BITCOIN, "Bitcoin"),
    )
    ACTIVE_NAMES = (
        (PAYPAL, "PayPal"),
        (CREDIT_CARD, "Credit Card"),
        (CHECK, "Check"),
    )


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class Donation(AbstractDateTimeModel):
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
    DISPUTED = 9
    DISPUTE_CLOSED = 10
    PAYMENT_STATUSES = (
        (AWAITING_PAYMENT, "Awaiting Payment"),
        (UNKNOWN_ERROR, "Unknown Error"),
        # This does not mean we get the money; must await "PROCESSED" for that.
        (COMPLETED_AWAITING_PROCESSING, "Completed, but awaiting processing"),
        (CANCELLED, "Cancelled"),
        (PROCESSED, "Processed"),  # Gold standard.
        (PENDING, "Pending"),
        (FAILED, "Failed"),
        (RECLAIMED_REFUNDED, "Reclaimed/Refunded"),
        (CAPTURED, "Captured"),
        (DISPUTED, "Disputed"),
        (DISPUTE_CLOSED, "Dispute closed"),
    )
    donor = models.ForeignKey(
        User,
        help_text="The user that made the donation",
        related_name="donations",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    clearing_date = models.DateTimeField(null=True, blank=True)
    send_annual_reminder = models.BooleanField(
        "Send me a reminder to donate again in one year",
        default=False,
    )
    min_docket_donation = settings.MIN_DONATION["docket_alerts"]
    min_donation_error = (
        f"Sorry, the minimum donation amount is ${min_docket_donation:0.2f}."
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=None,
        validators=[
            MinValueValidator(min_docket_donation, min_donation_error)
        ],
    )
    payment_provider = models.CharField(
        max_length=50, choices=PROVIDERS.NAMES, default=None
    )
    payment_id = models.CharField(
        help_text="Internal ID used during a transaction (used by PayPal and "
        "Stripe).",
        max_length=64,
    )
    transaction_id = models.CharField(
        help_text="The ID of a transaction made in PayPal.",
        max_length=64,
        null=True,
        blank=True,
    )
    status = models.SmallIntegerField(choices=PAYMENT_STATUSES)
    referrer = models.TextField("GET or HTTP referrer", blank=True)

    def __str__(self) -> str:
        return "%s: $%s, %s" % (
            self.get_payment_provider_display(),
            self.amount,
            self.get_status_display(),
        )

    class Meta:
        ordering = ["-date_created"]


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class MonthlyDonation(AbstractDateTimeModel):
    """The metadata needed to associate a monthly donation with a user."""

    donor = models.ForeignKey(
        User,
        help_text="The user that made the donation",
        related_name="monthly_donations",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    enabled = models.BooleanField(
        help_text="Is this monthly donation enabled?", default=True
    )
    payment_provider = models.CharField(max_length=50, choices=PROVIDERS.NAMES)
    monthly_donation_amount = models.DecimalField(
        max_digits=10, decimal_places=2
    )
    monthly_donation_day = models.SmallIntegerField(
        help_text="The day of the month that the monthly donation should be "
        "processed.",
    )
    stripe_customer_id = models.CharField(
        help_text="The ID of the Stripe customer object that we use to charge "
        "credit card users each month.",
        max_length=200,
    )
    failure_count = models.SmallIntegerField(
        help_text="The number of times this customer ID has failed. If a "
        "threshold is exceeded, we disable the subscription.",
        default=0,
    )

    def __str__(self) -> str:
        return "%s: $%s by %s" % (
            self.pk,
            self.monthly_donation_amount,
            self.get_payment_provider_display(),
        )
