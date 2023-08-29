from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple, Union, cast

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives, get_connection, send_mail
from django.db import transaction
from django.template import loader
from django.utils.timezone import now
from elasticsearch.exceptions import RequestError, TransportError
from elasticsearch_dsl.response import Hit

from cl.alerts.models import Alert, DocketAlert, ScheduledAlertHit
from cl.alerts.utils import percolate_document, send_alert_email
from cl.api.models import WebhookEventType
from cl.api.tasks import (
    send_docket_alert_webhook_events,
    send_es_search_alert_webhook,
)
from cl.celery_init import app
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.models import Note, UserTag
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import merge_highlights_into_result
from cl.lib.redis_utils import create_redis_semaphore, delete_redis_semaphore
from cl.lib.string_utils import trunc
from cl.recap.constants import COURT_TIMEZONES
from cl.search.constants import ALERTS_HL_TAG
from cl.search.models import Docket, DocketEntry
from cl.stats.utils import tally_stat
from cl.users.models import UserProfile


def make_alert_key(d_pk: int) -> str:
    return f"docket.alert.enqueued:{d_pk}"


def enqueue_docket_alert(d_pk: int) -> bool:
    """Small wrapper to create keys for docket alerts"""
    key = make_alert_key(d_pk)
    return create_redis_semaphore("ALERTS", key, ttl=60 * 10)


@dataclass
class DocketAlertRecipient:
    email_address: str
    secret_key: str
    auto_subscribe: bool
    first_email: bool
    user_pk: int
    username: str


def get_docket_alert_recipients(
    d_pk: int,
    recap_email_recipients: list[str],
    recap_email_user_only: bool = False,
) -> tuple[list[DocketAlertRecipient], list[int], list[str]]:
    """Get the notification's recipients for a docket alert.

    :param d_pk: Docket primary key
    :param recap_email_recipients: List of @recap.email addresses to send the
    notification to.
    :param recap_email_user_only: True if we need to get recipients only for
    a recap.email user to send the alert independently and avoid sending
    duplicate docket alerts for current subscribers.
    :return: A list of DocketAlertRecipients objects, a list of User pks as
    webhook recipients and a list of @recap.email addresses that don't belong
    to any user if any.
    """

    # List of DocketAlertRecipient objects to send docket alerts
    da_recipients_list = []
    # List of DocketAlertRecipient objects to send webhooks
    webhook_recipients_list = []
    # List of @recap.email addresses that don't belong to any user
    recap_email_user_does_not_exist_list = []

    # First, get current docket alert recipients to avoid duplicate alerts
    if not recap_email_user_only:
        docket_alerts_current_subscribers = DocketAlert.objects.select_related(
            "user"
        ).filter(docket_id=d_pk, alert_type=DocketAlert.SUBSCRIPTION)
        for da in docket_alerts_current_subscribers:
            dar = DocketAlertRecipient(
                email_address=da.user.email,
                secret_key=da.secret_key,
                auto_subscribe=False,
                first_email=False,
                user_pk=da.user.pk,
                username=da.user.username,
            )
            da_recipients_list.append(dar)
            webhook_recipients_list.append(da.user.pk)

    # Get recap email recipients and create new docket alerts objects
    for email_address in recap_email_recipients:
        try:
            user_profile = UserProfile.objects.select_related("user").get(
                recap_email=email_address
            )
        except UserProfile.DoesNotExist:
            recap_email_user_does_not_exist_list.append(email_address)
            continue

        alert_type = (
            DocketAlert.SUBSCRIPTION
            if user_profile.auto_subscribe
            else DocketAlert.UNSUBSCRIPTION
        )
        with transaction.atomic():
            # select_for_update to avoid a race condition when creating the
            # docket alert.
            (
                docket_alert,
                created,
            ) = DocketAlert.objects.select_for_update().get_or_create(
                docket_id=d_pk,
                user=user_profile.user,
                defaults={"alert_type": alert_type},
            )
            if not created:
                # If a docket alert exists for this @recap.email user-case,
                # avoid sending the first email or webhook event
                continue

            dar = DocketAlertRecipient(
                email_address=user_profile.user.email,
                secret_key=docket_alert.secret_key,
                auto_subscribe=user_profile.auto_subscribe,
                first_email=True,
                user_pk=user_profile.user.pk,
                username=user_profile.user.username,
            )
            da_recipients_list.append(dar)
            # For first-time user-case notifications we only send webhook
            # events if the user has the auto-subscribe option enabled.
            if user_profile.auto_subscribe:
                webhook_recipients_list.append(user_profile.user.pk)

    return (
        da_recipients_list,
        webhook_recipients_list,
        recap_email_user_does_not_exist_list,
    )


