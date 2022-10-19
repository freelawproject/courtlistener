import sys
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from cl.lib.command_utils import VerboseCommand
from cl.users.email_handlers import schedule_failed_email
from cl.users.models import FLAG_TYPES, STATUS_TYPES, EmailFlag, FailedEmail


def periodic_send_failed_email() -> int:
    """Method to retry failed email messages periodically.

    Send failed emails that their status is ENQUEUED_DELIVERY or ENQUEUED.
    And their scheduled next_retry_date is smaller than the current time.

    :param: None
    :return: The number of failed emails sent.
    """

    enqueued_failed_email = FailedEmail.objects.select_for_update().filter(
        Q(status=STATUS_TYPES.ENQUEUED_DELIVERY)
        | Q(status=STATUS_TYPES.ENQUEUED),
        next_retry_date__lte=now(),
    )
    with transaction.atomic():
        for failed_email_to_send in enqueued_failed_email:
            failed_email_to_send.status = STATUS_TYPES.IN_PROGRESS
            failed_email_to_send.save()
            # Compose email from stored message.
            email = (
                failed_email_to_send.stored_email.convert_to_email_multipart()
            )
            email.send()
            failed_email_to_send.status = STATUS_TYPES.SUCCESSFUL
            failed_email_to_send.save()
    return len(enqueued_failed_email)


def periodic_check_recipient_deliverability() -> None:
    """Method to look for email addresses that are now deliverable after a
    backoff event expires.

    It works by looking for backoff events that need to be checked
    (checked False) and that have expired DELIVERABILITY_THRESHOLD hours ago.
    That is, they have not received a new bounce event recently:

    e.g: considering DELIVERABILITY_THRESHOLD = 1:
    - 11:00 bounce be1 -> next_retry_date 13:00, checked: False
    - 14:00 check_recipient_deliverability() be1 is now deliverable, no new
    bounce in the last hour

    - 11:00 bounce be2 -> next_retry_date 13:00, checked: False
    - 13:30 bounce be2 -> next_retry_date 17:30, checked: False
    - 14:00 check_recipient_deliverability() be2 is not deliverable, a new
    bounce in the last hour
    ...
    - 19:00 check_recipient_deliverability() be2 is now deliverable, no new
    bounce in the last hour

    Then waiting failed emails are scheduled to be sent.

    :param: None
    :return: None
    """

    active_backoff_events = EmailFlag.objects.select_for_update().filter(
        flag_type=FLAG_TYPES.BACKOFF,
        checked=False,
        next_retry_date__lte=now()
        - timedelta(hours=settings.DELIVERABILITY_THRESHOLD),
    )
    with transaction.atomic():
        for backoff_event in active_backoff_events:
            # There wasn't a new bounce recently, seems that the
            # recipient accepted the email, so we can schedule the waiting failed
            # emails to be sent.
            backoff_event.checked = True
            backoff_event.save()
            schedule_failed_email(backoff_event.email_address)


class Command(VerboseCommand):
    """Command to check email recipients' deliverability and send failed emails
    periodically."""

    help = "Check email recipients' deliverability or send failed emails."

    def add_arguments(self, parser):
        parser.add_argument(
            "--send-failed-email",
            action="store_true",
            default=False,
            help="Send failed email.",
        )
        parser.add_argument(
            "--check-recipients-deliverability",
            action="store_true",
            default=False,
            help="Check email recipients' deliverability",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        if options["send_failed_email"]:
            sys.stdout.write("Sending failed email...")
            email_sent = periodic_send_failed_email()
            sys.stdout.write(f"{email_sent} emails sent.")
            return

        if options["check_recipients_deliverability"]:
            sys.stdout.write("Checking recipients deliverability...")
            periodic_check_recipient_deliverability()
            return
