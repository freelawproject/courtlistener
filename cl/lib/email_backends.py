from collections.abc import Sequence

from django.conf import settings
from django.core.mail import (
    EmailMessage,
    EmailMultiAlternatives,
    get_connection,
)
from django.core.mail.backends.base import BaseEmailBackend

from cl.users.email_handlers import (
    compose_message,
    convert_list_to_str,
    has_small_version,
    store_message,
)
from cl.users.models import OBJECT_TYPES, BackoffEvent, EmailFlag


class EmailBackend(BaseEmailBackend):
    """This is a custom email backend to handle sending an email with some
    extra functions before the email is sent.

    Is neccesary to set the following settings:
    BASE_BACKEND: The base email backend to use to send emails, in our case:
    django_ses.SESBackend, for testing is used:
    django.core.mail.backends.locmem.EmailBackend
    MAX_ATTACHMENT_SIZE: The maximum file size in bytes that an attachment can
    have to be sent.

    - Verifies if the recipient's email address is not banned before sending
    or storing the message.
    - Stores a message in DB, generates a unique message_id.
    - Verifies if the recipient's email address is under a backoff event
    waiting period.
    - Verifies if the recipient's email address is small_email_only flagged
    or if attachments exceed MAX_ATTACHMENT_SIZE, if so send the small email
    version.
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
        msg_count = 0
        for email_message in email_messages:
            to = email_message.to
            message = email_message.message()

            # Verify if the recipient's email address is banned.
            banned_email = EmailFlag.objects.filter(
                email_address=convert_list_to_str(to),
                object_type=OBJECT_TYPES.BAN,
            )
            if banned_email.exists():
                continue
            # If the recipient's email address is not banned continue,
            # otherwise the message is discarded.

            # Compute attachments total size in bytes
            attachment_size = 0
            for attachment in email_message.attachments:
                # An attachment is a tuple: (filename, content, mimetype)
                # with attachment[1] we obtain the base64 file content
                # so we can obtain the file size in bytes with len()
                attachment_size = len(attachment[1]) + attachment_size

            small_version = has_small_version(message)
            if small_version:
                # If the message has a small version
                small_only = EmailFlag.objects.filter(
                    email_address=convert_list_to_str(to),
                    object_type=OBJECT_TYPES.FLAG,
                    flag=EmailFlag.SMALL_ONLY,
                )
                if (
                    small_only.exists()
                    or attachment_size > settings.MAX_ATTACHMENT_SIZE
                ):
                    # If email address is small_only_email flagged or
                    # attachments exceed the MAX_ATTACHMENT_SIZE

                    # Compose small messages without attachments
                    # according to available content types
                    email = compose_message(email_message, small_version=True)
                else:
                    # If not small flag or not file size limit exceeded
                    # get rid of small version

                    # Compose normal messages with attachments
                    # according to available content types.
                    # Discard text/plain_small and text/html_small
                    # content types.
                    email = compose_message(email_message, small_version=False)
                    # Add attachments
                    for attachment in email_message.attachments:
                        # An attachment is a tuple:filename, content, mimetype
                        email.attach(
                            attachment[0], attachment[1], attachment[2]
                        )
            else:
                # If not small version, send original message.
                email = email_message

            # Use base backend connection to send the message
            email.connection = connection

            # Store message in DB and obtain the unique
            # message_id to add in headers to identify the message
            stored_id = store_message(email_message)
            # Add header with unique message_id to identify message
            email.extra_headers["X-CL-ID"] = stored_id

            # Verify if recipient email address is under a backoff event
            backoff_event = BackoffEvent.objects.filter(
                email_address=convert_list_to_str(to),
            ).first()

            # If backoff event exists, check if it's under waiting period
            if backoff_event.under_waiting_period if backoff_event else False:
                # TODO QUEUE email
                pass
            else:
                # If not under backoff waiting period, continue sending.
                email.send()
                msg_count += 1

        # Close base backend connection
        connection.close()
        return msg_count
