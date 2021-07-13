from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Sum
from django.utils.timezone import now
from localflavor.us.models import USStateField

from cl.api.utils import invert_user_logs

donation_exclusion_codes = [
    1,  # Unknown error
    3,  # Cancelled
    6,  # Failed
    7,  # Reclaimed/Refunded
]


class BarMembership(models.Model):
    barMembership = USStateField(
        "the two letter state abbreviation of a bar membership"
    )

    def __str__(self) -> str:
        return self.get_barMembership_display()

    class Meta:
        verbose_name = "bar membership"
        ordering = ["barMembership"]


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        related_name="profile",
        verbose_name="the user this model extends",
        on_delete=models.CASCADE,
        unique=True,
    )
    barmembership = models.ManyToManyField(
        BarMembership,
        verbose_name="the bar memberships held by the user",
        blank=True,
    )
    stub_account = models.BooleanField(
        default=False,
    )
    employer = models.CharField(
        help_text="the user's employer",
        max_length=100,
        blank=True,
        null=True,
    )
    address1 = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )
    address2 = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )
    city = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )
    state = models.CharField(
        max_length=2,
        blank=True,
        null=True,
    )
    zip_code = models.CharField(
        max_length=10,
        blank=True,
        null=True,
    )
    avatar = models.ImageField(
        help_text="the user's avatar",
        upload_to="avatars/%Y/%m/%d",
        blank=True,
    )
    wants_newsletter = models.BooleanField(
        help_text="This user wants newsletters",
        default=False,
    )
    unlimited_docket_alerts = models.BooleanField(
        help_text="Should the user get unlimited docket alerts?",
        default=False,
    )
    plaintext_preferred = models.BooleanField(
        help_text="should the alert should be sent in plaintext",
        default=False,
    )
    activation_key = models.CharField(
        max_length=40,
    )
    key_expires = models.DateTimeField(
        help_text="The time and date when the user's activation_key expires",
        blank=True,
        null=True,
    )
    email_confirmed = models.BooleanField(
        help_text="The user has confirmed their email address",
        default=False,
    )
    notes = models.TextField(
        help_text="Any notes about the user.",
        blank=True,
    )
    is_tester = models.BooleanField(
        help_text="The user tests new features before they are finished",
        default=False,
    )

    @property
    def total_donated_last_year(self) -> Decimal:
        one_year_ago = now() - timedelta(days=365)
        total = (
            self.user.donations.filter(date_created__gte=one_year_ago)
            .exclude(status__in=donation_exclusion_codes)
            .aggregate(Sum("amount"))["amount__sum"]
        )
        if total is None:
            total = Decimal(0.0)
        return total

    @property
    def total_donated(self) -> Decimal:
        total = self.user.donations.exclude(
            status__in=donation_exclusion_codes
        ).aggregate(Sum("amount"))["amount__sum"]
        if total is None:
            total = Decimal(0.0)
        return total

    @property
    def is_monthly_donor(self) -> bool:
        """Does the profile have any monthly donations set up and running?

        :return bool: True if so, False if not.
        """
        return bool(self.user.monthly_donations.filter(enabled=True).count())

    @property
    def recent_api_usage(self) -> Dict[str, int]:
        """Get stats about API usage for the user for the past 14 days

        :return: A dict of date-count pairs indicating the amount of times the
        user has hit the API per day.
        :rtype: collections.OrderedDict
        """
        start = datetime.today() - timedelta(days=14)
        end = datetime.today()
        data = invert_user_logs(start, end, add_usernames=False)
        return data[self.user.pk]

    def __str__(self) -> str:
        return f"{self.user.username}"

    class Meta:
        verbose_name = "user profile"
        verbose_name_plural = "user profiles"
