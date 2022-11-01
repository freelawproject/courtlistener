import logging
from urllib.parse import urljoin

import requests
from celery import Task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import loader

from cl.api.models import Webhook
from cl.celery_init import app

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
    params = {"apikey": settings.MOOSEND_API_KEY}

    if action == "subscribe":
        path = f"/v3/subscribers/{settings.MOOSEND_DEFAULT_LIST_ID}/subscribe.json"
    else:
        path = f"/v3/subscribers/{settings.MOOSEND_DEFAULT_LIST_ID}/unsubscribe.json"

    try:
        r = requests.post(
            url=urljoin(settings.MOOSEND_API_URL, path),
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
    :created: Whether the webhook was just created or not.
    :return: None
    """

    webhook = Webhook.objects.get(pk=webhook_pk)

    action = "created" if created else "updated"
    subject = f"A webhook was {action}"
    txt_template = loader.get_template("emails/new_or_updated_webhook.txt")
    html_template = loader.get_template("emails/new_or_updated_webhook.html")
    context = {"webhook": webhook, "action": action}
    txt = txt_template.render(context)
    html = html_template.render(context)
    msg = EmailMultiAlternatives(
        subject,
        txt,
        settings.DEFAULT_FROM_EMAIL,
        [a[1] for a in settings.MANAGERS],
    )
    msg.attach_alternative(html, "text/html")
    msg.send()