def get_docket_notes_and_tags_by_user(
    d_pk: int, user_pk: int
) -> tuple[str | None, list[UserTag]]:
    """Get user notes and tags for a docket.

    :param d_pk: Docket primary key
    :param user_pk: The User primary key
    :return: A two tuple of docket notes or None if not available, a list of
    tags assigned to the docket.
    """

    notes = None
    note = (
        Note.objects.filter(docket_id=d_pk, user_id=user_pk)
        .only("notes")
        .first()
    )
    if note and note.notes:
        notes = note.notes

    user_tags = list(UserTag.objects.filter(user_id=user_pk, dockets__id=d_pk))
    return notes, user_tags


def make_alert_messages(
    d: Docket,
    new_des: list[DocketEntry],
    da_recipients: list[DocketAlertRecipient],
) -> list[EmailMultiAlternatives]:
    """Make docket alert messages that can be sent to users

    :param d: The docket to work on
    :param new_des: The new docket entries
    :param da_recipients: A list of DocketAlertRecipients objects
    :return: A list of email messages to send
    """

    case_name = trunc(best_case_name(d), 100, ellipsis="...")
    txt_template = loader.get_template("docket_alert_email.txt")
    html_template = loader.get_template("docket_alert_email.html")
    subject_template = loader.get_template("docket_alert_subject.txt")
    de_count = len(new_des)
    subject_context = {
        "docket": d,
        "count": de_count,
        "case_name": case_name,
    }
    email_context = {
        "new_des": new_des,
        "count": de_count,
        "docket": d,
        "docket_alert_secret_key": None,
        "timezone": COURT_TIMEZONES.get(d.court_id, "US/Eastern"),
    }
    messages = []
    for recipient in da_recipients:
        notes, tags = get_docket_notes_and_tags_by_user(
            d.pk, recipient.user_pk
        )
        email_context["notes"] = notes
        email_context["tags"] = tags
        email_context["username"] = recipient.username
        email_context["docket_alert_secret_key"] = recipient.secret_key
        email_context["first_email"] = recipient.first_email
        subject_context["first_email"] = recipient.first_email
        email_context["auto_subscribe"] = recipient.auto_subscribe
        subject_context["auto_subscribe"] = recipient.auto_subscribe
        subject = subject_template.render(subject_context).strip()  # Remove
        # newlines that editors can insist on adding.
        msg = EmailMultiAlternatives(
            subject=subject,
            body=txt_template.render(email_context),
            from_email=settings.DEFAULT_ALERTS_EMAIL,
            to=[recipient.email_address],
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
    recap_email_recipients: list[str] | None = None,
    des_pks: list[int] | None = None,
) -> None:
    """Send an alert and webhook for a given docket

    There are two methods to send docket alerts. The first one is based on the
    time *since* new docket entries for a docket were created. This method is
    the most common to send docket alerts since we send alerts for new docket
    entries.

    There's an exception when sending docket alerts triggered by recap.email.
    If we receive a recap.email notification two or more times for the same
    docket entry we must avoid sending duplicated docket alerts to subscribed
    users and send the alert independently for the recap.email user from whom
    we received additional notifications for the same docket entry.

    This works as follows for recap.email users:

    - Bob: Subscribed to the case, via the "Subscribe" button on the website.
    - Atty1: Uses recap.email, and has atty1@recap.email set up in her PACER
      account for the case.
    - Atty2: Just started using recap.email and just added atty2@recap.email to
     their PACER account for the case.

    An email comes in for atty1@recap.email. We:
    - Send emails to atty1@recap.email and to Bob.
    - atty1@recap.email has the auto-subscribe option enabled so is now
      subscribed to the case.

    Another email for the same docket entry comes in for atty2@recap.email. We:
    - Already sent out notifications for everybody else.
      Don't want to send additional ones.
    - Just sent a notification to atty2.
    - atty2@recap.email has the auto-subscribe option enabled so is now
      subscribed to the case.

    Later, another docket entry is filed and we get two more emails.
    The first is to atty2@recap.email (but the order doesn't matter). We:
    - Send emails to all subscribers, which includes atty2, Bob, and atty1.

     The second email comes in to atty1@recap.email. We:
     -Do nothing.

    :param d_pk: The docket PK that was modified
    :param since: If we run alerts, notify users about items *since* this time.
    :param recap_email_recipients: The recap.email addresses if needed to send
    the first case-user notification email.
    :param des_pks: A list of docket entries pks used if we need to send an
    alert again for a recap.email user independently
    :return: None
    """

    if recap_email_recipients is None:
        recap_email_recipients = []
    recap_email_user_only = False
    if des_pks:
        recap_email_user_only = True

    (
        da_recipients,
        webhook_recipients,
        re_user_does_not_exist_list,
    ) = get_docket_alert_recipients(
        d_pk, recap_email_recipients, recap_email_user_only
    )

    if re_user_does_not_exist_list:
        send_recap_email_user_not_found(re_user_does_not_exist_list)

    if not da_recipients and not recap_email_user_only:
        # Nobody subscribed to the docket.
        delete_redis_semaphore("ALERTS", make_alert_key(d_pk))
        return

    d = Docket.objects.get(pk=d_pk)
    if des_pks is not None:
        new_des = DocketEntry.objects.filter(pk__in=des_pks)
    else:
        new_des = list(
            DocketEntry.objects.filter(date_created__gte=since, docket=d)
        )
        des_pks = [de.pk for de in new_des]
    if len(new_des) == 0 and not recap_email_user_only:
        # No new docket entries.
        delete_redis_semaphore("ALERTS", make_alert_key(d_pk))
        return

    messages = make_alert_messages(d, new_des, da_recipients)
    connection = get_connection()
    connection.send_messages(messages)

    # Work completed. Tally, log, and clean up
    tally_stat("alerts.docket.alerts.sent", inc=len(messages))
    DocketAlert.objects.filter(docket=d).update(date_last_hit=now())

    # Send docket entries to webhook
    send_docket_alert_webhook_events.delay(des_pks, webhook_recipients)
    if not recap_email_user_only:
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


