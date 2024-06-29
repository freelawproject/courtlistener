import copy
import datetime
import traceback

from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.http import QueryDict
from django.utils.timezone import now
from elasticsearch.exceptions import RequestError, TransportError
from elasticsearch_dsl.response import Hit
from redis import Redis

from cl.alerts.models import Alert, ScheduledAlertHit
from cl.alerts.tasks import send_search_alert_emails
from cl.alerts.utils import (
    add_document_hit_to_alert_set,
    alert_hits_limit_reached,
    has_document_alert_hit_been_triggered,
    query_includes_rd_field,
    recap_document_hl_matched,
)
from cl.api.models import WebhookEventType
from cl.api.tasks import send_es_search_alert_webhook
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.elasticsearch_utils import do_es_sweep_alert_query
from cl.lib.redis_utils import get_redis_interface
from cl.search.documents import DocketSweepDocument
from cl.search.exception import (
    BadProximityQuery,
    UnbalancedParenthesesQuery,
    UnbalancedQuotesQuery,
)
from cl.search.models import SEARCH_TYPES, Docket
from cl.stats.utils import tally_stat
from cl.users.models import UserProfile


def index_daily_recap_documents():
    # TODO implement
    pass


def should_docket_hit_be_included(
    r: Redis, alert_id: int, docket_id: int
) -> bool:
    """Determine if a Docket alert should be triggered based on its
    date_modified and if the docket has triggered the alert previously.

    :param r: The Redis interface.
    :param alert_id: The ID of the alert.
    :param docket_id: The ID of the docket.
    :return: True if the Docket alert should be triggered, False otherwise.
    """
    docket = Docket.objects.filter(id=docket_id).only("date_modified").first()
    if not docket:
        return False
    date_modified = docket.date_modified.date()
    if not has_document_alert_hit_been_triggered(r, alert_id, "d", docket_id):
        if date_modified == now().date():
            return True
    return False


def filter_rd_alert_hits(r: Redis, alert_id: int, rd_hits, check_rd_hl=False):
    """Filter RECAP document hits based on specified conditions.

    :param r: The Redis interface.
    :param alert_id: The ID of the alert.
    :param rd_hits: A list of RECAP document hits to be processed.
    :param check_rd_hl: A boolean indicating whether to check if the RECAP
    document hit matched RD HLs.
    :return: A list of RECAP document hits that meet all specified conditions.
    """

    rds_to_send = []
    for rd_hit in rd_hits:
        conditions = [
            not has_document_alert_hit_been_triggered(
                r, alert_id, "r", rd_hit["_source"]["id"]
            )
        ]
        if check_rd_hl:
            conditions.append(recap_document_hl_matched(rd_hit))
        if all(conditions):
            rds_to_send.append(rd_hit)
            add_document_hit_to_alert_set(
                r, alert_id, "r", rd_hit["_source"]["id"]
            )
    return rds_to_send


def query_alerts(
    search_params: QueryDict,
) -> tuple[list[Hit] | None, int | None]:
    try:
        search_query = DocketSweepDocument.search()
        return do_es_sweep_alert_query(
            search_query,
            search_params,
        )
    except (
        UnbalancedParenthesesQuery,
        UnbalancedQuotesQuery,
        BadProximityQuery,
        TransportError,
        ConnectionError,
        RequestError,
    ):
        traceback.print_exc()
        logger.info(f"Search for this alert failed: {search_params}\n")
        return None, None


def process_alert_hits(
    r: Redis, results: list[Hit], search_params: QueryDict, alert_id: int
) -> list[Hit]:
    """Process alert hits by filtering and prepare the results to send based
    on alert conditions.

    :param r: The Redis instance.
    :param results: A list of Hit objects containing search results.
    :param search_params: Query parameters used for the search.
    :param alert_id: The ID of the alert being processed.
    :return: A list of Hit objects that are filtered and prepared to be sent.
    """

    includes_rd_fields = query_includes_rd_field(search_params)
    results_to_send = []
    if len(results) > 0:
        for hit in results:
            if not includes_rd_fields:
                # Possible Docket-only alert
                rds_to_send = filter_rd_alert_hits(
                    r, alert_id, hit["child_docs"], check_rd_hl=True
                )
                if rds_to_send:
                    # Cross-object query
                    hit["child_docs"] = rds_to_send
                    results_to_send.append(hit)
                elif should_docket_hit_be_included(r, alert_id, hit.docket_id):
                    # Docket-only alert
                    hit["child_docs"] = []
                    results_to_send.append(hit)
                    add_document_hit_to_alert_set(
                        r, alert_id, "d", hit.docket_id
                    )
            else:
                # RECAP-only alerts or cross-object alerts
                rds_to_send = filter_rd_alert_hits(
                    r, alert_id, hit["child_docs"]
                )
                if rds_to_send:
                    # Cross-object alert
                    hit["child_docs"] = rds_to_send
                    results_to_send.append(hit)
    return results_to_send


