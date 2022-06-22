from django.dispatch import receiver
from django_ses.signals import (
    bounce_received,
    complaint_received,
    delivery_received,
)

from cl.users.email_handlers import (
    handle_complaint,
    handle_hard_bounce,
    handle_soft_bounce,
)


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


@receiver(bounce_received)
def bounce_handler(sender, mail_obj, bounce_obj, raw_message, *args, **kwargs):
    """Receiver function to handle bounce notifications sent by Amazon SES via
    handle_event_webhook
    """

    message_id = get_message_id(mail_obj)
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


@receiver(complaint_received)
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
