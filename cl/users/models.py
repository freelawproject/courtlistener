import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict

from django.contrib.auth.models import User
from django.core.exceptions import FieldError
from django.db import models
from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now
from localflavor.us.models import USStateField

from cl.api.utils import invert_user_logs
from cl.lib.models import AbstractDateTimeModel

donation_exclusion_codes = [
    1,  # Unknown error
    3,  # Cancelled
    6,  # Failed
    7,  # Reclaimed/Refunded
]


class SUB_TYPES(object):
    """SNS Event Subtypes"""

    UNDETERMINED = 0
    GENERAL = 1
    NOEMAIL = 2
    SUPPRESSED = 3
    ONACCOUNTSUPPRESSIONLIST = 4
    MAILBOXFULL = 5
    MESSAGETOOLARGE = 6
    CONTENTREJECTED = 7
    ATTACHMENTREJECTED = 8
    COMPLAINT = 9
    OTHER = 10

    TYPES = (
        (UNDETERMINED, "Undetermined"),
        (GENERAL, "General"),
        (NOEMAIL, "NoEmail"),
        (SUPPRESSED, "Suppressed"),
        (ONACCOUNTSUPPRESSIONLIST, "OnAccountSuppressionList"),
        (MAILBOXFULL, "MailboxFull"),
        (MESSAGETOOLARGE, "MessageTooLarge"),
        (CONTENTREJECTED, "ContentRejected"),
        (ATTACHMENTREJECTED, "AttachmentRejected"),
        (COMPLAINT, "Complaint"),
        (OTHER, "Other"),
    )


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
    recap_email = models.EmailField(
        help_text="Generated recap email address for the user.",
        blank=True,
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


class EmailFlag(AbstractDateTimeModel):
    """Stores flags for email addresses

    Two types of :object_type:
    BAN: ban an email address and avoid sending any email
    FLAG: flag an email address for a special treatment e.g small_email_only.
    :flag: the actual flag assigned, like: small_email_only
    :event_sub_type: the SNS bounce subtype that triggered the object
    :email_address: an EmailFlag object belongs to an email address instead
    of a user, in this way, if users change their email address this won't
    affect new user email address.
    """

    BAN = 0
    FLAG = 1
    OBJECT_TYPES = (
        (BAN, "Email ban"),
        (FLAG, "Email flag"),
    )
    SMALL_ONLY = 0
    MAX_RETRY_REACHED = 1
    FLAGS = (
        (SMALL_ONLY, "small_email_only"),
        (MAX_RETRY_REACHED, "max_retry_reached"),
    )
    email_address = models.EmailField(
        help_text="Email address flagged.",
    )
    object_type = models.SmallIntegerField(
        help_text="The object type assigned: ban or flag",
        choices=OBJECT_TYPES,
    )
    flag = models.SmallIntegerField(
        help_text="The actual flag assigned, like: small_email_only",
        choices=FLAGS,
        blank=True,
        null=True,
    )
    event_sub_type = models.SmallIntegerField(
        help_text="The notification event subtype.",
        choices=SUB_TYPES.TYPES,
    )

    class Meta:
        indexes = [
            models.Index(fields=["email_address"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_object_type_display()} for {self.email_address}"


class BackoffEvent(AbstractDateTimeModel):
    """Stores backoff events for email addresses, this is created or updated
    after receiving a soft bounce object for an email address.

    :email_address: The backoff event is related to this email address
    instead of a user, in this way, if users change their email address
    this won't affect new user email address.
    """

    email_address = models.EmailField(
        help_text="Email address under backoff event.",
    )
    retry_counter = models.SmallIntegerField(
        help_text="The retry counter for exponential backoff events.",
    )
    next_retry_date = models.DateTimeField(
        help_text="The datetime for next retry.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["email_address"]),
        ]

    def __str__(self) -> str:
        return f"Backoff event for {self.email_address}, next: {self.next_retry_date}"


def generate_recap_email(user_profile: UserProfile, append: int = None) -> str:
    username = user_profile.user.username
    recap_email_header = re.sub(r"[^0-9a-zA-Z]+", ".", username) + str(
        append if append is not None else ""
    )
    recap_email = f"{recap_email_header.lower()}@recap.email"
    user_profiles_with_match = UserProfile.objects.filter(
        recap_email=recap_email
    )
    if append is not None and append >= 100:
        raise FieldError("Too many requests made to generate recap email.")
    elif len(user_profiles_with_match) > 0:
        return generate_recap_email(user_profile, (append or 0) + 1)
    return recap_email


@receiver(post_save, sender=UserProfile)
def assign_recap_email(sender, instance=None, created=False, **kwargs) -> None:
    if created:
        instance.recap_email = generate_recap_email(instance)
        instance.save()
