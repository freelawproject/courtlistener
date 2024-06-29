import datetime
import traceback

from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.http import QueryDict
from django.utils.timezone import now
from elasticsearch.exceptions import RequestError, TransportError
from redis import Redis

from cl.alerts.models import Alert
from cl.alerts.tasks import send_search_alert_emails
from cl.alerts.utils import (
    add_document_hit_to_alert_set,
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


def filter_rd_alert_hits(r, alert_id, rd_hits, check_rd_hl=False):
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


def query_and_send_alerts(rate):
    r = get_redis_interface("CACHE")
    alert_users = User.objects.filter(alerts__rate=rate).distinct()
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
            includes_rd_fields = query_includes_rd_field(search_params)
            try:
                search_query = DocketSweepDocument.search()
                results, total_hits = do_es_sweep_alert_query(
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
                logger.info(f"Search for this alert failed: {alert.query}\n")
                continue

            alerts_to_update.append(alert.pk)
            if len(results) > 0:
                search_type = search_params.get("type", SEARCH_TYPES.RECAP)
                results_to_send = []
                for hit in results:
                    if not includes_rd_fields:
                        # Possible Docket-only alert
                        rds_to_send = filter_rd_alert_hits(
                            r, alert.pk, hit["child_docs"], check_rd_hl=True
                        )
                        if rds_to_send:
                            # Cross-object query
                            hit["child_docs"] = rds_to_send
                            results_to_send.append(hit)
                        elif should_docket_hit_be_included(
                            r, alert.pk, hit.docket_id
                        ):
                            # Docket-only alert
                            hit["child_docs"] = []
                            results_to_send.append(hit)
                            add_document_hit_to_alert_set(
                                r, alert.pk, "d", hit.docket_id
                            )
                    else:
                        # RECAP-only alerts or cross-object alerts
                        rds_to_send = filter_rd_alert_hits(
                            r, alert.pk, hit["child_docs"]
                        )
                        if rds_to_send:
                            # Cross-object alert
                            hit["child_docs"] = rds_to_send
                            results_to_send.append(hit)

                if results_to_send:
                    hits.append(
                        [
                            alert,
                            search_type,
                            results_to_send,
                            len(results_to_send),
                        ]
                    )
                    alert.query_run = search_params.urlencode()
                    alert.date_last_hit = now()
                    alert.save()

                    # Send webhook event if the user has a SEARCH_ALERT
                    # endpoint enabled.
                    user_webhooks = user.webhooks.filter(
                        event_type=WebhookEventType.SEARCH_ALERT, enabled=True
                    )
                    for user_webhook in user_webhooks:
                        send_es_search_alert_webhook.delay(
                            results_to_send, user_webhook.pk, alert.pk
                        )

        if hits:
            send_search_alert_emails.delay([(user.pk, hits)])
            alerts_sent_count += 1

        # Update Alert's date_last_hit in bulk.
        Alert.objects.filter(id__in=alerts_to_update).update(
            date_last_hit=now_time
        )
        async_to_sync(tally_stat)(f"alerts.sent.{rate}", inc=alerts_sent_count)
        logger.info(f"Sent {alerts_sent_count} {rate} email alerts.")


def query_and_schedule_wly_and_mly_alerts():
    # TODO implement
    pass


class Command(VerboseCommand):
    help = "Send RECAP Search Alerts."

    def handle(self, *args, **options):
        super().handle(*args, **options)
        index_daily_recap_documents()
        query_and_send_alerts(Alert.REAL_TIME)
        query_and_send_alerts(Alert.DAILY)
        query_and_schedule_wly_and_mly_alerts()
