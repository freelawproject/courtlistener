from collections.abc import Sequence

from django.conf import settings
from django.core.mail import (
    EmailMessage,
    EmailMultiAlternatives,
    get_connection,
)
from django.core.mail.backends.base import BaseEmailBackend

from cl.users.email_handlers import (
    add_bcc_random,
    compose_message,
    has_small_version,
    is_not_email_banned,
    is_small_only_flagged,
    normalize_addresses,
    store_message,
    under_backoff_waiting_period,
)


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

            # Compute attachments total size in bytes
            attachment_size = 0
            for attachment in email_message.attachments:
                # An attachment is a tuple: (filename, content, mimetype)
                # with attachment[1] we obtain the base64 file content
                # so we can obtain the file size in bytes with len()
                attachment_size = len(attachment[1]) + attachment_size

            small_version = has_small_version(message)
            if small_version:
                # Check if at least one recipient is small_email_only flagged
                send_small = False
                for email_address in recipient_list:
                    if is_small_only_flagged(email_address):
                        send_small = True
                        break
                if (
                    send_small
                    or attachment_size > settings.MAX_ATTACHMENT_SIZE
                ):
                    # If at least one recipient is small_only_email flagged or
                    # attachments exceed the MAX_ATTACHMENT_SIZE

                    # Compose small messages without attachments
                    # according to available content types
                    email = compose_message(email_message, small_version=True)
                else:
                    # If not small flag or not file size limit exceeded
                    # get rid of small version

                    # Compose normal messages with attachments according to
                    # available content types.
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
                # If no small version is available, send the original message
                email = email_message

            # Verify if email addresses are under a backoff waiting period
            final_recipient_list = []
            backoff_recipient_list = []
            for email_address in recipient_list:
                if under_backoff_waiting_period(email_address):
                    # If a email address is under a waiting period
                    # add to a backoff recipient list to queue the message
                    backoff_recipient_list.append(email_address)
                else:
                    # If a email address is not under a waiting period
                    # add to the final recipients list
                    final_recipient_list.append(email_address)

            if backoff_recipient_list:
                # TODO QUEUE email
                pass

            # Store message in DB and obtain the unique
            # message_id to add in headers to identify the message
            stored_id = store_message(email_message)
            # Add header with unique message_id to identify message
            email.extra_headers["X-CL-ID"] = stored_id
            # Use base backend connection to send the message
            email.connection = connection

            # Call the random function to determine if we should add or not
            # a BCC to the message based on the EMAIL_BCC_COPY_RATE set
            add_bcc = add_bcc_random(settings.EMAIL_BCC_COPY_RATE)
            if add_bcc == True:
                email.bcc.append(settings.BCC_EMAIL_ADDRESS)

            # If we have recipients to send the message to, we send it.
            if final_recipient_list:
                # Update message with the final recipient list
                email.to = final_recipient_list
                email.send()
                msg_count += 1

        # Close base backend connection
        connection.close()
        return msg_count
