from datetime import date, timedelta
from typing import Self

import pghistory
from django.conf import settings
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from cl.lib.model_helpers import invert_choices_group_lookup
from cl.lib.models import AbstractDateTimeModel


class PAYMENT_TYPES:
    DONATION = "donation"
    PAYMENT = "payment"
    BADGE_SIGNUP = "badge_signup"


class FREQUENCIES:
    ONCE = "once"
    MONTHLY = "monthly"
    NAMES = (
        (MONTHLY, "Monthly"),
        (ONCE, "Once"),
    )


class PROVIDERS:
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


@pghistory.track()
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
        return f"{self.get_payment_provider_display()}: ${self.amount}, {self.get_status_display()}"

    class Meta:
        ordering = ["-date_created"]


@pghistory.track()
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
        return f"{self.pk}: ${self.monthly_donation_amount} by {self.get_payment_provider_display()}"


class NeonWebhookEvent(AbstractDateTimeModel):
    MEMBERSHIP_CREATION = 1
    MEMBERSHIP_EDIT = 2
    MEMBERSHIP_DELETE = 3
    MEMBERSHIP_UPDATE = 4
    TYPES = (
        (MEMBERSHIP_CREATION, "createMembership"),
        (MEMBERSHIP_EDIT, "editMembership"),
        (MEMBERSHIP_DELETE, "deleteMembership"),
        (MEMBERSHIP_UPDATE, "updateMembership"),
    )
    trigger = models.PositiveSmallIntegerField(
        help_text="Specifies the action that initiated this webhook event",
        choices=TYPES,
    )
    account_id = models.CharField(
        help_text="Unique identifier assigned by Neon CRM to a customer record",
        blank=True,
    )
    membership_id = models.CharField(
        help_text="Unique identifier assigned by Neon CRM to a membership record",
        blank=True,
    )
    content = models.JSONField(  # type: ignore
        encoder=DjangoJSONEncoder,
        help_text="The content of the payload of the POST request.",
    )


class MembershipPaymentStatus:
    PENDING = 0
    SUCCEEDED = 1
    FAILED = 2

    CHOICES = (
        (PENDING, "Awaiting payment processing"),
        (SUCCEEDED, "Payment successfully processed"),
        (FAILED, "Payment failed or was declined"),
    )


class NeonMembershipLevel:
    """Constants and choices for Neon membership levels."""

    # Individual memberships
    BASIC = 1
    LEGACY = 2
    TIER_1 = 3
    TIER_2 = 4
    TIER_3 = 5
    TIER_4 = 6
    LSO_1 = 7
    EDU = 9

    # Old group memberships
    GROUP_SMALLEST = 10
    GROUP_SMALL = 11
    GROUP_MEDIUM = 12
    GROUP_LARGE = 13
    GROUP_UNLIMITED = 14

    # Group memberships – Tier 1
    GROUP_T1_SMALLEST = 20
    GROUP_T1_SMALL = 21
    GROUP_T1_MEDIUM = 22
    GROUP_T1_LARGE = 23
    GROUP_T1_UNLIMITED = 24

    # Group memberships – Tier 2
    GROUP_T2_SMALLEST = 30
    GROUP_T2_SMALL = 31
    GROUP_T2_MEDIUM = 32
    GROUP_T2_LARGE = 33
    GROUP_T2_UNLIMITED = 34

    # Group memberships – Tier 3
    GROUP_T3_SMALLEST = 40
    GROUP_T3_SMALL = 41
    GROUP_T3_MEDIUM = 42
    GROUP_T3_LARGE = 43
    GROUP_T3_UNLIMITED = 44

    # Group memberships – Tier 4
    GROUP_T4_SMALLEST = 50
    GROUP_T4_SMALL = 51
    GROUP_T4_MEDIUM = 52
    GROUP_T4_LARGE = 53
    GROUP_T4_UNLIMITED = 54

    # HeyCounsel Memberships
    HEYCOUNSEL_T1 = 60
    HEYCOUNSEL_T2 = 61
    HEYCOUNSEL_T3 = 62
    HEYCOUNSEL_T4 = 63

    TYPES = (
        # Individual
        (BASIC, "CL Membership - Basic"),
        (LEGACY, "CL Legacy Membership"),
        (TIER_1, "CL Membership - Tier 1"),
        (TIER_2, "CL Membership - Tier 2"),
        (TIER_3, "CL Membership - Tier 3"),
        (TIER_4, "CL Membership - Tier 4"),
        (LSO_1, "LSO 1"),
        (EDU, "EDU Membership"),
        (GROUP_SMALLEST, "Group Membership - Smallest"),
        (GROUP_SMALL, "Group Membership - Small"),
        (GROUP_MEDIUM, "Group Membership - Medium"),
        (GROUP_LARGE, "Group Membership - Large"),
        (GROUP_UNLIMITED, "Group Membership - Unlimited"),
        # Group Tier 1
        (GROUP_T1_SMALLEST, "Group Tier 1 Membership - Smallest"),
        (GROUP_T1_SMALL, "Group Tier 1 Membership - Small"),
        (GROUP_T1_MEDIUM, "Group Tier 1 Membership - Medium"),
        (GROUP_T1_LARGE, "Group Tier 1 Membership - Large"),
        (GROUP_T1_UNLIMITED, "Group Tier 1 Membership - Unlimited"),
        # Group Tier 2
        (GROUP_T2_SMALLEST, "Group Tier 2 Membership - Smallest"),
        (GROUP_T2_SMALL, "Group Tier 2 Membership - Small"),
        (GROUP_T2_MEDIUM, "Group Tier 2 Membership - Medium"),
        (GROUP_T2_LARGE, "Group Tier 2 Membership - Large"),
        (GROUP_T2_UNLIMITED, "Group Tier 2 Membership - Unlimited"),
        # Group Tier 3
        (GROUP_T3_SMALLEST, "Group Tier 3 Membership - Smallest"),
        (GROUP_T3_SMALL, "Group Tier 3 Membership - Small"),
        (GROUP_T3_MEDIUM, "Group Tier 3 Membership - Medium"),
        (GROUP_T3_LARGE, "Group Tier 3 Membership - Large"),
        (GROUP_T3_UNLIMITED, "Group Tier 3 Membership - Unlimited"),
        # Group Tier 4
        (GROUP_T4_SMALLEST, "Group Tier 4 Membership - Smallest"),
        (GROUP_T4_SMALL, "Group Tier 4 Membership - Small"),
        (GROUP_T4_MEDIUM, "Group Tier 4 Membership - Medium"),
        (GROUP_T4_LARGE, "Group Tier 4 Membership - Large"),
        (GROUP_T4_UNLIMITED, "Group Tier 4 Membership - Unlimited"),
        # HeyCounsel
        (HEYCOUNSEL_T1, "HeyCounsel Tier 1"),
        (HEYCOUNSEL_T2, "HeyCounsel Tier 2"),
        (HEYCOUNSEL_T3, "HeyCounsel Tier 3"),
        (HEYCOUNSEL_T4, "HeyCounsel Tier 4"),
    )
    TYPES_INVERTED = invert_choices_group_lookup(TYPES)


