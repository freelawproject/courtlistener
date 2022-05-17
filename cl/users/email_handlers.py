import logging
import random
from collections.abc import Sequence
from datetime import datetime, timedelta
from email.utils import parseaddr

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import (
    EmailMessage,
    EmailMultiAlternatives,
    SafeMIMEMultipart,
    SafeMIMEText,
)
from django.db import transaction
from django.utils.timezone import now

from cl.users.models import (
    EMAIL_NOTIFICATIONS,
    OBJECT_TYPES,
    STATUS_TYPES,
    BackoffEvent,
    EmailFlag,
    EmailSent,
    FailedEmail,
)


def get_bounce_subtype(event_sub_type: str) -> int:
    """Returns a bounce subtype integer from a bounce subtype string"""
    sub_types_dict = dict(EMAIL_NOTIFICATIONS.TYPES)
    for key, value in sub_types_dict.items():
        if value == event_sub_type:
            return key
    return EMAIL_NOTIFICATIONS.OTHER


def handle_hard_bounce(
    event_sub_type: str, recipient_emails: list[str]
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
    message_id: str, event_sub_type: str, recipient_emails: list[str]
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
                    "notification_subtype": get_bounce_subtype(event_sub_type),
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

            # Enqueue the soft bounce related message to retry again later
            enqueue_email([email], message_id)

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


def handle_complaint(recipient_emails: list[str]) -> None:
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
            defaults={"event_sub_type": EMAIL_NOTIFICATIONS.COMPLAINT},
        )


def handle_delivery(recipient_emails: list[str]) -> None:
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


def has_small_version(message: SafeMIMEText | SafeMIMEMultipart) -> bool:
    """Function to check if a message has a small version available

    :param message: The message to check
    :return: True if the message has a small body version; otherwise False
    """

    # Check if the message contains a small version
    for part in message.walk():
        if (
            part.get_content_type() == "text/plain_small"
            or part.get_content_type() == "text/html_small"
        ):
            return True
    return False


def get_email_body(
    message: SafeMIMEText | SafeMIMEMultipart,
    small_version: bool,
) -> tuple[str, str]:
    """Function to retrieve html and plain body content of an email

    :param message: the message to extract the body content
    :param small_version: True if we need to extract the small body version,
    False to return the normal body version.
    :return: plaintext_body and html_body strings
    """

    # Returns the content_type we need to extract
    if small_version:
        plain = "text/plain_small"
        html = "text/html_small"
    else:
        plain = "text/plain"
        html = "text/html"

    plaintext_body = ""
    html_body = ""
    for part in message.walk():
        if part.get_content_type() == plain:
            plaintext_body = part.get_payload()
            break

    for part in message.walk():
        if part.get_content_type() == html:
            html_body = part.get_payload()
            break

    return plaintext_body, html_body


def normalize_addresses(email_list: Sequence[str]) -> list[str]:
    """Takes a collection of email addresses and returns a list of the
    normalized email addresses.
    e.g: ["Admin User <success@simulator.amazonses.com>"] turns to
    ["success@simulator.amazonses.com"]

    :param email_list: A collection of email addresses (tuple, list, etc)
    :return list[str]: A list with the normalized email addresses
    """

    normalized_addresses = []
    for email in email_list:
        raw_address = parseaddr(email)
        # parseaddr returns a 2-tuple of ('realname', 'email'), selects email.
        normalized_addresses.append(raw_address[1])

    return normalized_addresses


def store_message(message: EmailMessage | EmailMultiAlternatives) -> str:
    """Stores an email message and returns its message_id, if the original
    message had attachments we store the small version without attachments

    :param message: The  message to store
    :return message_id: The unique email message identifier
    """
    subject = message.subject
    from_email = message.from_email
    to = normalize_addresses(message.to)
    bcc = normalize_addresses(message.bcc)
    cc = normalize_addresses(message.cc)
    reply_to = normalize_addresses(message.reply_to)
    headers = message.extra_headers
    body_message = message.message()
    small_version = has_small_version(body_message)
    plain_body, html_body = get_email_body(body_message, small_version)

    # Look for the CL user by email address to assign it.
    # We only try to assign the message to an user if is a unique recipient
    if len(to) == 1:
        users = User.objects.filter(email=to[0])
        if users.exists():
            user = users[0]
        else:
            user = None
    else:
        user = None

    email_stored = EmailSent.objects.create(
        user=user,
        from_email=from_email,
        to=to,
        bcc=bcc,
        cc=cc,
        reply_to=reply_to,
        subject=subject,
        plain_text=plain_body,
        html_message=html_body,
        headers=headers,
    )
    return email_stored.message_id


