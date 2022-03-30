from threading import local

from django.conf import settings
from django.core.mail import (
    EmailMessage,
    EmailMultiAlternatives,
    get_connection,
)
from django.core.mail.backends.base import BaseEmailBackend

from cl.lib.command_utils import logger
from cl.users.email_handlers import (
    convert_list_to_str,
    get_email_body,
    store_message,
)
from cl.users.models import OBJECT_TYPES, BackoffEvent, EmailFlag


class ConnectionHandler:
    """This is an email backend connection handler, based on
    django-post-office/connections.py
    """

    def __init__(self):
        self._connections = local()

    def __getitem__(self, alias):
        try:
            return self._connections.connections[alias]
        except AttributeError:
            self._connections.connections = {}
        except KeyError:
            pass

        backend = settings.BASE_BACKEND
        connection = get_connection(backend)
        connection.open()
        self._connections.connections[alias] = connection
        return connection

    def all(self):
        return getattr(self._connections, "connections", {}).values()

    def close(self):
        for connection in self.all():
            connection.close()


connections = ConnectionHandler()


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

        for email_message in email_messages:
            subject = email_message.subject
            from_email = email_message.from_email
            to = email_message.to
            bcc = email_message.bcc
            cc = email_message.cc
            headers = email_message.extra_headers
            message = email_message.message()

            # Open a connection for the BASE_BACKEND set in settings.
            connection = connections["default"]

            # Verify if recipient email address is banned.
            banned_email = EmailFlag.objects.filter(
                email_address=convert_list_to_str(to),
                object_type=OBJECT_TYPES.BAN,
            )

            # If the recipient's email address is not banned continue,
            # otherwise the message is discarded.
            if not banned_email.exists():

                # Retrieve plain normal body and html normal body
                [plaintext_body, html_body] = get_email_body(
                    message,
                    plain="text/plain",
                    html="text/html",
                )

                # Compute attachments total size in bytes
                attachment_size = 0
                for attachment in email_message.attachments:
                    attachment_size = len(attachment[1]) + attachment_size

                # Check if the message contains a small version
                plain_small = ""
                html_small = ""
                small_version = False
                for part in message.walk():
                    if part.get_content_type() == "text/plain_small":
                        plain_small = part.get_payload()
                        small_version = True
                        if html_small:
                            break
                    if part.get_content_type() == "text/html_small":
                        html_small = part.get_payload()
                        small_version = True
                        if plain_small:
                            break

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
                            cc=cc,
                            bcc=bcc,
                            subject=subject,
                            message=plain_small_body,
                            html_message=html_small_body,
                            headers=headers,
                        )

                        # Compose small messages without attachments
                        # according to available content types
                        if html_small_body:
                            if plain_small_body:
                                email = EmailMultiAlternatives(
                                    subject=subject,
                                    body=plain_small_body,
                                    from_email=from_email,
                                    to=to,
                                    bcc=bcc,
                                    cc=cc,
                                    headers=headers,
                                    connection=connection,
                                )
                                email.attach_alternative(
                                    html_small_body, "text/html"
                                )
                            else:
                                email = EmailMultiAlternatives(
                                    subject=subject,
                                    body=html_small_body,
                                    from_email=from_email,
                                    to=to,
                                    bcc=bcc,
                                    cc=cc,
                                    headers=headers,
                                    connection=connection,
                                )
                                email.content_subtype = "html"
                        else:
                            email = EmailMessage(
                                subject=subject,
                                body=plain_small_body,
                                from_email=email_message.from_email,
                                to=email_message.to,
                                bcc=email_message.bcc,
                                cc=email_message.cc,
                                connection=connection,
                                headers=headers,
                            )

                    else:

                        # Store normal message in DB and obtain the unique
                        # message_id to add in headers to identify the message
                        stored_id = store_message(
                            from_email=from_email,
                            to=to,
                            cc=cc,
                            bcc=bcc,
                            subject=subject,
                            message=plaintext_body,
                            html_message=html_body,
                            headers=headers,
                        )

                        # Compose normal messages with attachments
                        # according to available content types.
                        # Discard text/plain_small and text/html_small
                        # content types.
                        if html_body:
                            if plaintext_body:
                                email = EmailMultiAlternatives(
                                    subject=subject,
                                    body=plaintext_body,
                                    from_email=from_email,
                                    to=to,
                                    bcc=bcc,
                                    cc=cc,
                                    headers=headers,
                                    connection=connection,
                                )
                                email.attach_alternative(
                                    html_body, "text/html"
                                )
                            else:
                                email = EmailMultiAlternatives(
                                    subject=subject,
                                    body=html_body,
                                    from_email=from_email,
                                    to=to,
                                    bcc=bcc,
                                    cc=cc,
                                    headers=headers,
                                    connection=connection,
                                )
                                email.content_subtype = "html"
                        else:
                            email = EmailMessage(
                                subject=subject,
                                body=plaintext_body,
                                from_email=email_message.from_email,
                                to=email_message.to,
                                bcc=email_message.bcc,
                                cc=email_message.cc,
                                connection=connection,
                                headers=headers,
                            )

                        # Add attachments
                        for attachment in email_message.attachments:
                            # file name, file data, file content type
                            email.attach(
                                attachment[0], attachment[1], attachment[2]
                            )

                else:
                    # Store message in DB and obtain the unique message_id to
                    # add in headers to identify the message
                    stored_id = store_message(
                        from_email=from_email,
                        to=to,
                        cc=cc,
                        bcc=bcc,
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
                if (
                    backoff_event.under_waiting_period
                    if backoff_event
                    else False
                ):
                    # TODO QUEUE email
                    pass
                else:
                    # If not under backoff waiting period, continue sending.

                    try:
                        email.send()
                    except Exception as e:
                        # Log an error
                        logger.error(f"Error sending email: {e}")
                    connections.close()
