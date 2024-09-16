import sys
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from cl.lib.command_utils import VerboseCommand
from cl.users.email_handlers import schedule_failed_email
from cl.users.models import FLAG_TYPES, STATUS_TYPES, EmailFlag, FailedEmail


def handle_failing_emails() -> int:
    """Method to look for email addresses that are now deliverable after a
    backoff event expires and then retry failed email messages periodically.

    Checks recipients' deliverability:
    It works by looking for backoff events that need to be checked
    (checked None) and that have expired DELIVERABILITY_THRESHOLD hours ago.
    That is, they have not received a new bounce event recently:

    e.g: considering DELIVERABILITY_THRESHOLD = 1:
    - 11:00 bounce be1 -> next_retry_date 13:00, checked: None
    - 14:00 check_recipient_deliverability() be1 is now deliverable, no new
    bounce in the last hour

    - 11:00 bounce be2 -> next_retry_date 13:00, checked: None
    - 13:30 bounce be2 -> next_retry_date 17:30, checked: None
    - 14:00 check_recipient_deliverability() be2 is not deliverable, a new
    bounce in the last hour
    ...
    - 19:00 check_recipient_deliverability() be2 is now deliverable, no new
    bounce in the last hour

    Then waiting failed emails are scheduled to be sent.

    Send failed email:
    Send failed emails that their status is ENQUEUED_DELIVERY or ENQUEUED.
    And their scheduled next_retry_date is smaller than the current time.

    :param: None
    :return: The number of failed emails sent.
    """
    # Checks recipients' deliverability
    active_backoff_events = EmailFlag.objects.select_for_update().filter(
        flag_type=FLAG_TYPES.BACKOFF,
        checked=None,
        next_retry_date__lte=now()
        - timedelta(hours=settings.DELIVERABILITY_THRESHOLD),  # type: ignore
    )
    with transaction.atomic():
        for backoff_event in active_backoff_events:
            # There wasn't a new bounce recently, seems that the
            # recipient accepted the email, so we can schedule the waiting failed
            # emails to be sent.
            backoff_event.checked = now()
            backoff_event.save()
            schedule_failed_email(backoff_event.email_address)

    # Send failed email
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


class Command(VerboseCommand):
    """Command to check email recipients' deliverability and send failed emails
    periodically."""

    help = "Check email recipients' deliverability and send failed emails."

    def handle(self, *args, **options):
        super().handle(*args, **options)
        sys.stdout.write("Sending failed email...")
        email_sent = handle_failing_emails()
        sys.stdout.write(f"{email_sent} emails sent.")
        return