def compose_message(
    message: EmailMessage | EmailMultiAlternatives, small_version: bool
) -> EmailMessage | EmailMultiAlternatives:
    """Composes an email message according to the version needed and
    available content_type

    :param message: The  message to compose
    :param small_version: Whether to use the small version of an email
    :return message: Returns a EmailMessage or EmailMultiAlternatives message
    """
    subject = message.subject
    from_email = message.from_email
    to = message.to
    bcc = message.bcc
    cc = message.cc
    reply_to = message.reply_to
    headers = message.extra_headers
    body_message = message.message()
    plain_body, html_body = get_email_body(body_message, small_version)

    email: EmailMessage | EmailMultiAlternatives
    if html_body:
        if plain_body:
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_body,
                from_email=from_email,
                to=to,
                bcc=bcc,
                cc=cc,
                reply_to=reply_to,
                headers=headers,
            )
            email.attach_alternative(html_body, "text/html")
        else:
            email = EmailMultiAlternatives(
                subject=subject,
                body=html_body,
                from_email=from_email,
                to=to,
                bcc=bcc,
                cc=cc,
                reply_to=reply_to,
                headers=headers,
            )
            email.content_subtype = "html"
    else:
        email = EmailMessage(
            subject=subject,
            body=plain_body,
            from_email=from_email,
            to=to,
            bcc=bcc,
            cc=cc,
            reply_to=reply_to,
            headers=headers,
        )
    return email


def under_backoff_waiting_period(email_address: str) -> bool:
    """Returns True if the provided email address is under a backoff waiting
    period, otherwise False.

    :param email_address: The email address to verify
    :return bool: True if the email address is under a waiting period, if not
    False
    """
    backoff_event = BackoffEvent.objects.filter(
        email_address=email_address,
    ).first()
    if backoff_event.under_waiting_period if backoff_event else False:
        return True
    return False


def is_not_email_banned(email_address: str) -> bool:
    """Returns True if the email address provided is not banned, otherwise
    False.

    :param email_address: The email address to verify
    :return bool: True if the email address is not banned, otherwise False
    """
    banned_email = EmailFlag.objects.filter(
        email_address=email_address,
        object_type=OBJECT_TYPES.BAN,
    )
    if not banned_email.exists():
        return True
    return False


def is_small_only_flagged(email_address: str) -> bool:
    """Returns True if the email address is small email only flagged,
    otherwise False.

    :param email_address: The email address to verify
    :return bool: True if the email address is small email only flagged,
    if not False
    """
    small_only = EmailFlag.objects.filter(
        email_address=email_address,
        object_type=OBJECT_TYPES.FLAG,
        flag=EmailFlag.SMALL_ONLY,
    )
    if small_only.exists():
        return True
    return False


def add_bcc_random(
    message: EmailMessage | EmailMultiAlternatives,
    bcc_rate: float,
) -> EmailMessage | EmailMultiAlternatives:
    """This function uses randint() to obtain the probability of BCC a message
    based on the bcc_rate which is a float value from 0 to 1.

    e.g: if we want to bcc to the 10% of messages we should use a bcc_rate
    of 0.1, so we'd have a normalized_bcc_rate of 10, so it'll check if the
    random returned value by randint(1,100) is <= 10, which means, in theory,
    a probability of 1/10.

    :param bcc_rate: The email bcc copy rate, a float value between 0-1 that
    represent the percentage of messages that we want to add a BCC
    :return EmailMessage | EmailMultiAlternatives: Returns the message with a
    BCC added or not.
    """

    returned_value = random.randint(1, 100)
    normalized_bcc_rate = int(bcc_rate * 100)
    if returned_value <= normalized_bcc_rate:
        message.bcc.append(settings.BCC_EMAIL_ADDRESS)
    return message


def compose_stored_message(
    message_id: str,
) -> EmailMessage | EmailMultiAlternatives:
    """Composes an email message from the data stored in EmailSent model.

    :param message_id: The unique email message identifier
    :return email: Returns an EmailMessage or EmailMultiAlternatives message
    """

    stored_message = EmailSent.objects.get(message_id=message_id)

    # If the message has a related User, choose the user email address to
    # ensure we send it to the updated user email address.
    if stored_message.user:
        to = [stored_message.user.email]
    else:
        to = stored_message.to
    from_email = stored_message.from_email
    reply_to = stored_message.reply_to
    subject = stored_message.subject
    plain_body = stored_message.plain_text
    html_body = stored_message.html_message
    headers = stored_message.headers

    email: EmailMessage | EmailMultiAlternatives
    if html_body:
        if plain_body:
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_body,
                from_email=from_email,
                to=to,
                reply_to=reply_to,
                headers=headers,
            )
            email.attach_alternative(html_body, "text/html")
        else:
            email = EmailMultiAlternatives(
                subject=subject,
                body=html_body,
                from_email=from_email,
                to=to,
                reply_to=reply_to,
                headers=headers,
            )
            email.content_subtype = "html"
    else:
        email = EmailMessage(
            subject=subject,
            body=plain_body,
            from_email=from_email,
            to=to,
            reply_to=reply_to,
            headers=headers,
        )
    return email


