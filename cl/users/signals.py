from django.dispatch import receiver
from django_ses.signals import (
    bounce_received,
    complaint_received,
    delivery_received,
)

from cl.users.email_handlers import (
    handle_complaint,
    handle_delivery,
    handle_hard_bounce,
    handle_soft_bounce,
)


@receiver(bounce_received)
def bounce_handler(sender, mail_obj, bounce_obj, raw_message, *args, **kwargs):
    """Receiver function to handle bounce notifications sent by Amazon SES via
    handle_event_webhook
    """
    if bounce_obj:
        message_id = mail_obj["messageId"]
        bounce_type = bounce_obj["bounceType"]
        bounce_sub_type = bounce_obj["bounceSubType"]
        bounced_recipients = bounce_obj["bouncedRecipients"]
        recipient_emails = [
            email["emailAddress"] for email in bounced_recipients
        ]
        # If bounce_type is Permanent, handle a hard bounce
        # If bounce_type is Transient, handle a soft bounce
        # If bounce_type is Undetermined, handle a soft bounce
        if bounce_type == "Permanent":
            handle_hard_bounce(bounce_sub_type, recipient_emails)
        elif bounce_type == "Transient" or "Undetermined":
            handle_soft_bounce(message_id, bounce_sub_type, recipient_emails)


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


@receiver(delivery_received)
def delivery_handler(
    sender, mail_obj, delivery_obj, raw_message, *args, **kwargs
):
    """Receiver function to handle delivery notifications sent by
    Amazon SES via handle_event_webhook
    """
    if delivery_obj:
        message_id = mail_obj["messageId"]
        recipient_emails = mail_obj["destination"]
        handle_delivery(message_id, recipient_emails)