@app.task(ignore_result=True)
def send_search_alert_and_webhooks(
    user_id: int, hits: list[tuple[Alert, str, list[dict[str, Any]], int]]
) -> None:
    """Send alert emails and webhooks for a user.

    One email is sent per User and one webhook event is sent for every Alert
    per User.

    :param user_id: The user to whom the alerts should be sent.
    :param hits: A list of tuples containing the Alert, search type,
    documents, and number of documents.
    :return: None
    """

    alert_user: UserProfile.user = User.objects.get(pk=user_id)
    if len(hits) > 0:
        send_alert_email(alert_user.email, hits)

    for alert, search_type, documents, num_docs in hits:
        user_webhooks = alert_user.webhooks.filter(
            event_type=WebhookEventType.SEARCH_ALERT, enabled=True
        )
        for user_webhook in user_webhooks:
            send_es_search_alert_webhook.delay(
                documents,
                user_webhook,
                alert,
            )


@app.task(ignore_result=True)
def process_percolator_response(
    response: tuple[list[Hit], dict[str, Any]]
) -> None:
    """Process the response from the percolator and handle alerts triggered by
     the percolator query.

    :param response: A two tuple, a list of Alerts triggered and the document
    data that triggered the alert.
    :return: None
    """

    if not response:
        return None
    alerts_triggered, document_content = response
    for hit in alerts_triggered:
        alert_triggered = (
            Alert.objects.filter(pk=hit.meta.id)
            .select_related(
                "user",
            )
            .first()
        )
        if not alert_triggered:
            continue

        # Send RT Alerts
        if alert_triggered.rate == Alert.REAL_TIME:
            alert_user: UserProfile.user = alert_triggered.user
            not_donated_enough = (
                alert_user.profile.total_donated_last_year
                < settings.MIN_DONATION["rt_alerts"]
            )
            if not_donated_enough:
                logger.info(
                    "User: %s has not donated enough for their "
                    "RT alerts to be sent.\n" % alert_user
                )
                continue

            # Set highlight if available in response.
            if hasattr(hit.meta, "highlight"):
                merge_highlights_into_result(
                    hit.meta.highlight.to_dict(),
                    document_content,
                    ALERTS_HL_TAG,
                )
            hits = []
            search_type = alert_triggered.alert_type
            hits.append(
                (
                    alert_triggered,
                    search_type,
                    [document_content],
                    1,
                )
            )
            alert_triggered.date_last_hit = now()
            alert_triggered.save()

            # Send Alerts and Webhooks
            send_search_alert_and_webhooks.delay(alert_user.pk, hits)

            tally_stat(f"alerts.sent.{Alert.REAL_TIME}", inc=1)
            logger.info(f"Sent {1} {Alert.REAL_TIME} email alerts.")

        else:
            # Schedule DAILY, WEEKLY and MONTHLY Alerts
            highlights = {}
            if hasattr(hit.meta, "highlight"):
                highlights = hit.meta["highlight"].to_dict()
            ScheduledAlertHit.objects.create(
                user=alert_triggered.user,
                rate=alert_triggered.rate,
                alert=alert_triggered,
                document_content=document_content,
                highlighted_fields=highlights,  # Merge highlights in content.
            )


