import logging
from urllib.parse import urljoin

from celery import Task
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.timezone import now
from requests.exceptions import Timeout

from cl.api.models import Webhook, WebhookEvent
from cl.celery_init import app
from cl.lib.email_utils import make_multipart_email
from cl.lib.neon_utils import NeonClient

logger = logging.getLogger(__name__)


def abort_or_retry(task, exc):
    """Abort a task if we've run out of retries. Else, retry it."""
    if task.request.retries == task.max_retries:
        return
    else:
        raise task.retry(exc=exc)


@app.task(
    bind=True,
    autoretry_for=(Timeout,),
    max_retries=3,
    interval_start=5,
    ignore_result=True,
)
def create_neon_account(self: Task, user_id: int) -> None:
    """
    Checks for existing Neon CRM accounts using the user's email address
    and handles account creation or raises AssertionError when multiple
    unmerged accounts share the same email address, requiring further
    action to maintain data integrity.

    Args:
        user_id (int): The ID of the user to check and potentially create an
        account for.

    Raises:
        AssertionError: If more than one matching account is found in Neon CRM.
    """
    user = User.objects.select_related("profile").get(pk=user_id)
    neon_client = NeonClient()
    neon_accounts = neon_client.search_account_by_email(user.email)

    if len(neon_accounts) > 1:
        # Neon CRM automatically merges accounts with identical names and
        # email addresses. This process, called Account Match feature, ensures
        # consistent data across records. However, If the accounts are very
        # close (email and phone match but not name) the accounts will be
        # entered into the Partial Match Queue. This queue allows users to
        # review these potential matches and decide whether to merge them
        # manually.
        raise AssertionError(
            "There's more than one account using the same email address. "
            "We should check the Partial Match Queue."
        )

    profile = user.profile  # type: ignore
    if len(neon_accounts) == 1:
        # We found an existing account that matches the email address. we'll
        # use that one instead of creating a new one to avoid potential future
        # merges.
        profile.neon_account_id = neon_accounts[0]["Account ID"]
        profile.save()
        return None

    new_account_id = neon_client.create_account(user)
    profile.neon_account_id = new_account_id
    profile.save()


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
