import logging
from datetime import timedelta
from typing import List

from django.db import transaction
from django.utils.timezone import now

from cl.users.models import OBJECT_TYPES, SUB_TYPES, BackoffEvent, EmailFlag


def get_bounce_subtype(event_sub_type: str) -> int:
    """Returns a bounce subtype integer from a bounce subtype string"""
    sub_types_dict = dict(SUB_TYPES.TYPES)
    for key, value in sub_types_dict.items():
        if value == event_sub_type:
            return key
    return SUB_TYPES.OTHER


def handle_hard_bounce(
    event_sub_type: str, recipient_emails: List[str]
) -> None:
    """Ban any email address that receives a hard bounce.

    :param event_sub_type: the notification event subtype determined
    by Amazon SES
    :param recipient_emails: a list of email addresses one per recipient
    to whom the bounce notification pertains
    :return: None

    Hard bounce subtypes are General, NoEmail, Suppressed and
    OnAccountSuppressionList.

    For General and NoEmail subtypes we'll ban the email address.

    We don't expect Suppressed and OnAccountSuppressionList bounces because
    we aren't going to use SES supression list, if we receive one of these
    we are going to log a warning an also ban the email address.
    """
    unexpected_events = ["Suppressed", "OnAccountSuppressionList"]
    for email in recipient_emails:
        if event_sub_type in unexpected_events:
            # Handle unexpected event_sub_type events, log a warning
            logging.warning(
                f"Unexpected {event_sub_type} hard bounce for {email}"
            )
        # After log the event ban the email address
        # Only ban email address if it hasn't been previously banned
        EmailFlag.objects.get_or_create(
            email_address=email,
            object_type=OBJECT_TYPES.BAN,
            defaults={"event_sub_type": get_bounce_subtype(event_sub_type)},
        )


@transaction.atomic
def handle_soft_bounce(
    message_id: str, event_sub_type: str, recipient_emails: List[str]
) -> None:
    """Handle a soft bounce notification received from SNS

    :param message_id: The unique message id assigned by Amazon SES
    :param event_sub_type: The subtype of the bounce, as determined
     by Amazon SES
    :param recipient_emails: a list of email addresses one per recipient
     to whom the bounce notification pertains
    :return: None

    There are different soft bounce subtypes: General, MailboxFull
    MessageTooLarge, ContentRejected and AttachmentRejected, we perform
    different actions for each type:
    For Undetermined, General and MailboxFull: create or update a backoff
    event that works as follows:
    The general idea is to consider an average max retry period of 5 days, the
    exact period will depend on how fast SES sends bounce notifications.

    The first time we get a new soft bounce notification for an email address
    we'll wait 2 hours before trying to send another message to the same
    email address.

    If after sending a new message we get another soft bounce notification for
    the same email address the next waiting period will be 4 hours,
    if continue bouncing the next waiting period will be 8, 16, 32, and 64
    hours in the 5º retry, for a total of 126 hours (in average 5.25 days)
    since the initial bounce, if we receive another bounce notification
    after the 5º retry, the email address is banned.

    For: MessageTooLarge, AttachmentRejected, we create a small_email_only
    flag for the email address in order to avoid sending attachments to this
    email address in the future and then we try to resend the
    small_email_only email version.

    For unexpected bounce types, like: ContentRejected, we log a warning.
    """

    back_off_events = ["Undetermined", "General", "MailboxFull"]
    small_only_events = ["MessageTooLarge", "AttachmentRejected"]

    MAX_RETRY_COUNTER = 5
    INITIAL_HOURS = 2

    for email in recipient_emails:
        if event_sub_type in back_off_events:
            # TODO Queue email function
            # Handle events that must trigger a backoff event

            next_retry_date = now() + timedelta(hours=INITIAL_HOURS)
            (
                backoff_event,
                created,
            ) = BackoffEvent.objects.select_for_update().get_or_create(
                email_address=email,
                defaults={
                    "retry_counter": 0,
                    "next_retry_date": next_retry_date,
                },
            )

            if not created:
                # If a previous backoff event exists
                retry_counter = backoff_event.retry_counter
                next_retry_date = backoff_event.next_retry_date

                # Check if waiting period expired
                if now() >= next_retry_date:
                    if retry_counter >= MAX_RETRY_COUNTER:
                        # Check if backoff event has reached
                        # max number of retries, if so ban email address
                        # Only ban email address if not previously banned
                        EmailFlag.objects.get_or_create(
                            email_address=email,
                            object_type=OBJECT_TYPES.BAN,
                            defaults={
                                "flag": EmailFlag.MAX_RETRY_REACHED,
                                "event_sub_type": get_bounce_subtype(
                                    event_sub_type
                                ),
                            },
                        )
                        # TODO checkif this update Email flag?
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

        elif event_sub_type in small_only_events:
            # Handle events that must trigger a small_email_only event
            # Create a small_email_only flag for email address
            EmailFlag.objects.get_or_create(
                email_address=email,
                object_type=OBJECT_TYPES.FLAG,
                flag=EmailFlag.SMALL_ONLY,
                defaults={
                    "event_sub_type": get_bounce_subtype(event_sub_type)
                },
            )
            # TODO Resend small_email_only email version
        else:
            # Handle other unexpected event_sub_type events, like:
            # ContentRejected, log a warning
            logging.warning(
                f"Unexpected {event_sub_type} soft bounce for {email}"
            )


def handle_complaint(recipient_emails: List[str]) -> None:
    """Handle a complaint notification received from SNS

    Ban email addresses that received a complaint.

    :param message_id: The unique message id assigned by Amazon SES
    :param recipient_emails: a list of email addresses one per recipient
     to whom the complaint notification pertains
    :return: None
    """
    for email in recipient_emails:
        # Only ban email address if it hasn't been previously banned
        EmailFlag.objects.get_or_create(
            email_address=email,
            object_type=OBJECT_TYPES.BAN,
            defaults={"event_sub_type": SUB_TYPES.COMPLAINT},
        )


def handle_delivery(message_id: str, recipient_emails: List[str]) -> None:
    """Handle a delivery notification received from SNS

    :param message_id: The unique message id assigned by Amazon SES
    :param recipient_emails: a list of email addresses one per recipient
     to whom the delivery notification pertains
    :return: None
    """
    for email in recipient_emails:
        # Delete backoff event for this email address if exists
        BackoffEvent.objects.filter(email_address=email).delete()
        # Schedule failed emails for this recipient
        schedule_failed_email(email)


def schedule_failed_email(recipient_email: str) -> None:
    """Schedule recipient's failed emails after receive a delivery notification

    :param recipient_email: the recipient email address
     to whom the delivery notification pertains
    :return: None
    """
    pass
