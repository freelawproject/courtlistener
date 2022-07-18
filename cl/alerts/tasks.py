from datetime import datetime
from typing import Dict, List, Tuple, Union, cast

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection, send_mail
from django.db.models import QuerySet
from django.template import loader
from django.utils.timezone import now

from cl.alerts.models import DocketAlert
from cl.api.models import Webhook, WebhookEvent, WebhookEventType
from cl.celery_init import app
from cl.corpus_importer.api_serializers import DocketEntrySerializer
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


def get_docket_alert_recipients(
    d_pk: int,
    recap_email_recipients: list[str] = [],
) -> tuple[
    list[tuple[str, str]],
    list[tuple[str, str]],
    list[tuple[str, str]],
    list[str],
]:
    """Get the notification's recipients for a docket alert.
    :param d_pk: Docket primary key
    :param recap_email_recipients: List of @recap.email addresses to send the
    notification to.
    :return: A Tuple of lists of tuples (email_address, secret_key) and a list
    of @recap.email addresses that don't belong to any user if any.
    """

    # Lists of tuples (email_address, docket_alert.secret_key)
    docket_alert_recipients_list = []
    recap_email_first_time_auto_subscribe_list = []
    recap_email_first_time_no_auto_subscribe_list = []
    # List of @recap.email addresses that don't belong to any user
    recap_email_user_does_not_exist_list = []

    # First, get current docket alert recipients to avoid duplicate alerts
    docket_alerts_current_subscribers = DocketAlert.objects.filter(
        docket_id=d_pk, alert_type=DocketAlert.SUBSCRIPTION
    )
    for da in docket_alerts_current_subscribers:
        recipient_tuple = (da.user.email, da.secret_key)
        docket_alert_recipients_list.append(recipient_tuple)

    # Get recap email recipients and create new docket alerts objects
    for email_address in recap_email_recipients:
        try:
            user_profile = UserProfile.objects.get(recap_email=email_address)
        except UserProfile.DoesNotExist:
            recap_email_user_does_not_exist_list.append(email_address)
            continue
        email_address = user_profile.user.email
        docket_alert_exist = DocketAlert.objects.filter(
            docket_id=d_pk, user=user_profile.user
        ).exists()
        if docket_alert_exist:
            # If a docket alert exists for this @recap.email user, avoid
            # sending the first email
            continue
        if user_profile.auto_subscribe:
            # First time recipient, auto_subscribe True
            docket_alert = DocketAlert.objects.create(
                docket_id=d_pk, user=user_profile.user
            )
            recipient_tuple = (email_address, docket_alert.secret_key)
            recap_email_first_time_auto_subscribe_list.append(recipient_tuple)
        else:
            # First time recipient, auto_subscribe False
            docket_alert = DocketAlert.objects.create(
                docket_id=d_pk,
                user=user_profile.user,
                alert_type=DocketAlert.UNSUBSCRIPTION,
            )
            recipient_tuple = (email_address, docket_alert.secret_key)
            recap_email_first_time_no_auto_subscribe_list.append(
                recipient_tuple
            )
    return (
        docket_alert_recipients_list,
        recap_email_first_time_auto_subscribe_list,
        recap_email_first_time_no_auto_subscribe_list,
        recap_email_user_does_not_exist_list,
    )


def make_alert_messages(
    d: Docket,
    new_des: QuerySet,
    recipients: list[tuple[str, str]],
    first_email: bool,
    auto_subscribe: bool,
) -> list[EmailMultiAlternatives]:
    """Make docket alert messages that can be sent to users

    :param d: The docket to work on
    :param new_des: The new docket entries
    :param recipients: A list of user email and secret_key tuples to send to
    :param first_email: Whether this is the first email for this docket
    :param auto_subscribe: Whether this is the first time the user has received
    a notification for this docket
    :return: A list of email messages to send
    """

    case_name = trunc(best_case_name(d), 100, ellipsis="...")
    txt_template = loader.get_template("docket_alert_email.txt")
    html_template = loader.get_template("docket_alert_email.html")
    subject_template = loader.get_template("docket_alert_subject.txt")
    subject_context = {
        "docket": d,
        "count": new_des.count(),
        "case_name": case_name,
        "first_email": first_email,
        "auto_subscribe": auto_subscribe,
    }
    email_context = {
        "new_des": new_des,
        "docket": d,
        "docket_alert_secret_key": None,
        "first_email": first_email,
        "auto_subscribe": auto_subscribe,
    }

    messages = []
    for recipient_tuple in recipients:
        email_context["docket_alert_secret_key"] = recipient_tuple[1]
        subject = subject_template.render(subject_context).strip()  # Remove
        # newlines that editors can insist on adding.
        msg = EmailMultiAlternatives(
            subject=subject,
            body=txt_template.render(email_context),
            from_email=settings.DEFAULT_ALERTS_EMAIL,
            to=[recipient_tuple[0]],
            headers={f"X-Entity-Ref-ID": f"docket.alert:{d.pk}"},
        )
        html = html_template.render(email_context)
        msg.attach_alternative(html, "text/html")
        messages.append(msg)
    return messages


