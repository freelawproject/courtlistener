import hashlib
import logging
from urlparse import urljoin

import requests
from django.conf import settings
from rest_framework.status import HTTP_200_OK, HTTP_404_NOT_FOUND

from cl.celery import app

logger = logging.getLogger(__name__)

MC_BASE_URL = 'https://us14.api.mailchimp.com/'
MC_LIST_ID = 'ba547fa86b'


def abort_or_retry(task, exc):
    """Abort a task if we've run out of retries. Else, retry it."""
    if task.request.retries == task.max_retries:
        return
    else:
        raise task.retry(exc=exc)


@app.task(bind=True, max_retries=5, interval_start=5 * 60,
          interval_step=5 * 60)
def subscribe_to_mailchimp(self, email):
    path = '/3.0/lists/%s/members/' % MC_LIST_ID
    try:
        r = requests.post(
            urljoin(MC_BASE_URL, path),
            json={
                "email_address": email,
                "status": "subscribed",
                "merge_fields": {}
            },
            headers={"Authorization": 'apikey %s' % settings.MAILCHIMP_API_KEY}
        )
    except requests.RequestException as exc:
        abort_or_retry(self, exc)
        return
    if r.status_code == HTTP_200_OK:
        logger.info("Successfully subscribed %s to mailchimp", email)
    else:
        j = r.json()
        logger.warn("Did not subscribe '%s' to mailchimp: '%s: %s'",
                    (email, r.status_code, j['title']))


@app.task(bind=True, max_retries=5, interval_start=5 * 60,
          interval_step=5 * 60)
def unsubscribe_from_mailchimp(self, email):
    md5_hash = hashlib.md5(email).hexdigest()
    path = '/3.0/lists/%s/members/%s' % (MC_LIST_ID, md5_hash)
    try:
        r = requests.patch(
            urljoin(MC_BASE_URL, path),
            json={'status': 'unsubscribed'},
            headers={"Authorization": 'apikey %s' % settings.MAILCHIMP_API_KEY}
        )
    except requests.RequestException as exc:
        abort_or_retry(self, exc)
        return
    if r.status_code == HTTP_200_OK:
        logger.info("Successfully unsubscribed '%s' from mailchimp.", email)
    elif r.status_code == HTTP_404_NOT_FOUND:
        logger.info("Did not unsubscribe '%s' from mailchimp. Address not "
                    "found.", email)
    else:
        logger.warn("Did not unsubscribe '%s' from mailchimp: '%s: %s'",
                    (email, r.status_code))