def delete_failed_tasks_objects(recipient: str) -> None:
    """Delete FailedEmail objects that their celery task failed after multiple
    retries.

    :param recipient: The recipient email to look for failed objects.
    :return None:
    """

    # Look for possible failed objects according to their status.
    failed_enqueued = FailedEmail.objects.filter(
        recipient=recipient,
        status__in=[
            STATUS_TYPES.ENQUEUED_DELIVERY,
            STATUS_TYPES.ENQUEUED,
            STATUS_TYPES.IN_PROGRESS,
        ],
    )

    # Give a 30 minutes gap to ensure tasks were max retried
    # delete the task if is out of this time gap.
    now_minus_30 = now() - timedelta(minutes=30)
    for failed in failed_enqueued:
        if now_minus_30 >= failed.next_retry_date:
            failed.delete()


def get_next_retry_date(recipient: str) -> datetime:
    """Returns the next retry datetime to schedule a message based on the
    recipient backoff event next retry date time.

    :param recipient: The email address to look for a backoff event next retry
    datetime.
    :return datatime: The next retry datetime.
    """

    backoff_event = BackoffEvent.objects.filter(
        email_address=recipient,
    ).first()
    if backoff_event:
        # Return backoff event next_retry_date and add an additional minute
        return backoff_event.next_retry_date + timedelta(minutes=1)

    # In case we don't have an active backoff event it means that it was
    # deleted due to an incoming delivery notification, in this case, we could
    # retry messages as soon as possible.
    return now()


def is_message_stored(message_id: str) -> bool:
    """Returns True if the message is stored in database.

    :param message_id: The message unique identifier.
    :return bool: True if the message is available in database, otherwise False
    """
    if message_id:
        if EmailSent.objects.filter(message_id=message_id).exists():
            return True
    return False


from cl.users.tasks import send_failed_email


def schedule_failed_email(recipient_email: str) -> None:
    """Schedule recipient's waiting failed emails after receiving a delivery
    notification because it means the recipient's inbox is working again.

    :param recipient_email: The recipient's email address to whom the delivery
    notification belongs
    :return: None
    """

    # Look for FailedEmail objects in WAITING status.
    failed_messages = FailedEmail.objects.filter(
        recipient=recipient_email, status=STATUS_TYPES.WAITING
    )
    # Before clean possible failed objects.
    delete_failed_tasks_objects(recipient_email)

    # Get the next retry datetime to schedule the message, in this case now()
    scheduled_datetime = get_next_retry_date(recipient_email)
    # If the recipient has multiple messages to retry we'll send one message
    # per minute.
    minutes = 1
    for fail_message in failed_messages:
        # Set schedule timen and update status to ENQUEUED_DELIVERY
        next_retry_datetime = scheduled_datetime + timedelta(minutes=minutes)
        fail_message.next_retry_date = next_retry_datetime
        fail_message.status = STATUS_TYPES.ENQUEUED_DELIVERY
        fail_message.save()
        # Call celery task.
        send_failed_email(fail_message.pk, next_retry_datetime)
        minutes += 1


def enqueue_email(recipients: list[str], message_id: str) -> None:
    """Enqueue a message for a list of recipients, due to a soft bounce or if
    the recipient is under a backoff event waiting period.

    :param recipients: The list of recipients to enqueue the message.
    :param message_id: The message unique identifier.
    :return None:
    """

    if is_message_stored(message_id):
        for recipient in recipients:
            # Before clean possible failed objects.
            delete_failed_tasks_objects(recipient)

            # Get the next retry datetime to schedule the message, based on the
            # active backoff event.
            scheduled_datetime = get_next_retry_date(recipient)

            # If not exists previously, enqueue the message as ENQUEUED status
            failed, created = FailedEmail.objects.get_or_create(
                recipient=recipient,
                status=STATUS_TYPES.ENQUEUED,
                defaults={
                    "message_id": message_id,
                    "next_retry_date": scheduled_datetime,
                },
            )
            if created:
                # If the ENQUEUED FailedEmail object was created, schedule the
                # celery task, in this way we ensure we have a message to send
                # to the user once the backoff event waiting period expires
                send_failed_email(failed.pk, scheduled_datetime)
            else:
                # If the recipient has already a scheduled message, enqueue the
                # next messages with WAITING status, these objects are going to
                # be scheduled when receiving a delivery notification.
                FailedEmail.objects.create(
                    recipient=recipient,
                    status=STATUS_TYPES.WAITING,
                    message_id=message_id,
                    next_retry_date=scheduled_datetime,
                )
    else:
        logging.warning(
            f"The message: {message_id} can't be enqueued because it "
            "doesn't exist anymore."
        )
