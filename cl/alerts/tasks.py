import copy
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from typing import Dict, List, Tuple, Union, cast
from urllib.parse import urlencode

from asgiref.sync import async_to_sync
from celery import Task
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.mail import EmailMultiAlternatives, get_connection, send_mail
from django.db import transaction
from django.template import loader
from django.urls import reverse
from django.utils.timezone import now
from elasticsearch.exceptions import ConnectionError

from cl.alerts.models import Alert, DocketAlert, ScheduledAlertHit
from cl.alerts.utils import (
    add_document_hit_to_alert_set,
    alert_hits_limit_reached,
    build_alert_email_subject,
    fetch_all_search_alerts_results,
    has_document_alert_hit_been_triggered,
    include_recap_document_hit,
    override_alert_query,
    percolate_document,
    percolate_es_document,
    prepare_percolator_content,
    scheduled_alert_hits_limit_reached,
    transform_percolator_child_document,
)
from cl.api.models import WebhookEventType
from cl.api.tasks import (
    send_docket_alert_webhook_events,
    send_search_alert_webhook_es,
)
from cl.celery_init import app
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.models import Note, UserTag
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import fetch_all_search_results
from cl.lib.redis_utils import (
    create_redis_semaphore,
    delete_redis_semaphore,
    get_redis_interface,
)
from cl.lib.string_utils import trunc
from cl.recap.constants import COURT_TIMEZONES
from cl.search.models import Docket, DocketEntry
from cl.search.types import (
    ESDocumentNameType,
    PercolatorResponseType,
    SaveDocumentResponseType,
    SaveESDocumentReturn,
    SearchAlertHitType,
    SendAlertsResponse,
)
from cl.stats.utils import tally_stat
from cl.users.models import UserProfile

