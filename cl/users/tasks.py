import logging
from datetime import datetime
from urllib.parse import urljoin

import requests
from celery import Task
from celery.canvas import chain
from django.conf import settings
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from cl.celery_init import app
from cl.lib.crypto import md5
from cl.users.models import STATUS_TYPES, FailedEmail

logger = logging.getLogger(__name__)

MC_BASE_URL = "https://us14.api.mailchimp.com/"
MC_LIST_ID = "ba547fa86b"


def abort_or_retry(task, exc):
    """Abort a task if we've run out of retries. Else, retry it."""
    if task.request.retries == task.max_retries:
        return
    else:
        raise task.retry(exc=exc)


@app.task(
    bind=True, max_retries=5, interval_start=5 * 60, interval_step=5 * 60
)
def subscribe_to_mailchimp(self, email):
    path = f"/3.0/lists/{MC_LIST_ID}/members/"
    try:
        r = requests.post(
            urljoin(MC_BASE_URL, path),
            json={
                "email_address": email,
                "status": "subscribed",
                "merge_fields": {},
            },
            headers={"Authorization": f"apikey {settings.MAILCHIMP_API_KEY}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        abort_or_retry(self, exc)
        return
    if r.status_code == HTTP_200_OK:
        logger.info("Successfully subscribed %s to mailchimp", email)
    elif r.status_code == HTTP_400_BAD_REQUEST:
        j = r.json()
        if j["title"] == "Member Exists":
            logger.info(
                "User with email '%s' already exists in mailchimp. "
                "Attempting via PATCH request.",
                email,
            )
            update_mailchimp(email, "subscribed")
    else:
        j = r.json()
        logger.warning(
            "Did not subscribe '%s' to mailchimp: '%s: %s'",
            (email, r.status_code, j["title"]),
        )


@app.task(
    bind=True, max_retries=5, interval_start=5 * 60, interval_step=5 * 60
)
def update_mailchimp(self, email, status):
    allowed_statuses = ["unsubscribed", "subscribed"]
    assert status in allowed_statuses, f"'{status}' is not an allowed status."
    md5_hash = md5(email)
    path = f"/3.0/lists/{MC_LIST_ID}/members/{md5_hash}"
    try:
        r = requests.patch(
            urljoin(MC_BASE_URL, path),
            json={"status": status},
            headers={"Authorization": f"apikey {settings.MAILCHIMP_API_KEY}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        abort_or_retry(self, exc)
        return
    if r.status_code == HTTP_200_OK:
        logger.info(
            "Successfully completed '%s' command on '%s' in mailchimp.",
            status,
            email,
        )
    elif r.status_code == HTTP_404_NOT_FOUND:
        logger.info(
            "Did not complete '%s' command on '%s' in mailchimp. "
            "Address not found.",
            status,
            email,
        )
    else:
        logger.warning(
            "Did not complete '%s' command on '%s' in mailchimp: '%s: %s'",
            status,
            email,
            r.status_code,
        )


@app.task(bind=True, max_retries=3, interval_start=5 * 60)
def process_retry_email(
    self: Task,
    failed_pk: int,
) -> int:
    """Task to retry failed email messages"""

    failed_email = FailedEmail.objects.get(pk=failed_pk)
    if failed_email.status != STATUS_TYPES.SUCCESSFUL:
        # Only execute this task if it has not been previously processed.
        failed_email.status = STATUS_TYPES.IN_PROGRESS
        failed_email.save()
        # Compose email from stored message.
        email = failed_email.stored_email.convert_to_email_multipart()
        try:
            email.send()
        except Exception as exc:
            # In case of error when sending e.g: SES downtime, retry the task.
            raise self.retry(exc=exc)
        failed_email.status = STATUS_TYPES.SUCCESSFUL
        failed_email.save()


def send_failed_email(
    failed_pk: int,
    start: datetime,
) -> None:
    return chain(
        process_retry_email.si(failed_pk),
    ).apply_async(eta=start)