@app.task(
    bind=True,
    autoretry_for=(TransportError, ConnectionError, RequestError),
    max_retries=3,
    interval_start=5,
)
def send_or_schedule_alerts(
    self, response: tuple[str, dict[str, Any]], document_index: str
) -> tuple[list[Hit], dict[str, Any]] | None:
    """Send real-time alerts based on the Elasticsearch search response.

    Or schedule other rates alerts to send them later.

    Iterates through each hit in the search response, checks if the alert rate
    is real-time, and if the user has donated enough. If so it sends an email
    alert and triggers webhooks.
    The process begins with an initial percolator query and continues to fetch
    additional results in chunks determined by settings.PERCOLATOR_PAGE_SIZE,
    until all results are retrieved or no more results are available.

    :param self: The task
    :param response: A two tuple, the document ID to be percolated in
    ES index and the document data that triggered the alert.
    :param document_index: The ES document index where the document lives.
    :return: A two tuple, a list of Alerts triggered and the document data that
    triggered the alert.
    """

    if not response:
        self.request.chain = None
        return None

    document_id, document_content = response
    # Perform an initial percolator query and process its response.
    alerts_triggered = []
    percolator_response = percolate_document(document_id, document_index)
    if not percolator_response:
        self.request.chain = None
        return None

    alerts_triggered.extend(percolator_response.hits)

    # Check if the query contains more documents than PERCOLATOR_PAGE_SIZE.
    # If so, return additional results until there are not more.
    batch_size = settings.PERCOLATOR_PAGE_SIZE
    total_hits = percolator_response.hits.total.value
    results_returned = len(percolator_response.hits.hits)
    if total_hits > batch_size:
        documents_retrieved = results_returned
        search_after = percolator_response.hits[-1].meta.sort
        while True:
            percolator_response = percolate_document(
                document_id, document_index, search_after=search_after
            )
            if not percolator_response:
                break

            alerts_triggered.extend(percolator_response.hits)
            results_returned = len(percolator_response.hits.hits)
            documents_retrieved += results_returned
            # Check if all results have been retrieved. If so break the loop
            # Otherwise, increase search_after.
            if documents_retrieved >= total_hits or results_returned == 0:
                break
            else:
                search_after = percolator_response.hits[-1].meta.sort

    return alerts_triggered, document_content
