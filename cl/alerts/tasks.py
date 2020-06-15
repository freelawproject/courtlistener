import logging

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template import loader
from django.utils.timezone import now

# TODO: Write MobileQuery code
from juriscraper.pacer import PacerSession, MobileQuery

from cl.alerts.models import DocketAlert
from cl.celery import app
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.pacer import map_cl_to_pacer_id
from cl.lib.pacer_session import get_or_cache_pacer_cookies
from cl.lib.redis_utils import make_redis_interface
from cl.lib.string_utils import trunc
from cl.scrapers.models import PACERMobilePageData
from cl.search.models import Docket, DocketEntry
from cl.stats.utils import tally_stat


logger = logging.getLogger(__name__)


def make_alert_key(d_pk):
    return "docket.alert.enqueued:%s" % d_pk


def enqueue_docket_alert(d_pk):
    """Enqueue a docket alert or punt it if there's already a task for it.

    :param d_pk: The ID of the docket we're going to send alerts for.
    :return: True if we enqueued the item, false if not.
    """
    # Create an expiring semaphor in redis or check if there's already one
    # there.
    r = make_redis_interface("ALERTS")
    key = make_alert_key(d_pk)
    # Set to True if not already set. Redis doesn't do bools anymore, so use 1.
    currently_enqueued = bool(r.getset(key, 1))
    if currently_enqueued:
        # We've got a task going for this alert.
        return False

    # We don't have a task for this yet. Set an expiration for the new key,
    # and make a new async task. The expiration gives us a safety so that the
    # semaphor *will* eventually go away even if our task or server crashes.
    safety_expiration_timeout = 10 * 60
    r.expire(key, safety_expiration_timeout)
    return True


# Ignore the result or else we'll use a lot of memory.
@app.task(ignore_result=True)
def send_docket_alert(d_pk, since):
    """Send an alert for a given docket

    :param d_pk: The docket PK that was modified
    :param since: If we run alerts, notify users about items *since* this time.
    :return: None
    """
    email_addresses = (
        User.objects.filter(docket_alerts__docket_id=d_pk,)
        .distinct()
        .values_list("email", flat=True)
    )
    if email_addresses:
        # We have an alert for this docket. Proceed.
        docket = Docket.objects.get(pk=d_pk)
        new_des = DocketEntry.objects.filter(
            date_created__gte=since, docket=docket
        )

        if new_des.count() > 0:
            # Notify every user that's subscribed to this alert.
            case_name = trunc(best_case_name(docket), 100, ellipsis="...")
            subject_template = loader.get_template("docket_alert_subject.txt")
            subject = subject_template.render(
                {
                    "docket": docket,
                    "count": new_des.count(),
                    "case_name": case_name,
                }
            ).strip()  # Remove newlines that editors can insist on adding.
            email_context = {"new_des": new_des, "docket": docket}
            txt_template = loader.get_template("docket_alert_email.txt")
            html_template = loader.get_template("docket_alert_email.html")
            messages = []
            for email_address in email_addresses:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=txt_template.render(email_context),
                    from_email=settings.DEFAULT_ALERTS_EMAIL,
                    to=[email_address],
                    headers={"X-Entity-Ref-ID": "docket.alert:%s" % d_pk},
                )
                html = html_template.render(email_context)
                msg.attach_alternative(html, "text/html")
                messages.append(msg)

            # Add a bcc to the first message in the list so that we get a copy.
            messages[0].bcc = ["docket-alert-testing@free.law"]
            connection = get_connection()
            connection.send_messages(messages)
            tally_stat("alerts.docket.alerts.sent", inc=len(email_addresses))

        DocketAlert.objects.filter(docket=docket).update(date_last_hit=now())

    # Work completed, clear the semaphore
    r = make_redis_interface("ALERTS")
    r.delete(make_alert_key(d_pk))


@app.task(ignore_result=True)
def send_docket_alerts(data):
    """Send many docket alerts at one time without making numerous calls
    to the send_docket_alert function.

    :param data: A dict with up to two keys:

      d_pks_to_alert: A list of tuples. Each tuple contains the docket ID, and
                      a time. The time indicates that alerts should be sent for
                      items *after* that point.
        rds_for_solr: A list of RECAPDocument ids that need to be sent to Solr
                      to be made searchable.
    :returns: Simply passes through the rds_for_solr list, in case it is
    consumed by the next task. If rds_for_solr is not provided, returns an
    empty list.
    """
    for args in data["d_pks_to_alert"]:
        send_docket_alert(*args)

    return data.get("rds_for_solr", [])


@app.task(ind=True, max_retries=2, interval_start=5, interval_step=5)
def crawl_pacer_mobile_page(self, d_pk):
    cookies = get_or_cache_pacer_cookies(
        "pacer_scraper",
        username=settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    s = PacerSession(
        cookies=cookies,
        username=settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    d = Docket.objects.get(pk=d_pk)
    report = MobileQuery(map_cl_to_pacer_id(d.court_id), s)
    try:
        report.query(d.pacer_case_id)
    except (requests.Timeout, requests.RequestException) as exc:
        logger.warning(
            "Timeout or unknown RequestException on iquery crawl. "
            "Trying again if retries not exceeded."
        )
        if self.request.retries == self.max_retries:
            return
        raise self.retry(exc=exc)

    entry_count = report.metadata["entry_count"]
    mobile_page, created = PACERMobilePageData.objects.get_or_create(docket=d)
    if created:
        # No alerts on first crawl because no baseline to compare to; punt
        pass
    elif (
        entry_count
        > mobile_page.count_last_mobile_crawl
        + mobile_page.count_last_rss_crawl
    ):
        # Send the alert
        newly_enqueued = enqueue_docket_alert(d.pk)
        if newly_enqueued:
            # TODO: Write this function
            send_mobile_page_alert(d.pk)

    mobile_page.count_last_mobile_crawl = entry_count
    mobile_page.date_last_mobile_crawl = now()
    mobile_page.count_last_rss_crawl = 0
    mobile_page.save()
