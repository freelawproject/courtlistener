from collections.abc import Sequence

from django.conf import settings
from django.core.mail import (
    EmailMessage,
    EmailMultiAlternatives,
    get_connection,
)
from django.core.mail.backends.base import BaseEmailBackend
from redis import Redis

from cl.lib.redis_utils import make_redis_interface
from cl.users.email_handlers import (
    add_bcc_random,
    enqueue_email,
    is_not_email_banned,
    normalize_addresses,
    store_message,
    under_backoff_waiting_period,
)


def inc_email_emergency_brake_or_raise(r: Redis) -> None:
    """Checks the value of the delivery_attempts key or creates it
    if it's expired.

    Args:
        r (Redis): The Redis DB to connect to as a connection interface

    Raises:
        ValueError: if the counter is bigger than the threshold from the settings.
    """

    email_counter = r.get("email:delivery_attempts")
    if email_counter:
        if int(email_counter) >= settings.SENT_EMAILS_THRESHOLD:
            raise ValueError(
                "Emergency brake engaged to prevent email quota exhaustion"
            )
    else:
        pipe = r.pipeline()
        pipe.expire("email:delivery_attempts", 60 * 60 * 24)  # 24 hours period
        pipe.execute()


class EmailBackend(BaseEmailBackend):
    """This is a custom email backend to handle sending an email with some
    extra functions before the email is sent.

    Is neccesary to set the following settings:
    BASE_BACKEND: The base email backend to use to send emails, in our case:
    django_ses.SESBackend, for testing is used:
    django.core.mail.backends.locmem.EmailBackend

    - Verifies if the recipient's email address is not banned before sending
    or storing the message.
    - Stores a message in DB, generates a unique message_id.
    - Verifies if the recipient's email address is under a backoff event
    waiting period.
    - Compose messages according to available content types
    """

    def send_messages(
        self,
        email_messages: Sequence[EmailMessage | EmailMultiAlternatives],
    ) -> int:
        if not email_messages:
            return 0
        # Open a connection to the BASE_BACKEND set in settings (e.g: SES).
        base_backend = settings.BASE_BACKEND
        connection = get_connection(base_backend)
        connection.open()
        r = make_redis_interface("CACHE")
        inc_email_emergency_brake_or_raise(r)
        msg_count = 0
        for email_message in email_messages:
            message = email_message.message()
            original_recipients = normalize_addresses(email_message.to)
            recipient_list = []

            # Verify a recipient's email address is banned.
            for email_address in original_recipients:
                if is_not_email_banned(email_address):
                    recipient_list.append(email_address)

            # If all recipients are banned, the message is discarded
            if not recipient_list:
                continue

            email = email_message

            # Verify if email addresses are under a backoff waiting period
            final_recipient_list = []
            backoff_recipient_list = []
            for email_address in recipient_list:
                if under_backoff_waiting_period(email_address):
                    # If an email address is under a waiting period
                    # add to a backoff recipient list to queue the message
                    backoff_recipient_list.append(email_address)
                else:
                    # If an email address is not under a waiting period
                    # add to the final recipients list
                    final_recipient_list.append(email_address)

            # Store message in DB and obtain the unique
            # message_id to add in headers to identify the message
            stored_id = store_message(email_message)

            if backoff_recipient_list:
                # Enqueue message for recipients under a waiting backoff period
                enqueue_email(backoff_recipient_list, stored_id)

            # Add header with unique message_id to identify message
            email.extra_headers["X-CL-ID"] = stored_id
            # Use base backend connection to send the message
            email.connection = connection

            # Call add_bcc_random function to BCC the message based on the
            # EMAIL_BCC_COPY_RATE set
            email = add_bcc_random(email, settings.EMAIL_BCC_COPY_RATE)

            # If we have recipients to send the message to, we send it.
            if final_recipient_list:
                # Update message with the final recipient list
                email.to = final_recipient_list
                email.send()
                msg_count += 1

        # Close base backend connection
        connection.close()
        r.incrby("email:delivery_attempts", msg_count)
        return msg_count
