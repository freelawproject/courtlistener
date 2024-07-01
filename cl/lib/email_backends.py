import time
from collections.abc import Sequence

from django.conf import settings
from django.core.mail import (
    EmailMessage,
    EmailMultiAlternatives,
    get_connection,
)
from django.core.mail.backends.base import BaseEmailBackend
from redis import Redis
from redis.client import Pipeline

from cl.lib.redis_utils import get_redis_interface
from cl.users.email_handlers import (
    add_bcc_random,
    enqueue_email,
    is_not_email_banned,
    normalize_addresses,
    store_message,
    under_backoff_waiting_period,
)


def get_email_prefix() -> str:
    """Simple helper for getting the prefix for the email counter.
    Useful for mocking the logger.
    """
    return "email"


def incr_email_counters(pipe: Pipeline) -> None:
    """increments the temporary counter and adds a new
    element to the sorted set once it reaches the value of
    the EMAILS_TEMP_COUNTER setting.

    Args:
        pipe (Pipeline): A pipeline object.
    """
    prefix = get_email_prefix()
    temp_counter = int(pipe.get(f"{prefix}:temp_counter") or 0)  # type: ignore
    pipe.multi()
    if int(temp_counter) + 1 >= settings.EMAIL_MAX_TEMP_COUNTER:
        current_time = time.time_ns()
        pipe.zadd(
            f"{prefix}:delivery_attempts", {str(current_time): current_time}
        )
        pipe.set(f"{prefix}:temp_counter", 0)
    else:
        pipe.incr(f"{prefix}:temp_counter")


def get_attempts_in_window(r: Redis) -> int:
    """
    Returns the number of elements stored in the set. This method
    check the current time, and shave off any attempts in the sorted set
    that are outside of our window, then check the cardinality of the
    sorted set

    Args:
        r (Redis): The Redis DB connection interface.

    Returns:
        int: number of elements stored in the set
    """
    current_time = time.time_ns()
    trim_time = current_time - (24 * 60 * 60 * 1_000_000_000)
    pipe = r.pipeline()
    prefix = get_email_prefix()
    # Removes attempts outside the current window
    pipe.zremrangebyscore(f"{prefix}:delivery_attempts", 0, trim_time)
    # Get number of elements in the set
    pipe.zcard(f"{prefix}:delivery_attempts")
    _removed, size = pipe.execute()
    return int(size)


def get_email_count(r: Redis) -> int:
    """Returns the number of email sent in the last 24 hours.

    This method multiplies the number of previous attempts by the
    MAX_TEMP_COUNTER setting because our approach only adds one entry
    to the email:delivery_attempts key after MAX_TEMP_COUNTER emails
    are sent.

    Args:
        r (Redis): The Redis DB connection interface.

    Returns:
        int: number of emails sent in the last 24 hours
    """
    prefix = get_email_prefix()
    temp_counter = r.get(f"{prefix}:temp_counter")
    previous_attempts = get_attempts_in_window(r)
    if not temp_counter:
        return previous_attempts * settings.EMAIL_MAX_TEMP_COUNTER
    return previous_attempts * settings.EMAIL_MAX_TEMP_COUNTER + int(
        temp_counter
    )


def check_emergency_brake(r: Redis) -> None:
    """
    Checks the emails sent in the last 24 hours. Raises ValueError
    if our threshold is exceeded.

    AWS SES uses a sliding window to calculate our email sending quota.
    When it runs out, we cannot recover without waiting ~24 hours, so
    this ensures that we always stay below a configured quota.

    Details: https://docs.aws.amazon.com/ses/latest/dg/manage-sending-quotas.html

    To do this, we implement the "sliding logs" algorithm, roughly as
    described here, but with one modification to minimize memory usage:

    https://medium.com/@SaiRahulAkarapu/rate-limiting-algorithms-using-redis-eb4427b47e33

    Sliding logs is a simple algorithm that logs a timestamp for every
    event that happens. Then, when an event request comes in, it checks
    how many events are in the log during the last period (in our case,
    24 hours), and either rejects or allows the event.

    Our tweak to this algorithm is to lose a small amount of accuracy
    (precisely EMAIL_MAX_TEMP_COUNTER - 1) in exchange for reducing
    the memory by EMAIL_MAX_TEMP_COUNTER×.

    For example, if EMAIL_MAX_TEMP_COUNTER is set to 10, then we log
    one entry to redis for every 10 events (great memory savings). but
    we may reject events at EMAIL_EMERGENCY_THRESHOLD - EMAIL_MAX_TEMP_COUNTER + 1
    instead of precisely when the threshold is exceeded. (E.g., if the
    threshold is 1_000 and temp counter is 10, we might trigger at 991).

    Args:
        r (Redis): The Redis DB to connect to as a connection interface

    Raises:
        ValueError: if the counter is bigger than the threshold from the settings.
    """
    current_email_count = get_email_count(r)
    if current_email_count >= settings.EMAIL_EMERGENCY_THRESHOLD:
        raise ValueError(
            "Emergency brake engaged to prevent email quota exhaustion"
        )


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
        r = get_redis_interface("CACHE")
        msg_count = 0
        for email_message in email_messages:
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

            # check the emergency brake before sending an email
            check_emergency_brake(r)
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
                # update the counters
                prefix = get_email_prefix()
                r.transaction(incr_email_counters, f"{prefix}:temp_counter")
                msg_count += 1

        # Close base backend connection
        connection.close()
        return msg_count