def send_search_alert_webhooks(
    user: UserProfile.user, results_to_send: list[Hit], alert_id: int
) -> None:
    """Send webhook events for search alerts if the user has SEARCH_ALERT
    endpoints enabled.

    :param user: The user object whose webhooks need to be checked.
    :param results_to_send: A list of Hit objects that contain the search
    results to be sent.
    :param alert_id: The Alert ID to be sent in the webhook.
    """
    user_webhooks = user.webhooks.filter(
        event_type=WebhookEventType.SEARCH_ALERT, enabled=True
    )
    for user_webhook in user_webhooks:
        send_es_search_alert_webhook.delay(
            results_to_send, user_webhook.pk, alert_id
        )


def query_and_send_alerts(rate: str) -> None:
    r = get_redis_interface("CACHE")
    alert_users: UserProfile.user = User.objects.filter(
        alerts__rate=rate
    ).distinct()
    alerts_sent_count = 0
    now_time = datetime.datetime.now()
    for user in alert_users:
        if rate == Alert.REAL_TIME:
            if not user.profile.is_member:
                continue
        alerts = user.alerts.filter(rate=rate, alert_type=SEARCH_TYPES.RECAP)
        logger.info(f"Running alerts for user '{user}': {alerts}")

        hits = []
        alerts_to_update = []
        for alert in alerts:
            search_params = QueryDict(alert.query.encode(), mutable=True)
            results, _ = query_alerts(search_params)
            if not results:
                continue
            alerts_to_update.append(alert.pk)
            search_type = search_params.get("type", SEARCH_TYPES.RECAP)
            results_to_send = process_alert_hits(
                r, results, search_params, alert.pk
            )
            if results_to_send:
                hits.append(
                    [
                        alert,
                        search_type,
                        results_to_send,
                        len(results_to_send),
                    ]
                )
                alert.query_run = search_params.urlencode()  # type: ignore
                alert.date_last_hit = now()
                alert.save()

                # Send webhooks
                send_search_alert_webhooks(user, results_to_send, alert.pk)

        if hits:
            send_search_alert_emails.delay([(user.pk, hits)])
            alerts_sent_count += 1

        # Update Alert's date_last_hit in bulk.
        Alert.objects.filter(id__in=alerts_to_update).update(
            date_last_hit=now_time
        )
        async_to_sync(tally_stat)(f"alerts.sent.{rate}", inc=alerts_sent_count)
        logger.info(f"Sent {alerts_sent_count} {rate} email alerts.")


def query_and_schedule_alerts(rate: str):
    r = get_redis_interface("CACHE")
    alert_users = User.objects.filter(alerts__rate=rate).distinct()
    for user in alert_users:
        alerts = user.alerts.filter(rate=rate, alert_type=SEARCH_TYPES.RECAP)
        logger.info(f"Running '{rate}' alerts for user '{user}': {alerts}")
        scheduled_hits_to_create = []
        for alert in alerts:
            search_params = QueryDict(alert.query.encode(), mutable=True)
            results, _ = query_alerts(search_params)
            if not results:
                continue
            results_to_send = process_alert_hits(
                r, results, search_params, alert.pk
            )
            if results_to_send:
                for hit in results_to_send:
                    # Schedule DAILY, WEEKLY and MONTHLY Alerts
                    if alert_hits_limit_reached(alert.pk, user.pk):
                        # Skip storing hits for this alert-user combination because
                        # the SCHEDULED_ALERT_HITS_LIMIT has been reached.
                        continue

                    child_result_objects = []
                    hit_copy = copy.deepcopy(hit)
                    if hasattr(hit_copy, "child_docs"):
                        for child_doc in hit_copy.child_docs:
                            child_result_objects.append(
                                child_doc["_source"].to_dict()
                            )
                    hit_copy["child_docs"] = child_result_objects
                    scheduled_hits_to_create.append(
                        ScheduledAlertHit(
                            user=user,
                            alert=alert,
                            document_content=hit_copy.to_dict(),
                        )
                    )
                    # Send webhooks
                    send_search_alert_webhooks(user, results_to_send, alert.pk)

        # Create scheduled WEEKLY and MONTHLY Alerts in bulk.
        if scheduled_hits_to_create:
            ScheduledAlertHit.objects.bulk_create(scheduled_hits_to_create)


class Command(VerboseCommand):
    help = "Send RECAP Search Alerts."

    def handle(self, *args, **options):
        super().handle(*args, **options)
        index_daily_recap_documents()
        query_and_send_alerts(Alert.REAL_TIME)
        query_and_send_alerts(Alert.DAILY)
        query_and_schedule_alerts(Alert.WEEKLY)
        query_and_schedule_alerts(Alert.MONTHLY)