es_document_module = import_module("cl.search.documents")


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
        unsubscribe_url = reverse(
            "one_click_docket_alert_unsubscribe", args=[recipient.secret_key]
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
            headers={
                "X-Entity-Ref-ID": f"docket.alert:{d.pk}",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                "List-Unsubscribe": f"<https://www.courtlistener.com{unsubscribe_url}>",
            },
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
    async_to_sync(tally_stat)("alerts.docket.alerts.sent", inc=len(messages))
    DocketAlert.objects.filter(docket=d).update(date_last_hit=now())

    # Send docket entries to webhook
    send_docket_alert_webhook_events.delay(des_pks, webhook_recipients)
    if not recap_email_user_only:
        delete_redis_semaphore("ALERTS", make_alert_key(d_pk))


@app.task(ignore_result=True)
def send_alerts_and_webhooks(data: list[tuple[int, datetime]]) -> List[int]:
    """Send many docket alerts at one time without making numerous calls
    to the send_alert_and_webhook function.

    :param data: A list of tuples. Each tuple contains the docket ID, and
        a time. The time indicates that alerts should be sent for
        items *after* that point.

    :returns: An empty list
    """
    for args in data:
        send_alert_and_webhook(*args)

    return []


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
        headers={"X-Entity-Ref-ID": f"docket.alert:{docket.pk}"},
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
        subject="@recap.email user not found",
        message=template.render(
            {"recap_email_recipients": recap_email_recipients}
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[a[1] for a in settings.MANAGERS],
    )


def send_webhook_alert_hits(
    alert_user: UserProfile.user, hits: list[SearchAlertHitType]
) -> None:
    """Send webhook alerts for search hits.

    :param alert_user: The user profile object associated with the webhooks.
    :param hits: A list of tuples, each containing information about an alert,
    its associated search type, documents found, and the number of documents.
    :return: None
    """

    for alert, search_type, documents, num_docs in hits:
        user_webhooks = alert_user.webhooks.filter(
            event_type=WebhookEventType.SEARCH_ALERT, enabled=True
        )
        for user_webhook in user_webhooks:
            send_search_alert_webhook_es.delay(
                documents,
                user_webhook.pk,
                alert.pk,
            )


@app.task(ignore_result=True)
def send_search_alert_emails(
    email_alerts_to_send: list[tuple[int, list[SearchAlertHitType]]],
    scheduled_alert: bool = False,
) -> None:
    """Send search alert emails for multiple users.

    :param email_alerts_to_send: A list of two tuples containing the user to
    whom the alerts should be sent. A list of tuples containing the Search
    Alert, (Alert, search type, documents, and number of documents)
    :param scheduled_alert: A boolean indicating weather this alert has been
    scheduled
    :return: None
    """

    messages = []
    txt_template = loader.get_template("alert_email_es.txt")
    html_template = loader.get_template("alert_email_es.html")

    for email_to_send in email_alerts_to_send:
        user_id, hits = email_to_send
        if not len(hits) > 0:
            continue

        subject = build_alert_email_subject(hits)
        alert_user: UserProfile.user = User.objects.get(pk=user_id)
        context = {
            "hits": hits,
            "hits_limit": settings.SCHEDULED_ALERT_HITS_LIMIT,
            "scheduled_alert": scheduled_alert,
        }
        headers = {}
        query_string = ""
        if len(hits) == 1:
            alert = hits[0][0]
            unsubscribe_path = reverse(
                "one_click_disable_alert", args=[alert.secret_key]
            )
            headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        else:
            params = {"keys": [hit[0].secret_key for hit in hits]}
            query_string = urlencode(params, doseq=True)
            unsubscribe_path = reverse("disable_alert_list")
        headers["List-Unsubscribe"] = (
            f"<https://www.courtlistener.com{unsubscribe_path}{'?' if query_string else ''}{query_string}>"
        )

        txt = txt_template.render(context)
        html = html_template.render(context)
        msg = EmailMultiAlternatives(
            subject,
            txt,
            settings.DEFAULT_ALERTS_EMAIL,
            [alert_user.email],
            headers=headers,
        )
        msg.attach_alternative(html, "text/html")
        messages.append(msg)

    connection = get_connection()
    connection.send_messages(messages)


# TODO: Remove after scheduled OA alerts have been processed.
@app.task(ignore_result=True)
def process_percolator_response(response: PercolatorResponseType) -> None:
    """Process the response from the percolator and handle alerts triggered by
     the percolator query.

    :param response: A two tuple, a list of Alerts triggered and the document
    data that triggered the alert.
    :return: None
    """

    if not response:
        return None

    scheduled_hits_to_create = []
    email_alerts_to_send = []
    rt_alerts_to_send = []
    alerts_triggered, document_content = response
    for hit in alerts_triggered:
        # Create a deep copy of the original 'document_content' to allow
        # independent highlighting for each alert triggered.
        document_content_copy = copy.deepcopy(document_content)

        alert_triggered = (
            Alert.objects.filter(pk=hit.meta.id).select_related("user").first()
        )
        if not alert_triggered:
            continue

        alert_user: UserProfile.user = alert_triggered.user
        # Set highlight if available in response.
        if hasattr(hit.meta, "highlight"):
            document_content_copy["meta"] = {}
            document_content_copy["meta"][
                "highlight"
            ] = hit.meta.highlight.to_dict()

        # Override order_by to show the latest items when clicking the
        # "View Full Results" button.
        qd = override_alert_query(alert_triggered)
        alert_triggered.query_run = qd.urlencode()  # type: ignore

        # Compose RT hit to send.
        hits = [
            (
                alert_triggered,
                alert_triggered.alert_type,
                [document_content_copy],
                1,
            )
        ]
        # Send real time Webhooks for all users regardless of alert rate and
        # user's donations.
        send_webhook_alert_hits(alert_user, hits)

        # Send RT Alerts
        if alert_triggered.rate == Alert.REAL_TIME:
            if not alert_user.profile.is_member:
                continue

            # Append alert RT email to be sent.
            email_alerts_to_send.append((alert_user.pk, hits))
            rt_alerts_to_send.append(alert_triggered.pk)

        else:
            # Schedule DAILY, WEEKLY and MONTHLY Alerts
            if alert_hits_limit_reached(
                alert_triggered.pk, alert_triggered.user.pk
            ):
                # Skip storing hits for this alert-user combination because
                # the SCHEDULED_ALERT_HITS_LIMIT has been reached.
                continue
            scheduled_hits_to_create.append(
                ScheduledAlertHit(
                    user=alert_triggered.user,
                    alert=alert_triggered,
                    document_content=document_content_copy,
                )
            )

    # Create scheduled DAILY, WEEKLY and MONTHLY Alerts in bulk.
    if scheduled_hits_to_create:
        ScheduledAlertHit.objects.bulk_create(scheduled_hits_to_create)
    # Sent all the related document RT emails.
    if email_alerts_to_send:
        send_search_alert_emails.delay(email_alerts_to_send)

    # Update RT Alerts date_last_hit, increase stats and log RT alerts sent.
    if rt_alerts_to_send:
        Alert.objects.filter(pk__in=rt_alerts_to_send).update(
            date_last_hit=now()
        )
        alerts_sent = len(rt_alerts_to_send)
        async_to_sync(tally_stat)(
            f"alerts.sent.{Alert.REAL_TIME}", inc=alerts_sent
        )
        logger.info(f"Sent {alerts_sent} {Alert.REAL_TIME} email alerts.")


@app.task(ignore_result=True)
def percolator_response_processing(response: SendAlertsResponse) -> None:
    """Process the response from the percolator and handle alerts triggered by
     the percolator query.

    :param response: A `SendAlertsResponse` object containing A list of hits
    for main, docket only and recap-only alerts, the document data that
    triggered the alerts and The related app label model.
    :return: None
    """
    if not response:
        return None

    scheduled_hits_to_create = []

    main_alerts_triggered = response.main_alerts_triggered
    rd_alerts_triggered = response.rd_alerts_triggered
    d_alerts_triggered = response.d_alerts_triggered
    document_content = response.document_content
    app_label_model = response.app_label_model
    app_label_str, model_str = app_label_model.split(".")
    instance_content_type = ContentType.objects.get(
        app_label=app_label_str, model=model_str.lower()
    )
    r = get_redis_interface("CACHE")
    recap_document_hits = [hit.id for hit in rd_alerts_triggered]
    docket_hits = [hit.id for hit in d_alerts_triggered]
    for hit in main_alerts_triggered:
        # Create a deep copy of the original 'document_content' to allow
        # independent highlighting for each alert triggered.

        document_content_copy = copy.deepcopy(document_content)
        alert_triggered = (
            Alert.objects.filter(pk=hit.meta.id).select_related("user").first()
        )
        if not alert_triggered:
            continue

        alert_user: UserProfile.user = alert_triggered.user
        # Set highlight if available in response.
        match app_label_model:
            case "search.RECAPDocument":
                # Filter out RECAPDocuments and set the document id to the
                # Redis RECAPDocument alert hits set.
                if not include_recap_document_hit(
                    alert_triggered.pk, recap_document_hits, docket_hits
                ) or has_document_alert_hit_been_triggered(
                    r, alert_triggered.pk, "r", document_content_copy["id"]
                ):
                    continue
                transform_percolator_child_document(
                    document_content_copy, hit.meta
                )
                add_document_hit_to_alert_set(
                    r, alert_triggered.pk, "r", document_content_copy["id"]
                )
                object_id = document_content_copy["docket_id"]
                child_document = True
            case "search.Docket":
                # Filter out Dockets and set the document id to the
                # Redis Docket alert hits set.
                if has_document_alert_hit_been_triggered(
                    r,
                    alert_triggered.pk,
                    "d",
                    document_content_copy["docket_id"],
                ):
                    continue
                add_document_hit_to_alert_set(
                    r,
                    alert_triggered.pk,
                    "d",
                    document_content_copy["docket_id"],
                )
                object_id = document_content_copy["docket_id"]
                child_document = False
            case "audio.Audio":
                object_id = document_content_copy["id"]
                child_document = False
            case _:
                raise NotImplementedError(
                    "Percolator response processing not supported for: %s",
                    app_label_model,
                )

        if hasattr(hit.meta, "highlight"):
            document_content_copy["meta"] = {}
            document_content_copy["meta"][
                "highlight"
            ] = hit.meta.highlight.to_dict()

        # Override order_by to show the latest items when clicking the
        # "View Full Results" button.
        qd = override_alert_query(alert_triggered)
        alert_triggered.query_run = qd.urlencode()  # type: ignore

        # Compose RT hit to send.
        hits = [
            (
                alert_triggered,
                alert_triggered.alert_type,
                [document_content_copy],
                1,
            )
        ]
        # Send real time Webhooks for all users regardless of alert rate and
        # user's donations.
        send_webhook_alert_hits(alert_user, hits)

        if (
            alert_triggered.rate == Alert.REAL_TIME
            and not alert_user.profile.is_member
        ):
            # Omit scheduling an RT alert if the user is not a member.
            continue
        # Schedule RT, DAILY, WEEKLY and MONTHLY Alerts
        if scheduled_alert_hits_limit_reached(
            alert_triggered.pk,
            alert_triggered.user.pk,
            instance_content_type,
            object_id,
            child_document,
        ):
            # Skip storing hits for this alert-user combination because
            # the SCHEDULED_ALERT_HITS_LIMIT has been reached.
            continue

        scheduled_hits_to_create.append(
            ScheduledAlertHit(
                user=alert_triggered.user,
                alert=alert_triggered,
                document_content=document_content_copy,
                content_type=instance_content_type,
                object_id=object_id,
            )
        )

    # Create scheduled RT, DAILY, WEEKLY and MONTHLY Alerts in bulk.
    if scheduled_hits_to_create:
        ScheduledAlertHit.objects.bulk_create(scheduled_hits_to_create)


# TODO: Remove after scheduled OA alerts have been processed.
@app.task(
    bind=True,
    autoretry_for=(ConnectionError,),
    max_retries=3,
    interval_start=5,
)
def send_or_schedule_alerts(
    self: Task, response: SaveDocumentResponseType, document_index: str
) -> PercolatorResponseType | None:
    """Send real-time alerts based on the Elasticsearch search response.

    Or schedule other rates alerts to send them later.

    Iterates through each hit in the search response, checks if the alert rate
    is real-time, and if the user has donated enough. If so it sends an email
    alert and triggers webhooks.
    The process begins with an initial percolator query and continues to fetch
    additional results in chunks determined by settings.ELASTICSEARCH_PAGINATION_BATCH_SIZE,
    until all results are retrieved or no more results are available.

    :param self: The celery task
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
    percolator_response = percolate_document(document_id, document_index)
    if not percolator_response:
        self.request.chain = None
        return None

    # Check if the query contains more documents than ELASTICSEARCH_PAGINATION_BATCH_SIZE.
    # If so, return additional results until there are not more.
    # Remember, percolator results are alerts, not documents, so what you're
    # paginating are user alerts that the document matched, not documents that
    # an alert matched. 🙃.
    alerts_triggered = fetch_all_search_results(
        percolate_document,
        percolator_response,
        document_id,
        document_index,
    )
    return alerts_triggered, document_content


@app.task(
    bind=True,
    autoretry_for=(ConnectionError,),
    max_retries=3,
    interval_start=5,
)
def send_or_schedule_search_alerts(
    self: Task, response: SaveESDocumentReturn | None
) -> SendAlertsResponse | None:
    """Send real-time alerts based on the Elasticsearch search response.

    Or schedule other rates alerts to send them later.

    Iterates through each hit in the search response, checks if the alert rate
    is real-time, and if the user has donated enough. If so it sends an email
    alert and triggers webhooks.
    The process begins with an initial percolator query and continues to fetch
    additional results in chunks determined by settings.ELASTICSEARCH_PAGINATION_BATCH_SIZE,
    until all results are retrieved or no more results are available.

    :param self: The celery task
    :param response: An optional `SaveESDocumentReturn` object containing the
    ID of the document saved in the ES index, the content of the document and
    the app label associated with the document.
    :return: A SendAlertsResponse dataclass containing the main alerts
    triggered, the recap documents alerts triggered, the docket alerts
    triggered, the document content that triggered the alert, and the related
    app label model or None.
    """

    if not response:
        self.request.chain = None
        return None

    if (
        not settings.PERCOLATOR_RECAP_SEARCH_ALERTS_ENABLED
        and response.app_label in ["search.RECAPDocument", "search.Docket"]
    ):
        # Disable percolation for RECAP search alerts until
        # PERCOLATOR_RECAP_SEARCH_ALERTS_ENABLED is set to True.
        self.request.chain = None
        return None

    app_label = response.app_label
    document_id = response.document_id
    document_content = response.document_content

    # Perform an initial percolator query and process its response.
    percolator_index, es_document_index, documents_to_percolate = (
        prepare_percolator_content(app_label, document_id)
    )
    if documents_to_percolate:
        # If documents_to_percolate is returned by prepare_percolator_content,
        # use the main document as the content to render in alerts.
        document_content, _, _ = documents_to_percolate
    percolator_responses = percolate_es_document(
        document_id,
        percolator_index,
        es_document_index,
        documents_to_percolate,
        app_label,
    )
    if not percolator_responses.main_response:
        self.request.chain = None
        return None

    # Check if the query contains more documents than ELASTICSEARCH_PAGINATION_BATCH_SIZE.
    # If so, return additional results until there are not more.
    # Remember, percolator results are alerts, not documents, so what you're
    # paginating are user alerts that the document matched, not documents that
    # an alert matched. 🙃.
    main_alerts_triggered, rd_alerts_triggered, d_alerts_triggered = (
        fetch_all_search_alerts_results(
            percolator_responses,
            document_id,
            percolator_index,
            es_document_index,
            documents_to_percolate,
            app_label,
        )
    )

    return SendAlertsResponse(
        main_alerts_triggered=main_alerts_triggered,
        rd_alerts_triggered=rd_alerts_triggered,
        d_alerts_triggered=d_alerts_triggered,
        document_content=document_content,
        app_label_model=app_label,
    )


# New task
@app.task(
    bind=True,
    autoretry_for=(ConnectionError,),
    max_retries=3,
    interval_start=5,
    ignore_result=True,
    queue=settings.CELERY_ETL_TASK_QUEUE,
)
def es_save_alert_document(
    self: Task,
    alert_id: int,
    es_document_name: ESDocumentNameType,
) -> None:
    """Helper method to prepare and index an Alert object into Elasticsearch.

    :param self: The celery task
    :param alert_id: The Alert instance ID to be indexed.
    :param es_document_name: The Elasticsearch document percolator name used
    for indexing.
    the Alert instance.
    :return: Bool, True if document was properly indexed, otherwise None.
    """

    es_document = getattr(es_document_module, es_document_name)
    document = es_document()
    alert = Alert.objects.get(pk=alert_id)
    alert_doc = {
        "timestamp": document.prepare_timestamp(alert),
        "rate": alert.rate,
        "date_created": alert.date_created,
        "id": alert.pk,
        "percolator_query": document.prepare_percolator_query(alert),
    }
    if not alert_doc["percolator_query"]:
        return None
    doc_indexed = es_document(meta={"id": alert.pk}, **alert_doc).save(
        skip_empty=True, refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH
    )
    if doc_indexed not in ["created", "updated"]:
        logger.warning(f"Error indexing Alert ID: {alert.pk}")
