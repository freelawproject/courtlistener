import sys
import time
from datetime import timedelta

from django.db import transaction
from django.utils.timezone import now

from cl.api.models import WEBHOOK_EVENT_STATUS, Webhook, WebhookEvent
from cl.api.webhooks import send_webhook_event
from cl.lib.command_utils import VerboseCommand
from cl.lib.redis_utils import get_redis_interface
from cl.users.tasks import send_webhook_still_disabled_email

DAYS_TO_DELETE = 90

# It must be greater than the elapsed time after reaching the max retries.
# Currently, that's about 54 hours (3 min delay with 3× backoff).
HOURS_WEBHOOKS_CUT_OFF = 60


def retry_webhook_events() -> int:
    """Retry Webhook events that need to be retried.

    :return: Number of retried webhooks .
    """

    with transaction.atomic():
        created_date_cut_off = now() - timedelta(hours=HOURS_WEBHOOKS_CUT_OFF)
        base_events = WebhookEvent.objects.select_for_update().filter(
            next_retry_date__lte=now(),
            debug=False,
            webhook__enabled=True,
        )
        # Mark as failed webhook events older than HOURS_WEBHOOKS_CUT_OFF hours
        # avoid retrying.
        failed_webhook_events = base_events.filter(
            event_status__in=[
                WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                WEBHOOK_EVENT_STATUS.ENDPOINT_DISABLED,
            ],
            date_created__lt=created_date_cut_off,
        ).update(event_status=WEBHOOK_EVENT_STATUS.FAILED, date_modified=now())

        # Restore retry counter to 0 for ENDPOINT_DISABLED events after
        # webhook is re-enabled.
        webhook_events_to_restart = base_events.filter(
            event_status=WEBHOOK_EVENT_STATUS.ENDPOINT_DISABLED,
            date_created__gte=created_date_cut_off,
        ).update(retry_counter=0, date_modified=now())

        webhook_events_to_retry = base_events.filter(
            event_status__in=[
                WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                WEBHOOK_EVENT_STATUS.ENDPOINT_DISABLED,
            ],
            date_created__gte=created_date_cut_off,
        ).order_by("date_created")
        for webhook_event in webhook_events_to_retry:
            send_webhook_event(webhook_event)
    return len(webhook_events_to_retry)


def delete_old_webhook_events() -> int:
    """Delete webhook events older than DAYS_TO_DELETE days.
    This is executed once a day at 12:00 UTC (4:00 PDT)

    :return: The number of deleted webhooks events.
    """

    older_than = now() - timedelta(days=DAYS_TO_DELETE)
    webhooks_events_to_delete = WebhookEvent.objects.filter(
        date_created__lt=older_than
    ).delete()
    return webhooks_events_to_delete[0]


def notify_webhooks_still_disabled() -> int:
    """Send a notification to webhook owners if one of their webhook endpoints
    is still disabled after 1, 2, and 3 days.

    :return: The number of notifications sent.
    """

    four_days_ago = now() - timedelta(days=4)
    one_day_ago = now() - timedelta(days=1)
    webhooks_disabled = Webhook.objects.filter(
        enabled=False, date_modified__range=(four_days_ago, one_day_ago)
    )
    for webhook in webhooks_disabled:
        send_webhook_still_disabled_email(webhook.pk)
    return len(webhooks_disabled)


def check_if_executed_today() -> bool:
    """Stores in redis a key to check if the task has been executed today.

    :return: True if the task has already been executed today, otherwise False
    """
    daemon_key = "daemon:webhooks:executed"
    r = get_redis_interface("CACHE", decode_responses=False)
    exists_daemon_key = r.get(daemon_key)
    if exists_daemon_key:
        return True
    r.set(daemon_key, "True", ex=60 * 15)
    return False


def execute_additional_tasks() -> tuple[int | None, int | None]:
    """Wrapper to execute additional webhook tasks once a day.

    :return: A two tuple of webhook events deleted, webhooks still disabled
    notifications sent or None, None if it's not time to execute.
    """

    webhook_events_deleted, notifications_sent = None, None
    if now().hour == 12 and now().minute < 10:
        # This check might be executed anytime between 12:00 UTC to 12:10 UTC
        # (4:00 PDT  to 4:10 PDT) to ensure it's executed even if a previous
        # task lasts some minutes. If a previous task lasts more than 10
        # minutes, we'll need to tweak this time.
        if check_if_executed_today():
            return webhook_events_deleted, notifications_sent

        notifications_sent = notify_webhooks_still_disabled()
        webhook_events_deleted = delete_old_webhook_events()
    return webhook_events_deleted, notifications_sent


class Command(VerboseCommand):
    """Command to retry enqueued failed webhooks."""

    help = "Retry enqueued failed webhooks."

    DELAY_BETWEEN_ITERATIONS = 1 * 60  # One minute

    def handle(self, *args, **options):
        super().handle(*args, **options)

        # Execute it continuously with a delay of one minute between iterations
        while True:
            # Delete old webhook events.
            deleted_count, notifications_sent = execute_additional_tasks()
            if deleted_count is not None:
                sys.stdout.write(f"{deleted_count} webhook events deleted.\n")
            if notifications_sent is not None:
                sys.stdout.write(
                    f"{notifications_sent} disabled webhook notifications sent.\n"
                )

            sys.stdout.write("Retrying failed webhooks...\n")
            webhooks_retried = retry_webhook_events()
            sys.stdout.write(f"{webhooks_retried} webhooks retried.\n")

            time.sleep(self.DELAY_BETWEEN_ITERATIONS)
