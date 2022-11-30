import sys
import time
from datetime import timedelta

from django.db import transaction
from django.utils.timezone import now

from cl.api.models import WEBHOOK_EVENT_STATUS, WebhookEvent
from cl.api.utils import send_webhook_event
from cl.lib.command_utils import VerboseCommand

DAYS_TO_DELETE = 90


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


def delete_old_webhook_events() -> int | None:
    """Delete webhook events older than DAYS_TO_DELETE days.
    This is executed once a day at 12:00 UTC (4:00 PDT)

    :return: The number of deleted webhooks events or None if it's not time to
    execute the method.
    """

    minute_of_the_day = now().hour * 60 + now().minute
    # 12:00 UTC -> 4:00 PDT (minute 720 of the day)
    if minute_of_the_day == 720:
        # Older than DAYS_TO_DELETE days
        days = DAYS_TO_DELETE
        older_than = now() - timedelta(days=days)
        webhooks_events_to_delete = WebhookEvent.objects.filter(
            date_created__lt=older_than
        )
        deleted_count = len(webhooks_events_to_delete)
        webhooks_events_to_delete.delete()
        return deleted_count
    return None


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

            # Delete old webhook events.
            deleted_count = delete_old_webhook_events()
            if deleted_count is not None:
                sys.stdout.write(f"{deleted_count} webhook events deleted.")

            time.sleep(self.DELAY_BETWEEN_ITERATIONS)
