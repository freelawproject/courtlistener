import sys
import time
from datetime import timedelta

from django.db import transaction
from django.utils.timezone import now

from cl.api.models import WEBHOOK_EVENT_STATUS, WebhookEvent
from cl.api.utils import send_webhook_event
from cl.lib.command_utils import VerboseCommand


def retry_webhook_events() -> int:
    """Retry Webhook events that need to be retried.

    :return: Number of retried webhooks .
    """

    with transaction.atomic():
        cut_off_date_two_days = now() - timedelta(days=2)
        base_events = WebhookEvent.objects.select_for_update().filter(
            next_retry_date__lte=now(),
            debug=False,
            webhook__enabled=True,
        )
        # Mark as failed webhook events older than 2 days, avoid retrying.
        failed_webhook_events = base_events.filter(
            event_status__in=[
                WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                WEBHOOK_EVENT_STATUS.ENDPOINT_DISABLED,
            ],
            date_created__lt=cut_off_date_two_days,
        ).update(event_status=WEBHOOK_EVENT_STATUS.FAILED, date_modified=now())

        # Restore retry counter to 0 for ENDPOINT_DISABLED events after
        # webhook is re-enabled.
        webhook_events_to_restart = base_events.filter(
            event_status=WEBHOOK_EVENT_STATUS.ENDPOINT_DISABLED,
            date_created__gte=cut_off_date_two_days,
        ).update(retry_counter=0, date_modified=now())

        webhook_events_to_retry = base_events.filter(
            event_status__in=[
                WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                WEBHOOK_EVENT_STATUS.ENDPOINT_DISABLED,
            ],
            date_created__gte=cut_off_date_two_days,
        ).order_by("date_created")
        for webhook_event in webhook_events_to_retry:
            send_webhook_event(webhook_event)
    return len(webhook_events_to_retry)


class Command(VerboseCommand):
    """Command to retry enqueued failed webhooks."""

    help = "Retry enqueued failed webhooks."

    DELAY_BETWEEN_ITERATIONS = 1 * 60  # One minute

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        # Execute it continuously with a delay of one minute between iterations
        while True:
            sys.stdout.write("Retrying failed webhooks...")
            webhooks_retried = retry_webhook_events()
            sys.stdout.write(f"{webhooks_retried} webhooks retried.")
            time.sleep(self.DELAY_BETWEEN_ITERATIONS)
