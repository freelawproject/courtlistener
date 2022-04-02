from threading import local

from django.conf import settings
from django.core.mail import get_connection
from django.core.mail.backends.base import BaseEmailBackend

from cl.lib.command_utils import logger
from cl.users.email_handlers import (
    compose_message,
    convert_list_to_str,
    get_email_body,
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

    def open(self):
        pass

    def close(self):
        pass

    def send_messages(self, email_messages):

        if not email_messages:
            return

        # Open a connection for the BASE_BACKEND set in settings.
        backend = settings.BASE_BACKEND
        connection = get_connection(backend)
        connection.open()
        for email_message in email_messages:

            subject = email_message.subject
            from_email = email_message.from_email
            to = email_message.to
            bcc = email_message.bcc
            cc = email_message.cc
            reply_to = email_message.reply_to
            headers = email_message.extra_headers
            message = email_message.message()

            # Verify if recipient email address is banned.
            banned_email = EmailFlag.objects.filter(
                email_address=convert_list_to_str(to),
                object_type=OBJECT_TYPES.BAN,
            )

            if banned_email.exists():
                continue

            # If the recipient's email address is not banned continue,
            # otherwise the message is discarded.
            # Retrieve plain normal body and html normal body
            [plaintext_body, html_body] = get_email_body(
                message,
                plain="text/plain",
                html="text/html",
            )

            # Compute attachments total size in bytes
            attachment_size = 0
            for attachment in email_message.attachments:
                # An attachment is a tuple: (filename, content, mimetype)
                # with attachment[1] we obtain the base64 file content
                # so we can obtain the file size in bytes with len()
                attachment_size = len(attachment[1]) + attachment_size

            # Check if the message contains a small version
            small_version = False
            for part in message.walk():
                if (
                    part.get_content_type() == "text/plain_small"
                    or part.get_content_type() == "text/html_small"
                ):
                    small_version = True
                    continue

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

                    # Retrieve plain small body and html small body
                    [plain_small_body, html_small_body] = get_email_body(
                        message,
                        plain="text/plain_small",
                        html="text/html_small",
                    )

                    # Store small message in DB and obtain the unique
                    # message_id to add in headers to identify the message
                    stored_id = store_message(
                        from_email=from_email,
                        to=to,
                        bcc=bcc,
                        cc=cc,
                        reply_to=reply_to,
                        subject=subject,
                        message=plain_small_body,
                        html_message=html_small_body,
                        headers=headers,
                    )

                    # Compose small messages without attachments
                    # according to available content types

                    email = compose_message(
                        html_body=html_small_body,
                        plain_body=plain_small_body,
                        from_email=from_email,
                        to=to,
                        bcc=bcc,
                        cc=cc,
                        reply_to=reply_to,
                        subject=subject,
                        headers=headers,
                    )

                else:

                    # If not small version and not small flag or file size
                    # limit get rid of small version

                    # Store normal message in DB and obtain the unique
                    # message_id to add in headers to identify the message
                    stored_id = store_message(
                        from_email=from_email,
                        to=to,
                        bcc=bcc,
                        cc=cc,
                        reply_to=reply_to,
                        subject=subject,
                        message=plaintext_body,
                        html_message=html_body,
                        headers=headers,
                    )

                    # Compose normal messages with attachments
                    # according to available content types.
                    # Discard text/plain_small and text/html_small
                    # content types.

                    email = compose_message(
                        html_body=html_body,
                        plain_body=plaintext_body,
                        from_email=from_email,
                        to=to,
                        bcc=bcc,
                        cc=cc,
                        reply_to=reply_to,
                        subject=subject,
                        headers=headers,
                    )

                    # Add attachments
                    for attachment in email_message.attachments:
                        # An attachment is a tuple:
                        # (filename, content, mimetype)
                        email.attach(
                            attachment[0], attachment[1], attachment[2]
                        )

            else:
                # Store message in DB and obtain the unique message_id to
                # add in headers to identify the message
                stored_id = store_message(
                    from_email=from_email,
                    to=to,
                    bcc=bcc,
                    cc=cc,
                    reply_to=reply_to,
                    subject=subject,
                    message=plaintext_body,
                    html_message=html_body,
                    headers=headers,
                )
                # If not small version, send original message.
                email = email_message

            # Use backend connection
            email.connection = connection
            # Add header to with the unique message_id
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
                try:
                    email.send()
                except Exception as e:
                    # Log an error
                    logger.error(f"Error sending email: {e}")

        # Close email backend connection
        connection.close()
