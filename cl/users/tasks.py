import logging
from urllib.parse import urljoin

import requests
from celery import Task
from django.conf import settings
from django.utils.timezone import now

from cl.api.models import Webhook, WebhookEvent
from cl.celery_init import app
from cl.lib.email_utils import make_multipart_email

logger = logging.getLogger(__name__)


def abort_or_retry(task, exc):
    """Abort a task if we've run out of retries. Else, retry it."""
    if task.request.retries == task.max_retries:
        return
    else:
        raise task.retry(exc=exc)


@app.task(
    bind=True, max_retries=5, interval_start=5 * 60, interval_step=5 * 60
)
def update_moosend_subscription(self: Task, email: str, action: str) -> None:
    """Subscribe or unsubscribe email address to moosend mailing list.

    Perform update if email address is already registered.

    :param self: The celery task
    :param email: The user's email address
    :param action: Action to perfom on moosend
    :return: None
    """
    allowed_actions = ["subscribe", "unsubscribe"]
    assert action in allowed_actions, f"'{action}' is not an allowed action."
    params = {"apikey": settings.MOOSEND_API_KEY}  # type: ignore

    if action == "subscribe":
        path = f"/v3/subscribers/{settings.MOOSEND_DEFAULT_LIST_ID}/subscribe.json"  # type: ignore
    else:
        path = f"/v3/subscribers/{settings.MOOSEND_DEFAULT_LIST_ID}/unsubscribe.json"  # type: ignore

    try:
        r = requests.post(
            url=urljoin(settings.MOOSEND_API_URL, path),  # type: ignore
            params=params,
            json={
                "Email": email,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        abort_or_retry(self, exc)
        return

    j = r.json()
    code = j.get("Code")

    if code == 0:
        logger.info(
            "Successfully completed '%s' action on '%s' in moosend.",
            action,
            email,
        )
    else:
        error = j.get("Error", "Unknown error")
        logger.warning(
            "Did not complete '%s' action on '%s' in moosend: '%s'",
            action,
            email,
            error,
        )


@app.task(ignore_result=True)
def notify_new_or_updated_webhook(
    webhook_pk: int,
    created: bool,
) -> None:
    """Send a notification to the admins if a webhook was created or updated.

    :param webhook_pk: The webhook PK that was created or updated.
    :param created: Whether the webhook was just created or not.
    :return: None
    """

    webhook = Webhook.objects.get(pk=webhook_pk)

    action = "created" if created else "updated"
    subject = f"A webhook was {action}"
    txt_template = "emails/new_or_updated_webhook.txt"
    html_template = "emails/new_or_updated_webhook.html"
    context = {"webhook": webhook, "action": action}
    msg = make_multipart_email(
        subject,
        html_template,
        txt_template,
        context,
        [a[1] for a in settings.MANAGERS],
    )
    msg.send()


@app.task(ignore_result=True)
def notify_failing_webhook(
    webhook_event_pk: int,
    failure_counter: int,
    webhook_enabled: bool,
) -> None:
    """Send a notification to the webhook user when a webhook event fails, or
    it has been disabled.

    :param webhook_event_pk: The related webhook event PK.
    :param failure_counter: The current webhook event failure counter.
    :param webhook_enabled: Whether the webhook has been disabled.
    :return: None
    """

    webhook_event = WebhookEvent.objects.get(pk=webhook_event_pk)
    webhook = webhook_event.webhook
    first_name = webhook.user.first_name
    subject = f"[Action Needed]: Your {webhook.get_event_type_display()} webhook is failing."
    if not webhook_enabled:
        subject = f"[Action Needed]: Your {webhook.get_event_type_display()} webhook is now disabled."
    txt_template = "emails/failing_webhook.txt"
    html_template = "emails/failing_webhook.html"
    context = {
        "webhook": webhook,
        "webhook_event_pk": webhook_event_pk,
        "failure_counter": failure_counter,
        "first_name": first_name,
        "disabled": not webhook_enabled,
    }
    msg = make_multipart_email(
        subject, html_template, txt_template, context, [webhook.user.email]
    )
    msg.send()


def get_days_disabled(webhook: Webhook) -> str:
    """Compute and return a string saying the number of days the webhook has
    been disabled.

    :param: The related Webhook object.
    :return: A string with the number of days the webhook has been disabled.
    """

    date_disabled = webhook.date_modified
    today = now()
    days = (today - date_disabled).days
    str_day = "day"
    if days > 1:
        str_day = "days"
    return f"{days} {str_day}"


@app.task(ignore_result=True)
def send_webhook_still_disabled_email(webhook_pk: int) -> None:
    """Send an email to the webhook owner when a webhook endpoint is
    still disabled after 1, 2, and 3 days.

    :param webhook_pk: The related webhook PK.
    :return: None
    """

    webhook = Webhook.objects.get(pk=webhook_pk)
    first_name = webhook.user.first_name
    days_disabled = get_days_disabled(webhook)
    subject = f"[Action Needed]: Your {webhook.get_event_type_display()} webhook has been disabled for {days_disabled}."
    txt_template = "emails/webhook_still_disabled.txt"
    html_template = "emails/webhook_still_disabled.html"
    context = {
        "webhook": webhook,
        "first_name": first_name,
    }
    msg = make_multipart_email(
        subject, html_template, txt_template, context, [webhook.user.email]
    )
    msg.send()
