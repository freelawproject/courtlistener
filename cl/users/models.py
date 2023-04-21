import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict

import pghistory
from django.conf import settings
from django.contrib.auth.models import Group, Permission, User
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import FieldError
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.db import models
from django.db.models import Q, Sum, UniqueConstraint
from django.utils.timezone import now
from localflavor.us.models import USStateField

from cl.api.utils import invert_user_logs
from cl.lib.model_helpers import invert_choices_group_lookup
from cl.lib.models import AbstractDateTimeModel
from cl.lib.pghistory import AfterUpdateOrDeleteSnapshot

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


@pghistory.track(AfterUpdateOrDeleteSnapshot())
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
    auto_subscribe = models.BooleanField(
        help_text="If enabled, for every new case that comes in from the "
        "user's recap.email address, a new docket subscription for the case "
        "will be created; if disabled we'll ask users if they want to "
        "subscribe to the case.",
        default=True,
    )
    docket_default_order_desc = models.BooleanField(
        help_text="Sort dockets in descending order by default",
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
    def email_grants_unlimited_docket_alerts(self) -> bool:
        """Does the user's email grant them unlimited docket alerts?

        :return: True if their email is on the list; else False.
        """
        # Don't check if the email is confirmed. They can't log in if so.
        domain = self.user.email.split("@")[1]
        if domain in settings.UNLIMITED_DOCKET_ALERT_EMAIL_DOMAINS:
            return True
        return False

    @property
    def can_make_another_alert(self) -> bool:
        """Can the user make another alert?

        The answer is yes, if any of the following is true:
         - They get unlimited ones
         - They are a monthly donor
         - They are under the threshold
         - Their email domain is unlimited

        return: True if they can make another alert; else False.
        """
        if any(
            [
                # Place performant checks first
                self.unlimited_docket_alerts,
                self.email_grants_unlimited_docket_alerts,
                self.is_monthly_donor,
                self.user.docket_alerts.subscriptions().count()
                < settings.MAX_FREE_DOCKET_ALERTS,
            ]
        ):
            return True
        return False

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


@pghistory.track(AfterUpdateOrDeleteSnapshot(), obj_field=None)
class UserProfileBarMembership(UserProfile.barmembership.through):
    """A model class to track user profile barmembership m2m relation"""

    class Meta:
        proxy = True


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
    MAX_RETRY_REACHED = 10

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
        (MAX_RETRY_REACHED, "MaxRetryReached"),
    )
    INVERTED = invert_choices_group_lookup(TYPES)


class FLAG_TYPES(object):
    """EmailFlag Flag Types"""

    BAN = 0
    BACKOFF = 1
    TYPES = (
        (BAN, "Email banned"),
        (BACKOFF, "Email backoff event"),
    )


class EmailFlag(AbstractDateTimeModel):
    """Stores flags for email addresses."""

    email_address = models.EmailField(
        help_text="The email address the EmailFlag object is related to.",
    )
    flag_type = models.SmallIntegerField(
        help_text="The flag type assigned, "
        "Email ban: ban an email address and avoid sending any email. "
        "Email backoff event: an active backoff event.",
        choices=FLAG_TYPES.TYPES,
        default=FLAG_TYPES.BAN,
    )
    notification_subtype = models.SmallIntegerField(
        help_text="The SES notification subtype that triggered the object.",
        choices=EMAIL_NOTIFICATIONS.TYPES,
        default=EMAIL_NOTIFICATIONS.UNDETERMINED,
    )
    retry_counter = models.SmallIntegerField(
        help_text="The retry counter for exponential backoff events.",
        blank=True,
        null=True,
    )
    next_retry_date = models.DateTimeField(
        help_text="The next retry datetime for exponential backoff events.",
        blank=True,
        null=True,
    )
    checked = models.DateTimeField(
        help_text="The datetime the recipient's deliverability was checked"
        " since the last bounce event.",
        blank=True,
        null=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["email_address"]),
            models.Index(fields=["flag_type", "checked"]),
        ]
        # Creates a unique constraint to allow only one BAN and Backoff Event
        # object for each email_address
        constraints = [
            UniqueConstraint(
                fields=["email_address"],
                condition=Q(flag_type=FLAG_TYPES.BAN),
                name="unique_email_ban",
            ),
            UniqueConstraint(
                fields=["email_address"],
                condition=Q(flag_type=FLAG_TYPES.BACKOFF),
                name="unique_email_backoff",
            ),
        ]

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
        return f"{self.get_flag_type_display()} for {self.email_address}"


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
        verbose_name = "Sent Email"
        verbose_name_plural = "Emails Sent"

    def convert_to_email_multipart(
        self,
    ) -> EmailMessage | EmailMultiAlternatives:
        """Composes an email multipart message from the data stored.

        :return email: Return an EmailMessage or EmailMultiAlternatives message
        """

        # Get the required fields to compose the email multipart message
        keys_to_use = ("subject", "from_email", "reply_to", "headers", "to")
        msg_dict = {k: v for k, v in self.__dict__.items() if k in keys_to_use}

        # If the message has a related User, choose the user email address to
        # ensure we send it to the updated user email address.
        if self.user:
            msg_dict["to"] = [self.user.email]

        email: EmailMessage | EmailMultiAlternatives
        if self.html_message:
            if self.plain_text:
                msg_dict["body"] = self.plain_text
                email = EmailMultiAlternatives(**msg_dict)
                email.attach_alternative(self.html_message, "text/html")
            else:
                msg_dict["body"] = self.html_message
                email = EmailMultiAlternatives(**msg_dict)
                email.content_subtype = "html"
        else:
            msg_dict["body"] = self.plain_text
            email = EmailMessage(**msg_dict)
        return email

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

    stored_email = models.ForeignKey(
        EmailSent,
        help_text="The related stored email message.",
        related_name="failed_emails",
        on_delete=models.CASCADE,
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
        return f"Failed Email: {self.stored_email.message_id}"


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


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class UserProxy(User):
    """A proxy model class to track auth user model"""

    class Meta:
        proxy = True


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class GroupProxy(Group):
    """A proxy model class to track auth group model"""

    class Meta:
        proxy = True


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class PermissionProxy(Permission):
    """A proxy model class to track auth permission model"""

    class Meta:
        proxy = True


@pghistory.track(AfterUpdateOrDeleteSnapshot(), obj_field=None)
class GroupPermissions(Group.permissions.through):
    """A proxy model class to track group permissions m2m relation"""

    class Meta:
        proxy = True


@pghistory.track(AfterUpdateOrDeleteSnapshot(), obj_field=None)
class UserGroups(User.groups.through):
    """A proxy model class to track user groups m2m relation"""

    class Meta:
        proxy = True


@pghistory.track(AfterUpdateOrDeleteSnapshot(), obj_field=None)
class UserPermissions(User.user_permissions.through):
    """A proxy model class to track user permissions m2m relation"""

    class Meta:
        proxy = True
