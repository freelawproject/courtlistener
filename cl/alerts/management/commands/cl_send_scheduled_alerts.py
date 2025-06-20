from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import pytz
from asgiref.sync import async_to_sync
from django.conf import settings
from django.utils.timezone import get_default_timezone, make_aware

from cl.alerts.models import (
    SCHEDULED_ALERT_HIT_STATUS,
    Alert,
    ScheduledAlertHit,
)
from cl.alerts.tasks import send_search_alert_emails
from cl.alerts.utils import InvalidDateError, override_alert_query
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import SEARCH_TYPES
from cl.search.types import ESDictDocument
from cl.stats.utils import tally_stat

DAYS_TO_DELETE = 90


def json_date_parser(dct):
    for key, value in dct.items():
        if isinstance(value, str):
            try:
                dct[key] = datetime.fromisoformat(value)
            except ValueError:
                pass
    return dct


def get_cut_off_date(
    rate: str,
    d: datetime,
    sweep_index: bool = False,
    custom_date: bool = False,
) -> date | datetime | None:
    """Given a rate of dly, wly or mly and a date, returns the date after for
    building a daterange filter.
    :param rate: The alert rate to send Alerts.
    :param d: The datetime alerts are run.
    :param sweep_index: True if this is being used to trigger alerts using the
    sweep index.
    :param custom_date: If true, send alerts on a custom date.
    :return: The cut-off date or None.
    """

    if rate == Alert.REAL_TIME and not sweep_index:
        # Set cut_off_date to the datetime when RT alerts are sent minus
        # (REAL_TIME_ALERTS_SENDING_RATE + 1) seconds, considering that RT alerts
        # are sent every REAL_TIME_ALERTS_SENDING_RATE seconds.
        cut_off_date = d - timedelta(
            seconds=settings.REAL_TIME_ALERTS_SENDING_RATE + 1
        )
        # Convert cut_off_date to UTC. This is important since hit timestamps
        # are in UTC.
        local_tz = get_default_timezone()
        aware_local_dt = make_aware(cut_off_date, timezone=local_tz)
        return aware_local_dt.astimezone(pytz.UTC)
    elif rate == Alert.DAILY or (rate == Alert.REAL_TIME and sweep_index):
        # Since scheduled daily alerts run early the next day, set cut_off_date
        # to the previous day unless a custom date is used.
        # When sending alerts using the sweep index, real-time alert hits are
        # ingested throughout the day, so the timestamp filter should behave
        # the same as for daily alerts.
        return d.date() - timedelta(days=1) if not custom_date else d.date()
    elif rate == Alert.WEEKLY:
        # For weekly alerts, set cut_off_date to 7 days earlier.
        return d.date() - timedelta(days=7)
    elif rate == Alert.MONTHLY:
        # Get the first of the month of the previous month regardless of the
        # current date
        early_last_month = d.date() - timedelta(days=28)
        return datetime(
            early_last_month.year, early_last_month.month, 1
        ).date()

    return None


def merge_alert_child_documents(
    documents: list[ESDictDocument],
) -> ESDictDocument:
    """Merge multiple child hits within the same main document.
    :param documents: A list of document hits.
    :return: A document dictionary where documents has been merged.
    """

    main_document = documents[0].copy()
    child_docs: list[ESDictDocument] = []
    for doc in documents:
        if "child_docs" in doc:
            child_docs.extend(doc["child_docs"])
            if len(child_docs) >= settings.RECAP_CHILD_HITS_PER_RESULT:
                # Nested child limits reached. Set child_remaining True to show
                # the "Show the view additional hits button"
                main_document["child_remaining"] = True
                break

    if child_docs:
        main_document["child_docs"] = child_docs
    return main_document


def query_and_send_alerts_by_rate(rate: str) -> None:
    """Query and send alerts per user.

    :param rate: The alert rate to send Alerts.
    :return: None
    """

    alerts_sent_count = 0
    now_time = datetime.now()
    # Get unique alert users with scheduled alert hits
    user_ids = (
        ScheduledAlertHit.objects.filter(
            alert__rate=rate, hit_status=SCHEDULED_ALERT_HIT_STATUS.SCHEDULED
        )
        .values_list("user", flat=True)
        .distinct()
    )

    for user_id in user_ids:
        # Query ScheduledAlertHits for every user.
        scheduled_hits = ScheduledAlertHit.objects.filter(
            user_id=user_id,
            alert__rate=rate,
            hit_status=SCHEDULED_ALERT_HIT_STATUS.SCHEDULED,
        ).select_related("user", "alert")

        # Group scheduled hits by Alert and the main_doc_id
        grouped_hits: defaultdict[
            Alert, defaultdict[int, list[dict[str, Any]]]
        ] = defaultdict(lambda: defaultdict(list))
        alerts_to_update = set()
        for hit in scheduled_hits:
            alert = hit.alert
            doc_content = json_date_parser(hit.document_content)
            match hit.alert.alert_type:
                case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
                    main_doc_id = doc_content.get("docket_id")
                case SEARCH_TYPES.ORAL_ARGUMENT:
                    main_doc_id = doc_content.get("id")
                case SEARCH_TYPES.OPINION:
                    main_doc_id = doc_content.get("cluster_id")
                case _:
                    # Not supported alert type.
                    continue
            grouped_hits[alert][main_doc_id].append(doc_content)
            alerts_to_update.add(alert.pk)

        # Merge child documents with the same main_doc_id if the document dict
        # contains the child_docs key.
        merged_hits: defaultdict[Alert, list[dict[str, Any]]] = defaultdict(
            list
        )
        for alert, document_groups in grouped_hits.items():
            for documents in document_groups.values():
                merged_hits[alert].append(
                    merge_alert_child_documents(documents)
                )

        hits = []
        for alert, documents in merged_hits.items():
            # Override the search type to RECAP for case-only alerts (DOCKETS)
            search_type = (
                SEARCH_TYPES.RECAP
                if alert.alert_type == SEARCH_TYPES.DOCKETS
                else alert.alert_type
            )
            # Override query in the 'View Full Results' URL to
            # include a filter by timestamp.
            cut_off_date = get_cut_off_date(rate, now_time)
            qd = override_alert_query(alert, cut_off_date)
            alert.query_run = qd.urlencode()  # type: ignore
            hits.append((alert, search_type, documents, len(documents)))

        if hits:
            send_search_alert_emails.delay(
                [(user_id, hits)], scheduled_alert=True
            )
            alerts_sent_count += 1

        # Update Alert's date_last_hit in bulk for this user's alerts
        Alert.objects.filter(id__in=alerts_to_update).update(
            date_last_hit=now_time
        )

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
        if date.today().day > 28:
            raise InvalidDateError(
                "Monthly alerts cannot be run on the 29th, 30th or 31st."
            )
    query_and_send_alerts_by_rate(rate)


def delete_old_scheduled_alerts() -> int:
    """Delete Scheduled alerts older than DAYS_TO_DELETE days.

    :return: The number of deleted scheduled hit alerts.
    """

    # Delete SENT ScheduledAlertHits after DAYS_TO_DELETE
    sent_older_than = datetime.now() - timedelta(days=DAYS_TO_DELETE)
    scheduled_sent_hits_to_delete = ScheduledAlertHit.objects.filter(
        date_created__lt=sent_older_than,
        hit_status=SCHEDULED_ALERT_HIT_STATUS.SENT,
    ).delete()

    # Delete SCHEDULED ScheduledAlertHits after 2 * DAYS_TO_DELETE
    unsent_older_than = datetime.now() - timedelta(days=2 * DAYS_TO_DELETE)
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
        send_scheduled_alerts(options["rate"])
