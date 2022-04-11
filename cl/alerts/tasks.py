from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union, cast

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db.models import QuerySet
from django.template import loader
from django.utils.timezone import now

from cl.alerts.models import DocketAlert
from cl.celery_init import app
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.redis_utils import create_redis_semaphore, delete_redis_semaphore
from cl.lib.string_utils import trunc
from cl.search.models import Docket, DocketEntry
from cl.stats.utils import tally_stat


def make_alert_key(d_pk: int) -> str:
    return f"docket.alert.enqueued:{d_pk}"


def enqueue_docket_alert(d_pk: int) -> bool:
    """Small wrapper to create keys for docket alerts"""
    key = make_alert_key(d_pk)
    return create_redis_semaphore("ALERTS", key, ttl=60 * 10)


def make_alert_messages(
    d: Docket,
    new_des: QuerySet,
    email_addresses: "ValuesQuerySet[User, Optional[str]]",  # type: ignore
) -> List[EmailMultiAlternatives]:
    """Make docket alert messages that can be sent to users

    :param d: The docket to work on
    :param new_des: The new docket entries
    :param email_addresses: A list of user email addresses to send to
    :return: A list of email messages to send
    """
    case_name = trunc(best_case_name(d), 100, ellipsis="...")
    subject_template = loader.get_template("docket_alert_subject.txt")
    subject = subject_template.render(
        {
            "docket": d,
            "count": new_des.count(),
            "case_name": case_name,
        }
    ).strip()  # Remove newlines that editors can insist on adding.
    email_context = {"new_des": new_des, "docket": d}
    txt_template = loader.get_template("docket_alert_email.txt")
    html_template = loader.get_template("docket_alert_email.html")
    messages = []
    for email_address in email_addresses:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=txt_template.render(email_context),
            from_email=settings.DEFAULT_ALERTS_EMAIL,
            to=[email_address],
            headers={f"X-Entity-Ref-ID": f"docket.alert:{d.pk}"},
        )
        html = html_template.render(email_context)
        msg.attach_alternative(html, "text/html")
        messages.append(msg)

    # Add a bcc to the first message in the list so that we get a copy.
    messages[0].bcc = ["docket-alert-testing@free.law"]
    return messages


# Ignore the result or else we'll use a lot of memory.
@app.task(ignore_result=True)
def send_docket_alert(d_pk: int, since: datetime) -> None:
    """Send an alert for a given docket

    :param d_pk: The docket PK that was modified
    :param since: If we run alerts, notify users about items *since* this time.
    :return: None
    """
    email_addresses = (
        User.objects.filter(docket_alerts__docket_id=d_pk)
        .distinct()
        .values_list("email", flat=True)
    )
    if not email_addresses:
        # Nobody subscribed to the docket.
        delete_redis_semaphore("ALERTS", make_alert_key(d_pk))
        return

    d = Docket.objects.get(pk=d_pk)
    new_des = DocketEntry.objects.filter(date_created__gte=since, docket=d)
    if new_des.count() == 0:
        # No new docket entries.
        delete_redis_semaphore("ALERTS", make_alert_key(d_pk))
        return

    # Notify every user that's subscribed to this alert.
    messages = make_alert_messages(d, new_des, email_addresses)
    connection = get_connection()
    connection.send_messages(messages)

    # Work completed. Tally, log, and clean up
    tally_stat("alerts.docket.alerts.sent", inc=len(email_addresses))
    DocketAlert.objects.filter(docket=d).update(date_last_hit=now())
    delete_redis_semaphore("ALERTS", make_alert_key(d_pk))


@app.task(ignore_result=True)
def send_docket_alerts(
    data: Dict[str, Union[List[Tuple], List[int]]]
) -> List[int]:
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

    return cast(List[int], data.get("rds_for_solr", []))
