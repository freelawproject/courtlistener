import datetime
from collections import defaultdict
from typing import DefaultDict, Any

import waffle
from asgiref.sync import async_to_sync

from cl.alerts.models import (
    SCHEDULED_ALERT_HIT_STATUS,
    Alert,
    ScheduledAlertHit,
)
from cl.alerts.tasks import send_search_alert_emails
from cl.alerts.utils import InvalidDateError, override_alert_query
from cl.lib.command_utils import VerboseCommand, logger
from cl.stats.utils import tally_stat

DAYS_TO_DELETE = 90


def json_date_parser(dct):
    for key, value in dct.items():
        if isinstance(value, str):
            try:
                dct[key] = datetime.datetime.fromisoformat(value)
            except ValueError:
                pass
    return dct


def get_cut_off_date(rate: str, d: datetime.date) -> datetime.date | None:
    """Given a rate of dly, wly or mly and a date, returns the date after for
    building a daterange filter.
    :param rate: The alert rate to send Alerts.
    :param d: The date alerts are run.
    :return: The cut-off date or None.
    """
    cut_off_date = None
    if rate == Alert.DAILY:
        cut_off_date = d
    elif rate == Alert.WEEKLY:
        cut_off_date = d - datetime.timedelta(days=7)
    elif rate == Alert.MONTHLY:
        # Get the first of the month of the previous month regardless of the
        # current date
        early_last_month = d - datetime.timedelta(days=28)
        cut_off_date = datetime.datetime(
            early_last_month.year, early_last_month.month, 1
        ).date()
    return cut_off_date


def merge_documents(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple RECAPDocuments with the same Docket.
    :param documents: A list of document hits.
    :return: A document dictionary where documents has been merged.
    """

    main_document = documents[0].copy()
    child_docs = []
    for doc in documents:
        if "child_docs" in doc:
            child_docs.extend(doc["child_docs"])
    if child_docs:
        main_document["child_docs"] = child_docs
    return main_document


def query_and_send_alerts_by_rate(rate: str) -> None:
    """Query and send alerts per user.

    :param rate: The alert rate to send Alerts.
    :return: None
    """

    alerts_sent_count = 0
    now_time = datetime.datetime.now()
    # Get unique alert users with scheduled alert hits
    user_ids = ScheduledAlertHit.objects.filter(
        alert__rate=rate,
        hit_status=SCHEDULED_ALERT_HIT_STATUS.SCHEDULED
    ).values_list("user", flat=True).distinct()

    for user_id in user_ids:
        # Query ScheduledAlertHits for every user.
        scheduled_hits = ScheduledAlertHit.objects.filter(
            user_id=user_id,
            alert__rate=rate,
            hit_status=SCHEDULED_ALERT_HIT_STATUS.SCHEDULED
        ).select_related("user", "alert")

        # Group scheduled hits by Alert and docket_id
        grouped_hits: DefaultDict[
            Alert, DefaultDict[int, list[dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list))
        alerts_to_update = set()

        for hit in scheduled_hits:
            alert = hit.alert
            doc_content = json_date_parser(hit.document_content)
            docket_id = doc_content.get("docket_id")
            grouped_hits[alert][docket_id].append(doc_content)
            alerts_to_update.add(alert.pk)

        # Merge documents with the same docket_id
        merged_hits: DefaultDict[Alert, list[dict[str, Any]]] = defaultdict(
            list)
        for alert, document_groups in grouped_hits.items():
            for documents in document_groups.values():
                merged_hits[alert].append(merge_documents(documents))

        hits = []
        for alert, documents in merged_hits.items():
            search_type = alert.alert_type

            # Override order_by to show the latest items when clicking the
            # "View Full Results" button.
            cut_off_date = get_cut_off_date(rate, now_time.date())
            qd = override_alert_query(alert, cut_off_date)
            alert.query_run = qd.urlencode()  # type: ignore
            hits.append((alert, search_type, documents, len(documents)))

        if hits:
            send_search_alert_emails.delay([(user_id, hits)],
                                           scheduled_alert=True)
            alerts_sent_count += 1

        # Update Alert's date_last_hit in bulk for this user's alerts
        Alert.objects.filter(id__in=alerts_to_update).update(
            date_last_hit=now_time)

        # Update Scheduled alert hits status to "SENT" for this user
        scheduled_hits.update(hit_status=SCHEDULED_ALERT_HIT_STATUS.SENT)

    # Remove old Scheduled alert hits sent, daily.
    if rate == Alert.DAILY:
        scheduled_alerts_deleted = delete_old_scheduled_alerts()
        logger.info(
            f"Removed {scheduled_alerts_deleted} Scheduled Alert Hits."
        )

    async_to_sync(tally_stat)(f"alerts.sent.{rate}", inc=alerts_sent_count)
    logger.info(f"Sent {alerts_sent_count} {rate} email alerts.")


def send_scheduled_alerts(rate: str) -> None:
    if rate == Alert.MONTHLY:
        if datetime.date.today().day > 28:
            raise InvalidDateError(
                "Monthly alerts cannot be run on the 29th, 30th or 31st."
            )
    query_and_send_alerts_by_rate(rate)


def delete_old_scheduled_alerts() -> int:
    """Delete Scheduled alerts older than DAYS_TO_DELETE days.

    :return: The number of deleted scheduled hit alerts.
    """

    # Delete SENT ScheduledAlertHits after DAYS_TO_DELETE
    sent_older_than = datetime.datetime.now() - datetime.timedelta(
        days=DAYS_TO_DELETE
    )
    scheduled_sent_hits_to_delete = ScheduledAlertHit.objects.filter(
        date_created__lt=sent_older_than,
        hit_status=SCHEDULED_ALERT_HIT_STATUS.SENT,
    ).delete()

    # Delete SCHEDULED ScheduledAlertHits after 2 * DAYS_TO_DELETE
    unsent_older_than = datetime.datetime.now() - datetime.timedelta(
        days=2 * DAYS_TO_DELETE
    )
    scheduled_unsent_hits_to_delete = ScheduledAlertHit.objects.filter(
        date_created__lt=unsent_older_than,
        hit_status=SCHEDULED_ALERT_HIT_STATUS.SCHEDULED,
    ).delete()
    deleted_items = (
        scheduled_sent_hits_to_delete[0] + scheduled_unsent_hits_to_delete[0]
    )
    return deleted_items


class Command(VerboseCommand):
    help = "Send scheduled Search Alerts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rate",
            required=True,
            choices=Alert.ALL_FREQUENCIES,
            help=f"The rate to send emails ({', '.join(Alert.ALL_FREQUENCIES)})",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        if not waffle.switch_is_active("oa-es-alerts-active"):
            logger.info("ES OA Alerts are disabled.")
            return None
        send_scheduled_alerts(options["rate"])
