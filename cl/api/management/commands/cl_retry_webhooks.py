import sys
import time

from django.db import transaction
from django.utils.timezone import now

from cl.api.models import WEBHOOK_EVENT_STATUS, WebhookEvent
from cl.api.utils import send_webhook_event
from cl.lib.command_utils import VerboseCommand


def retry_webhook_events() -> int:
    """Retry Webhook events that need to be retried. Those in ENQUEUED_RETRY
    status and that their next_retry_date is lower or equal to the current time
    and their parent webhook is not disabled.

    :return: Number of retried webhooks .
    """

    # Using select_for_update() and transaction.atomic() here will prevent more
    # than one instance retry pending webhooks, avoiding duplicated retries.
    webhook_events = WebhookEvent.objects.select_for_update().filter(
        event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
        next_retry_date__lte=now(),
        webhook__enabled=True,
    )
    with transaction.atomic():
        for webhook_event in webhook_events:
            send_webhook_event(webhook_event)
    return len(webhook_events)


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
