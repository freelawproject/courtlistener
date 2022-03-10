import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List

from django.contrib.auth.models import User
from django.core.exceptions import FieldError
from django.db import models
from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now
from django_ses.signals import (
    bounce_received,
    complaint_received,
    delivery_received,
)
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


class EmailFlag(models.Model):
    BAN = "ban"
    FLAG = "flag"
    FLAGS_TYPES = (
        (BAN, "Email ban"),
        (FLAG, "Email flag"),
    )
    email_address = models.EmailField(
        help_text="Email address flagged.",
    )
    flag_type = models.CharField(
        help_text="The flag type assigned.",
        choices=FLAGS_TYPES,
        max_length=5,
    )
    flag = models.CharField(
        help_text="The flag assigned to email address.",
        max_length=25,
        blank=True,
    )
    reason = models.CharField(
        help_text="The notification subtype",
        max_length=50,
        blank=True,
    )
    date_created = models.DateTimeField(
        help_text="The moment when the item was created.",
        auto_now_add=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["email_address"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_flag_type_display()} for {self.email_address}"


class BackoffEvent(models.Model):
    email_address = models.EmailField(
        help_text="Email address under backoff event.",
    )
    retry_counter = models.SmallIntegerField(
        help_text="The retry counter for exponential backoff events.",
    )
    next_retry_date = models.DateTimeField(
        help_text="The datetime for next retry.",
    )
    date_created = models.DateTimeField(
        help_text="The moment when the item was created.",
        auto_now_add=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["email_address"]),
        ]

    def __str__(self) -> str:
        return f"Backoff event for {self.email_address}"


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


def handle_hard_bounce(
    message_id: str, bounceSubType: str, recipient_emails: List[str]
) -> None:
    """Handle a hard bounce notification received from SNS
    :param message_id: The unique message id assigned by Amazon SES
    :param bounceSubType: The subtype of the bounce, as determined
     by Amazon SES
    :param recipient_emails: a list of email addresses one per recipient
     to whom the bounce notification pertains
    :return: None
    """
    pass


def handle_soft_bounce(
    message_id: str, bounceSubType: str, recipient_emails: List[str]
) -> None:
    """Handle a soft bounce notification received from SNS
    :param message_id: The unique message id assigned by Amazon SES
    :param bounceSubType: The subtype of the bounce, as determined
     by Amazon SES
    :param recipient_emails: a list of email addresses one per recipient
     to whom the bounce notification pertains
    :return: None
    """

    back_off_events = ["Undetermined", "General", "MailboxFull"]
    small_only_events = ["MessageTooLarge", "AttachmentRejected"]

    MAX_RETRY_COUNTER = 5
    INITIAL_HOURS = 2

    for email in recipient_emails:
        if bounceSubType in back_off_events:
            # Handle events that must trigger a backoff event
            backoff_event = BackoffEvent.objects.filter(
                email_address=email,
            )
            if not backoff_event.exists():
                # Create a backoff event for an email address if not exists
                # Initialize retry_counter and next_retry_date
                next_retry_date = now() + timedelta(hours=INITIAL_HOURS)
                BackoffEvent.objects.create(
                    email_address=email,
                    retry_counter=0,
                    next_retry_date=next_retry_date,
                )
            else:
                # If a previous backoff event exists
                retry_counter = backoff_event[0].retry_counter
                next_retry_date = backoff_event[0].next_retry_date

                # Check if waiting period expired
                if next_retry_date <= now():
                    if retry_counter >= MAX_RETRY_COUNTER:
                        # Check if backoff event has reached
                        # max number of retries, if so ban email address
                        EmailFlag.objects.create(
                            email_address=email,
                            flag_type="ban",
                            flag="max_retry_reached",
                            reason=bounceSubType,
                        )
                    else:
                        # If max number of retries has not been reached,
                        # update backoff event, update retry_counter
                        new_retry_counter = retry_counter + 1
                        # Update new_next_retry_date exponentially
                        new_next_retry_date = now() + timedelta(
                            hours=pow(INITIAL_HOURS, new_retry_counter + 1)
                        )
                        BackoffEvent.objects.filter(
                            email_address=email,
                        ).update(
                            retry_counter=new_retry_counter,
                            next_retry_date=new_next_retry_date,
                        )

        elif bounceSubType in small_only_events:
            # Handle events that must trigger a small_email_only event
            small_only_exists = EmailFlag.objects.filter(
                email_address=email,
                flag_type="flag",
                flag="small_email_only",
            ).exists()
            # Create a small_email_only flag for email address
            if not small_only_exists:
                EmailFlag.objects.create(
                    email_address=email,
                    flag_type="flag",
                    flag="small_email_only",
                    reason=bounceSubType,
                )
        else:
            # Handle other unexpected bounceSubType events, log a warning
            logging.warning(
                f"Unexpected {bounceSubType} soft bounce for {email}"
            )


def handle_complaint(message_id: str, recipient_emails: List[str]) -> None:
    """Handle a complaint notification received from SNS
    :param message_id: The unique message id assigned by Amazon SES
    :param recipient_emails: a list of email addresses one per recipient
     to whom the complaint notification pertains
    :return: None
    """
    pass


def handle_delivery(message_id: str, recipient_emails: List[str]) -> None:
    """Handle a delivery notification received from SNS
    :param message_id: The unique message id assigned by Amazon SES
    :param recipient_emails: a list of email addresses one per recipient
     to whom the delivery notification pertains
    :return: None
    """
    pass


@receiver(post_save, sender=UserProfile)
def assign_recap_email(sender, instance=None, created=False, **kwargs) -> None:
    if created:
        instance.recap_email = generate_recap_email(instance)
        instance.save()


@receiver(bounce_received)
def bounce_handler(sender, mail_obj, bounce_obj, raw_message, *args, **kwargs):
    """Receiver function to handle bounce notifications sent by Amazon SES via
    SESEventWebhookView
    """
    if bounce_obj:
        message_id = mail_obj["messageId"]
        bounceType = bounce_obj["bounceType"]
        bounceSubType = bounce_obj["bounceSubType"]
        bouncedRecipients = bounce_obj["bouncedRecipients"]
        recipient_emails = [
            email["emailAddress"] for email in bouncedRecipients
        ]
        # If bounceType is Permanent, handle a hard bounce
        # If bounceType is Transient, handle a soft bounce
        if bounceType == "Permanent":
            handle_hard_bounce(message_id, bounceSubType, recipient_emails)
        elif bounceType == "Transient":
            handle_soft_bounce(message_id, bounceSubType, recipient_emails)


@receiver(complaint_received)
def complaint_handler(
    sender, mail_obj, complaint_obj, raw_message, *args, **kwargs
):
    """Receiver function to handle complaint notifications sent by
    Amazon SES via SESEventWebhookView
    """

    if complaint_obj:
        message_id = mail_obj["messageId"]
        complainedRecipients = complaint_obj["complainedRecipients"]
        recipient_emails = [
            email["emailAddress"] for email in complainedRecipients
        ]
        handle_complaint(message_id, recipient_emails)


@receiver(delivery_received)
def delivery_handler(
    sender, mail_obj, delivery_obj, raw_message, *args, **kwargs
):
    """Receiver function to handle delivery notifications sent by
    Amazon SES via SESEventWebhookView
    """
    if delivery_obj:
        message_id = mail_obj["messageId"]
        recipient_emails = mail_obj["destination"]
        handle_delivery(message_id, recipient_emails)