class NeonMembershipQuerySet(models.QuerySet["NeonMembership"]):
    """QuerySet for NeonMembership that owns the shared "active" rule."""

    def active(self) -> Self:
        """Memberships that currently grant benefits, grace period included.

        Same rule as ``NeonMembership.is_active``: the payment status grants
        benefits and the termination date, taken in the current time zone,
        is on or after ``NeonMembership.benefits_cutoff_date()``. Use this
        instead of filtering on termination_date so ORM callers and Python
        callers can never disagree about who is a member.
        """
        # The ``__date`` lookup extracts the date in the current time zone,
        # matching ``timezone.localdate`` in ``is_active``.
        return self.filter(
            payment_status__in=NeonMembership.ACTIVE_PAYMENT_STATUSES
        ).filter(
            Q(termination_date__isnull=True)
            | Q(
                termination_date__date__gte=(
                    NeonMembership.benefits_cutoff_date()
                )
            )
        )


class NeonMembershipManager(models.Manager["NeonMembership"]):
    """Manager that exposes NeonMembershipQuerySet.active() on ``objects``.

    Written out instead of using ``QuerySet.as_manager()`` because the type
    checker can't see custom queryset methods behind that shortcut.
    """

    def get_queryset(self) -> NeonMembershipQuerySet:
        """Return a NeonMembershipQuerySet so its methods chain off ``objects``."""
        return NeonMembershipQuerySet(self.model, using=self._db)

    def active(self) -> NeonMembershipQuerySet:
        """See ``NeonMembershipQuerySet.active``."""
        return self.get_queryset().active()


@pghistory.track()
class NeonMembership(AbstractDateTimeModel):
    user = models.OneToOneField(
        User,
        related_name="membership",
        verbose_name="the user linked to the membership",
        on_delete=models.CASCADE,
        unique=True,
    )
    neon_id = models.CharField(
        help_text="Unique identifier assigned by Neon CRM to a membership record",
        blank=True,
    )
    level = models.PositiveSmallIntegerField(
        help_text="The current membership tier of a user within Neon CRM",
        choices=NeonMembershipLevel.TYPES,
    )
    termination_date = models.DateTimeField(
        help_text="The date a user's Neon membership will be terminated",
        blank=True,
        null=True,
    )
    payment_status = models.SmallIntegerField(
        choices=MembershipPaymentStatus.CHOICES,
        default=MembershipPaymentStatus.PENDING,
    )

    objects = NeonMembershipManager()

    # Payment statuses that grant membership benefits. PENDING ("waiting for
    # payment") is included so members keep access while a charge is still
    # processing; only an outright FAILED/declined payment revokes benefits.
    ACTIVE_PAYMENT_STATUSES = frozenset(
        {
            MembershipPaymentStatus.SUCCEEDED,
            MembershipPaymentStatus.PENDING,
        }
    )

    @classmethod
    def benefits_cutoff_date(cls) -> date:
        """Earliest termination date that still grants benefits today.

        Today's date in the current time zone minus the grace period
        (NEON_MEMBERSHIP_GRACE_PERIOD_DAYS), which keeps benefits going while
        a late renewal webhook or the daily Neon sync catches up. Shared by
        ``is_active`` and ``NeonMembershipQuerySet.active`` so the Python and
        SQL checks can't drift apart. Dates are compared as calendar days in
        the current time zone, so DST changes don't shorten the grace period.
        """
        grace = timedelta(days=settings.NEON_MEMBERSHIP_GRACE_PERIOD_DAYS)
        return timezone.localdate() - grace

    @property
    def is_active(self) -> bool:
        """Whether the membership currently grants benefits.

        Requires a payment status in ACTIVE_PAYMENT_STATUSES and a termination
        date on or after ``benefits_cutoff_date()``, or no termination date at
        all. ``NeonMembershipQuerySet.active`` applies the same rule in SQL.
        """
        if self.payment_status not in self.ACTIVE_PAYMENT_STATUSES:
            return False

        if not self.termination_date:
            return True

        return (
            timezone.localdate(self.termination_date)
            >= self.benefits_cutoff_date()
        )
