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

    # Using select_for_update() and transaction.atomic() here will prevent more
    # than one instance retry pending webhooks, avoiding duplicated retries.
    webhook_events = (
        WebhookEvent.objects.select_for_update()
        .filter(
            event_status__in=[
                WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                WEBHOOK_EVENT_STATUS.ENDPOINT_DISABLED,
            ],
            next_retry_date__lte=now(),
            debug=False,
            webhook__enabled=True,
        )
        .order_by("date_created")
    )

    webhook_events_retried = 0
    with transaction.atomic():
        cut_off_date_two_days = now() - timedelta(days=2)
        for webhook_event in webhook_events:
            if webhook_event.date_created < cut_off_date_two_days:
                # Mark as failed webhook events older than 2 days, avoid
                # retrying.
                webhook_event.event_status = WEBHOOK_EVENT_STATUS.FAILED
                webhook_event.save()
                continue

            # Restore retry counter to 0 for ENDPOINT_DISABLED events after
            # Webhook is re-enabled.
            if (
                webhook_event.event_status
                == WEBHOOK_EVENT_STATUS.ENDPOINT_DISABLED
            ):
                webhook_event.retry_counter = 0
                webhook_event.save()

            send_webhook_event(webhook_event)
            webhook_events_retried += 1
    return webhook_events_retried


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
