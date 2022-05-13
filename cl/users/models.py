import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict

from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import FieldError
from django.db import models
from django.db.models import Q, Sum, UniqueConstraint
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


class EMAIL_NOTIFICATIONS(object):
    """SES Email Notifications Subtypes"""

    UNDETERMINED = 0
    GENERAL = 1
    NO_EMAIL = 2
    SUPPRESSED = 3
    ON_ACCOUNT_SUPPRESSION_LIST = 4
    MAILBOX_FULL = 5
    MESSAGE_TOO_LARGE = 6
    CONTENT_REJECTED = 7
    ATTACHMENT_REJECTED = 8
    COMPLAINT = 9
    OTHER = 10

    TYPES = (
        (UNDETERMINED, "Undetermined"),
        (GENERAL, "General"),
        (NO_EMAIL, "NoEmail"),
        (SUPPRESSED, "Suppressed"),
        (ON_ACCOUNT_SUPPRESSION_LIST, "OnAccountSuppressionList"),
        (MAILBOX_FULL, "MailboxFull"),
        (MESSAGE_TOO_LARGE, "MessageTooLarge"),
        (CONTENT_REJECTED, "ContentRejected"),
        (ATTACHMENT_REJECTED, "AttachmentRejected"),
        (COMPLAINT, "Complaint"),
        (OTHER, "Other"),
    )


class OBJECT_TYPES(object):
    """EmailFlag Object Types"""

    BAN = 0
    FLAG = 1
    TYPES = (
        (BAN, "Email ban"),
        (FLAG, "Email flag"),
    )


class EmailFlag(AbstractDateTimeModel):
    """Stores flags for email addresses."""

    SMALL_ONLY = 0
    MAX_RETRY_REACHED = 1
    FLAGS = (
        (SMALL_ONLY, "Small Email Only"),
        (MAX_RETRY_REACHED, "Max Retry Reached"),
    )
    email_address = models.EmailField(
        help_text="The email address the EmailFlag object is related to.",
    )
    object_type = models.SmallIntegerField(
        help_text="The object type assigned, "
        "Email ban: ban an email address and avoid sending any email. "
        "Email flag: flag an email address for a special treatment.",
        choices=OBJECT_TYPES.TYPES,
    )
    flag = models.SmallIntegerField(
        help_text="The actual flag assigned, e.g: Small Email Only.",
        choices=FLAGS,
        blank=True,
        null=True,
    )
    event_sub_type = models.SmallIntegerField(
        help_text="The SES notification subtype that triggered the object.",
        choices=EMAIL_NOTIFICATIONS.TYPES,
    )

    class Meta:
        indexes = [
            models.Index(fields=["email_address"]),
        ]
        # Creates a unique constraint to allow only one BAN object for
        # each email_address
        constraints = [
            UniqueConstraint(
                fields=["email_address"],
                condition=Q(object_type=OBJECT_TYPES.BAN),
                name="unique_email_ban",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_object_type_display()} for {self.email_address}"


class BackoffEvent(AbstractDateTimeModel):
    """Stores backoff events for email addresses, this is created or updated
    after receiving a soft bounce object for an email address.
    """

    email_address = models.EmailField(
        help_text="The email address the Backoff event is related to.",
        unique=True,
    )
    retry_counter = models.SmallIntegerField(
        help_text="The retry counter for exponential backoff events.",
    )
    next_retry_date = models.DateTimeField(
        help_text="The next retry datetime for exponential backoff events.",
    )
    notification_subtype = models.SmallIntegerField(
        help_text="The SES notification subtype that triggered the object.",
        choices=EMAIL_NOTIFICATIONS.TYPES,
        default=EMAIL_NOTIFICATIONS.UNDETERMINED,
    )

    @property
    def under_waiting_period(self) -> bool:
        """Does the backoff event is under waiting period?

        :return bool: True if so, False if not.
        """
        if now() < self.next_retry_date:
            return True
        else:
            return False

    def __str__(self) -> str:
        return f"Backoff event for {self.email_address}, next: {self.next_retry_date}"


class EmailSent(AbstractDateTimeModel):
    """Stores email messages."""

    user = models.ForeignKey(
        User,
        help_text="The user that this message is related to in case of users "
        "change their email address we can send failed email to the user's "
        "new email address, this is optional in case we send email to an"
        "email address that doesn't belong to a CL user.",
        related_name="emails",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    message_id = models.UUIDField(
        help_text="Unique message identifier",
        default=uuid.uuid4,
        editable=False,
    )
    from_email = models.CharField(
        help_text="From email address", max_length=300
    )
    to = ArrayField(
        models.CharField(max_length=254),
        help_text="List of email recipients",
        blank=True,
        null=True,
    )
    bcc = ArrayField(
        models.CharField(max_length=254),
        help_text="List of BCC emails addresses",
        blank=True,
        null=True,
    )
    cc = ArrayField(
        models.CharField(max_length=254),
        help_text="List of CC emails addresses",
        blank=True,
        null=True,
    )
    reply_to = ArrayField(
        models.CharField(max_length=254),
        help_text="List of Reply to emails addresses",
        blank=True,
        null=True,
    )
    subject = models.TextField(help_text="Subject", blank=True)
    plain_text = models.TextField(
        help_text="Plain Text Message Body", blank=True
    )
    html_message = models.TextField(help_text="HTML Message Body", blank=True)
    headers = models.JSONField(
        help_text="Original email Headers", blank=True, null=True
    )

    class Meta:
        indexes = [
            models.Index(fields=["message_id"]),
        ]

    def __str__(self) -> str:
        return f"Email: {self.message_id}"


class STATUS_TYPES(object):
    """FailedEmail Status Types"""

    WAITING = 0
    ENQUEUED = 1
    ENQUEUED_DELIVERY = 2
    IN_PROGRESS = 3
    SUCCESSFUL = 4
    STATUS = (
        (WAITING, "Waiting for a delivery signal to enqueue."),
        (ENQUEUED, "Awaiting processing in queue after a backoff event."),
        (
            ENQUEUED_DELIVERY,
            "Awaiting processing in queue due to a delivery event.",
        ),
        (IN_PROGRESS, "Item is currently being processed."),
        (SUCCESSFUL, "Item processed successfully."),
    )


class FailedEmail(AbstractDateTimeModel):
    """Stores enqueue failed messages."""

    message_id = models.UUIDField(
        help_text="Unique message identifier.",
        default=uuid.uuid4,
        editable=False,
    )
    recipient = models.EmailField(
        help_text="The email address to which the delivery failed.",
    )

    status = models.SmallIntegerField(
        help_text="The enqueue failed message status.",
        default=STATUS_TYPES.WAITING,
        choices=STATUS_TYPES.STATUS,
    )
    next_retry_date = models.DateTimeField(
        help_text="The scheduled datetime to retry sending the message.",
        blank=True,
        null=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["recipient"]),
        ]

        constraints = [
            UniqueConstraint(
                fields=["recipient"],
                condition=Q(status=STATUS_TYPES.ENQUEUED),
                name="unique_failed_enqueued",
            )
        ]

    def __str__(self) -> str:
        return f"Failed Email: {self.message_id}"


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
