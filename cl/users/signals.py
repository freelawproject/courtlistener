import json
import random
from datetime import timedelta
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now
from django_ses.signals import bounce_received, complaint_received
from rest_framework.authtoken.models import Token

from cl.api.models import Webhook
from cl.lib.crypto import sha1_activation_key
from cl.lib.storage import S3PrivateUUIDStorage
from cl.users.email_handlers import (
    handle_complaint,
    handle_hard_bounce,
    handle_soft_bounce,
)
from cl.users.models import UserProfile, generate_recap_email
from cl.users.tasks import notify_new_or_updated_webhook


class SESEventType(str, Enum):
    BOUNCE = "bounce"
    COMPLAINT = "complaint"


def get_message_id(mail_obj: dict) -> str:
    """Returns the unique message_id from the SES notification header.

    :param mail_obj: The notification mail object to extract the message_id
    :return message_id: The unique message_id
    """

    headers = mail_obj["headers"]
    for header in headers:
        if header["name"] == "X-CL-ID":
            message_id = header["value"]
            return message_id
    return ""


def store_bounce_or_complaint_obj(
    bounce_obj: dict[str, Any], email_recipient: str, obj_type: SESEventType
) -> None:
    """
    Store the SES bounce/complaint payload to S3 as JSON.

    :param bounce_obj: The bounce payload to store.
    :param email_recipient: The email address the event belongs to.
    :param obj_type: The type of the bounce/complaint.
    """

    match obj_type:
        case SESEventType.COMPLAINT:
            dir_name = "complaints"
            storing_rate = settings.COMPLAINTS_STORE_RATE
        case SESEventType.BOUNCE:
            dir_name = "bounces"
            storing_rate = settings.BOUNCES_STORE_RATE
        case _:
            return None

    if random.random() >= storing_rate and email_recipient:
        # Ignore events over the random rate.
        return None

    try:
        storage = S3PrivateUUIDStorage()
        feedback_id = bounce_obj.get("feedbackId", "unknown_id")
        file_contents = json.dumps(bounce_obj, indent=2)
        s3_path = PurePosixPath(
            dir_name, email_recipient, f"{feedback_id}.json"
        )
        # Save to S3
        storage.save(str(s3_path), ContentFile(file_contents))
    except Exception:
        return None


@receiver(bounce_received, dispatch_uid="bounce_handler")
def bounce_handler(sender, mail_obj, bounce_obj, raw_message, *args, **kwargs):
    """Receiver function to handle bounce notifications sent by Amazon SES via
    handle_event_webhook
    """

    message_id = get_message_id(mail_obj)
    email_recipient = ""
    if bounce_obj:
        bounce_type = bounce_obj["bounceType"]
        bounce_sub_type = bounce_obj["bounceSubType"]
        bounced_recipients = bounce_obj["bouncedRecipients"]
        # If bounce_type is Permanent, handle a hard bounce
        # If bounce_type is Transient, handle a soft bounce
        # If bounce_type is Undetermined, handle a soft bounce
        if bounce_type == "Permanent":
            hard_recipient_emails = [
                email["emailAddress"] for email in bounced_recipients
            ]
            handle_hard_bounce(bounce_sub_type, hard_recipient_emails)
            email_recipient = (
                hard_recipient_emails[0] if hard_recipient_emails else ""
            )
        elif bounce_type == "Transient" or "Undetermined":
            # Only consider a soft bounce those that contains a "failed" action
            # in its bounce recipient, avoiding other bounces that might not
            # be related to failed deliveries, like auto-responders.
            soft_recipient_emails = [
                email["emailAddress"]
                for email in bounced_recipients
                if email.get("action", None) == "failed"
            ]
            if soft_recipient_emails:
                handle_soft_bounce(
                    message_id, bounce_sub_type, soft_recipient_emails
                )
                email_recipient = soft_recipient_emails[0]

        store_bounce_or_complaint_obj(
            bounce_obj, email_recipient, SESEventType.BOUNCE
        )


@receiver(complaint_received, dispatch_uid="complaint_handler")
def complaint_handler(
    sender, mail_obj, complaint_obj, raw_message, *args, **kwargs
):
    """Receiver function to handle complaint notifications sent by
    Amazon SES via handle_event_webhook
    """

    if complaint_obj:
        complained_recipients = complaint_obj["complainedRecipients"]
        recipient_emails = [
            email["emailAddress"] for email in complained_recipients
        ]
        handle_complaint(recipient_emails)
        email_recipient = recipient_emails[0] if recipient_emails else ""
        store_bounce_or_complaint_obj(
            complaint_obj, email_recipient, SESEventType.COMPLAINT
        )


@receiver(
    post_save,
    sender=settings.AUTH_USER_MODEL,
    dispatch_uid="create_auth_token",
)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)


@receiver(
    post_save,
    sender=settings.AUTH_USER_MODEL,
    dispatch_uid="create_superuser_profile_object",
)
def superuser_creation(sender, instance, created, **kwargs):
    # Create a profile whenever createsuperuser is run
    if created and instance.is_superuser:
        UserProfile.objects.create(
            user=instance,
            activation_key=sha1_activation_key(instance.username),
            key_expires=now() + timedelta(days=5),
            email_confirmed=True,
        )


@receiver(post_save, sender=UserProfile, dispatch_uid="assign_recap_email")
def assign_recap_email(sender, instance=None, created=False, **kwargs) -> None:
    if created:
        instance.recap_email = generate_recap_email(instance)
        instance.save()


@receiver(post_save, sender=Webhook, dispatch_uid="webhook_created_or_updated")
def webhook_created_or_updated(
    sender, instance=None, created=False, update_fields=None, **kwargs
) -> None:
    """Notify admins when a new webhook is created or updated. Avoid sending
    the notification when the webhook failure_count is updated.
    """
    if created:
        notify_new_or_updated_webhook.delay(instance.pk, created=True)
    else:
        if update_fields:
            if (
                "failure_count"
                or "enabled"
                or "date_modified" in update_fields
            ):
                return
        notify_new_or_updated_webhook.delay(instance.pk, created=False)
