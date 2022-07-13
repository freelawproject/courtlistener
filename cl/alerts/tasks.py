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
from cl.users.models import UserProfile


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
    recap_email_recipients: list[str] = [],
) -> List[EmailMultiAlternatives]:
    """Make docket alert messages that can be sent to users

    :param d: The docket to work on
    :param new_des: The new docket entries
    :param email_addresses: A list of user email addresses to send to
    :param recap_email_recipients: The recap_email addresses if needed to send
    the first case-user notification email.
    :return: A list of email messages to send
    """

    case_name = trunc(best_case_name(d), 100, ellipsis="...")
    messages = []
    txt_template = loader.get_template("docket_alert_email.txt")
    html_template = loader.get_template("docket_alert_email.html")
    subject_template = loader.get_template("docket_alert_subject.txt")
    subject_context = {
        "docket": d,
        "count": new_des.count(),
        "case_name": case_name,
        "first_email": False,
        "auto_subscribe": False,
    }
    email_context = {
        "new_des": new_des,
        "docket": d,
        "docket_alert": None,
        "first_email": False,
        "auto_subscribe": False,
    }

    # Concatenate current subscriptions addresses and recap_email_recipients
    email_addresses_list = list(email_addresses) + recap_email_recipients
    for email_address in email_addresses_list:
        if email_address in recap_email_recipients:
            # If the email_address is a @recap.email address we need to get the
            # actual user's email address and check if exists a DocketAlert
            # for this case-user. Ignore it if user doesn't exist in our DB.
            try:
                user_profile = UserProfile.objects.get(
                    recap_email=email_address
                )
            except UserProfile.DoesNotExist:
                # TODO send an email to admins informing the issue
                continue
            email_address = user_profile.user.email
            docket_alert_exist = DocketAlert.objects.filter(
                docket=d, user=user_profile.user
            ).exists()
            if docket_alert_exist:
                # If a docket alert exists for this @recap.email user, avoid
                # sending the first email
                continue
            first_email = True
            if user_profile.auto_subscribe:
                # First time recipient, auto_subscribe True
                auto_subscribe = True
                docket_alert = DocketAlert.objects.create(
                    docket=d, user=user_profile.user
                )
            else:
                # First time recipient, auto_subscribe False
                auto_subscribe = False
                docket_alert = DocketAlert.objects.create(
                    docket=d,
                    user=user_profile.user,
                    alert_type=DocketAlert.UNSUBSCRIPTION,
                )
        else:
            # Options for users that already have an active subscription for
            # this case
            first_email = auto_subscribe = False
            user = User.objects.filter(
                email=email_address, docket_alerts__docket=d
            ).first()
            docket_alert = DocketAlert.objects.get(docket=d, user=user)

        subject_context["first_email"] = first_email
        subject_context["auto_subscribe"] = auto_subscribe
        email_context["docket_alert"] = docket_alert
        email_context["first_email"] = first_email
        email_context["auto_subscribe"] = auto_subscribe
        subject = subject_template.render(subject_context).strip()  # Remove
        # newlines that editors can insist on adding.
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

    return messages


# Ignore the result or else we'll use a lot of memory.
@app.task(ignore_result=True)
def send_docket_alert(
    d_pk: int,
    since: datetime,
    recap_email_recipients: list[str] = [],
) -> None:
    """Send an alert for a given docket

    :param d_pk: The docket PK that was modified
    :param since: If we run alerts, notify users about items *since* this time.
    :param recap_email_recipients: The recap.email addresses if needed to send
    the first case-user notification email.
    :return: None
    """

    email_addresses = (
        User.objects.filter(
            docket_alerts__docket_id=d_pk,
            docket_alerts__alert_type=DocketAlert.SUBSCRIPTION,
        )
        .distinct()
        .values_list("email", flat=True)
    )

    if not email_addresses and not recap_email_recipients:
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
    messages = make_alert_messages(
        d, new_des, email_addresses, recap_email_recipients
    )
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


@app.task(ignore_result=True)
def send_unsubscription_confirmation(
    da_pk: int,
) -> None:
    """Send the unsubscription confirmation email after a user has unsubscribed
    from an email link.

    :param da_pk: The docket alert PK that was unsubscribed
    :return: None
    """

    docket_alert = DocketAlert.objects.get(pk=da_pk)
    docket = docket_alert.docket
    case_name = trunc(best_case_name(docket), 100, ellipsis="...")
    subject_template = loader.get_template(
        "docket_alert_unsubscription_subject.txt"
    )
    subject = subject_template.render(
        {
            "docket": docket,
            "case_name": case_name,
        }
    ).strip()
    txt_template = loader.get_template("docket_alert_unsubscription_email.txt")
    html_template = loader.get_template(
        "docket_alert_unsubscription_email.html"
    )
    email_context = {"docket": docket, "docket_alert": docket_alert}
    email_address = docket_alert.user.email
    msg = EmailMultiAlternatives(
        subject=subject,
        body=txt_template.render(email_context),
        from_email=settings.DEFAULT_ALERTS_EMAIL,
        to=[email_address],
        headers={f"X-Entity-Ref-ID": f"docket.alert:{docket.pk}"},
    )
    html = html_template.render(email_context)
    msg.attach_alternative(html, "text/html")
    msg.send()