# Ignore the result or else we'll use a lot of memory.
@app.task(ignore_result=True)
def send_alert_and_webhook(
    d_pk: int,
    since: datetime,
    recap_email_recipients: list[str] = [],
) -> None:
    """Send an alert and webhook for a given docket

    :param d_pk: The docket PK that was modified
    :param since: If we run alerts, notify users about items *since* this time.
    :param recap_email_recipients: The recap.email addresses if needed to send
    the first case-user notification email.
    :return: None
    """

    (
        docket_alert_recipients,
        recap_email_auto_subscribe_recipients,
        recap_email_no_auto_recipients,
        recap_email_user_does_not_exist_list,
    ) = get_docket_alert_recipients(d_pk, recap_email_recipients)

    if recap_email_user_does_not_exist_list:
        send_recap_email_user_not_found(recap_email_user_does_not_exist_list)

    if (
        not docket_alert_recipients
        and not recap_email_auto_subscribe_recipients
        and not recap_email_no_auto_recipients
    ):
        # Nobody subscribed to the docket.
        delete_redis_semaphore("ALERTS", make_alert_key(d_pk))
        return

    d = Docket.objects.get(pk=d_pk)
    new_des = DocketEntry.objects.filter(date_created__gte=since, docket=d)
    if new_des.count() == 0:
        # No new docket entries.
        delete_redis_semaphore("ALERTS", make_alert_key(d_pk))
        return

    docket_alert_messages = make_alert_messages(
        d,
        new_des,
        docket_alert_recipients,
        first_email=False,
        auto_subscribe=False,
    )
    re_first_time_auto_subscribe_messages = make_alert_messages(
        d,
        new_des,
        recap_email_auto_subscribe_recipients,
        first_email=True,
        auto_subscribe=True,
    )
    re_first_time_no_auto_subscribe_messages = make_alert_messages(
        d,
        new_des,
        recap_email_no_auto_recipients,
        first_email=True,
        auto_subscribe=False,
    )

    messages = (
        docket_alert_messages
        + re_first_time_auto_subscribe_messages
        + re_first_time_no_auto_subscribe_messages
    )
    connection = get_connection()
    connection.send_messages(messages)

    # Work completed. Tally, log, and clean up
    tally_stat("alerts.docket.alerts.sent", inc=len(messages))
    DocketAlert.objects.filter(docket=d).update(date_last_hit=now())

    # Webhooks recipients are handled separately, send it to current docket
    # alerts recipients + first time recap.email recipients with auto_subscribe
    # set to true.
    webhook_recipients = (
        docket_alert_recipients + recap_email_auto_subscribe_recipients
    )
    # Send the docket to webhook
    webhook_email_recipients = [email[0] for email in webhook_recipients]
    send_docket_to_webhook.delay(d_pk, since, webhook_email_recipients)
    delete_redis_semaphore("ALERTS", make_alert_key(d_pk))


@app.task(ignore_result=True)
def send_alerts_and_webhooks(
    data: Dict[str, Union[List[Tuple], List[int]]]
) -> List[int]:
    """Send many docket alerts at one time without making numerous calls
    to the send_alert_and_webhook function.

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
        send_alert_and_webhook(*args)

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


@app.task()
def send_docket_to_webhook(
    d_pk: int,
    since: datetime,
    webhook_recipients: list[str],
) -> None:
    """POSTS the DocketAlert to the recipients webhook(s)

    :param d_pk: The Docket primary key
    :param since: Start time for querying the docket entries
    :webhook_recipients: The list of email recipients to send the webhook to
    :return: None
    """

    docket_entries = DocketEntry.objects.filter(
        date_created__gte=since, docket_id=d_pk
    )
    if docket_entries.count() == 0:
        # No new docket entries.
        return

    webhooks = Webhook.objects.filter(
        event_type=WebhookEventType.DOCKET_ALERT,
        user__email__in=webhook_recipients,
        enabled=True,
    )

    serialized_docket_entries = []
    for de in docket_entries:
        serialized_docket_entries.append(DocketEntrySerializer(de).data)

    for webhook in webhooks:
        post_content = {
            "webhook": {
                "event_type": webhook.event_type,
                "version": webhook.version,
                "date_created": webhook.date_created.isoformat(),
            },
            "results": serialized_docket_entries,
        }
        response = requests.post(webhook.url, json=post_content, timeout=2)
        WebhookEvent.objects.create(
            webhook=webhook,
            status_code=response.status_code,
            content=post_content,
            response=response.text,
        )

        if not response.ok:
            webhook.failure_count = webhook.failure_count + 1
            webhook.save()


def send_recap_email_user_not_found(recap_email_recipients: list[str]) -> None:
    """Send a notification to the admins if a user does not exist for one or
     more a recap email recipients.

    :param recap_email_recipients: The list of @recap.email that doesn't belong
    to any user
    :return: None
    """

    template = loader.get_template("recap_email_user_not_found.txt")
    send_mail(
        subject=f"@recap.email user not found",
        message=template.render(
            {"recap_email_recipients": recap_email_recipients}
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[a[1] for a in settings.MANAGERS],
    )
