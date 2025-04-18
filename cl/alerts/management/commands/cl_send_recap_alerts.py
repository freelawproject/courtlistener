import copy
import datetime
import time
import traceback
from typing import Any, Literal

import pytz
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.http import QueryDict
from django.utils import timezone
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ApiError, RequestError, TransportError
from elasticsearch_dsl import connections
from elasticsearch_dsl.response import Hit, Response
from elasticsearch_dsl.utils import AttrList
from redis import Redis

from cl.alerts.models import Alert, ScheduledAlertHit
from cl.alerts.tasks import send_search_alert_emails
from cl.alerts.utils import (
    TaskCompletionStatus,
    add_document_hit_to_alert_set,
    has_document_alert_hit_been_triggered,
    scheduled_alert_hits_limit_reached,
)
from cl.api.models import WebhookEventType
from cl.api.tasks import send_search_alert_webhook_es
from cl.lib.argparse_types import valid_date_time
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.date_time import dt_as_local_date
from cl.lib.elasticsearch_utils import do_es_sweep_alert_query
from cl.lib.redis_utils import get_redis_interface
from cl.search.documents import (
    DocketDocument,
    ESRECAPSweepDocument,
    RECAPSweepDocument,
)
from cl.search.exception import (
    BadProximityQuery,
    DisallowedWildcardPattern,
    UnbalancedParenthesesQuery,
    UnbalancedQuotesQuery,
)
from cl.search.models import SEARCH_TYPES, Docket
from cl.stats.utils import tally_stat
from cl.users.models import UserProfile


def get_task_status(task_id: str, es: Elasticsearch) -> dict[str, Any]:
    """Fetch the status of a task from Elasticsearch.

    :param task_id: The ID of the task to fetch the status for.
    :param es: The Elasticsearch client instance.
    :return: The status of the task if successful, or an empty dictionary if
    an error occurs.
    """
    try:
        return es.tasks.get(task_id=task_id)
    except (
        TransportError,
        ConnectionError,
        RequestError,
    ) as e:
        logger.error("Error getting sweep alert index task status: %s", e)
        return {}


def compute_estimated_remaining_time(
    initial_wait: float, task_status: TaskCompletionStatus
) -> float:
    """Compute the estimated remaining time for the re_index task to complete.

    :param initial_wait: The default wait time in seconds.
    :param task_status: An instance of `TaskCompletionStatus` containing task
    information.
    :return: The estimated remaining time in seconds. If the start time,
    created, or total are invalid, the initial default time is returned.
    """

    if (
        task_status.start_time_millis is None
        or not task_status.created
        or not task_status.total
    ):
        return initial_wait

    start_time = datetime.datetime.fromtimestamp(
        task_status.start_time_millis / 1000.0
    )
    time_now = datetime.datetime.now()
    estimated_time_remaining = max(
        datetime.timedelta(
            seconds=(
                (time_now - start_time).total_seconds() / task_status.created
            )
            * (task_status.total - task_status.created)
        ).total_seconds(),
        initial_wait,
    )

    return estimated_time_remaining


def retrieve_task_info(task_info: dict[str, Any]) -> TaskCompletionStatus:
    """Retrieve task information from the given task dict.

    :param task_info: A dictionary containing the task status information.
    :return: A `TaskCompletionStatus` object representing the extracted task
    information.
    """

    if task_info:
        status = task_info["task"]["status"]
        return TaskCompletionStatus(
            completed=task_info["completed"],
            created=status["created"],
            total=status["total"],
            start_time_millis=task_info["task"]["start_time_in_millis"],
        )
    return TaskCompletionStatus()


def index_daily_recap_documents(
    r: Redis,
    source_index_name: str,
    target_index: type[RECAPSweepDocument] | type[ESRECAPSweepDocument],
    query_date: datetime.datetime,
    testing: bool = False,
    only_rd: bool = False,
) -> int:
    """Index Dockets added/modified during the day and all their RECAPDocuments
    and RECAPDocuments added/modified during the day and their parent Dockets.
    It uses the ES re_index API,

    :param r: Redis client instance.
    :param source_index_name: The source Elasticsearch index name from which
    documents will be queried.
    :param target_index: The target Elasticsearch index to which documents will
     be re-indexed.
    :param query_date: The query date to which documents will be queried.
    :param testing: Boolean flag for testing mode.
    :param only_rd: Whether to reindex only RECAPDocuments into the
    ESRECAPSweepDocument index.
    :return: The total number of documents re-indexed.
    """

    if target_index is RECAPSweepDocument and r.exists(
        "alert_sweep:main_re_index_completed"
    ):
        logger.info(
            "The main re-index task has been completed and will be omitted."
        )
        # The main re-indexing has been completed for the day. Abort it and
        # proceed with RECAPDocument re-index.
        return 0

    if target_index is ESRECAPSweepDocument and r.exists(
        "alert_sweep:rd_re_index_completed"
    ):
        logger.info(
            "The RECAPDocument only re-index task has been completed and will "
            "be omitted."
        )
        # The RECAPDocument re-indexing has been completed for the day. Abort
        # it and proceed with sending alerts.
        return 0

    logger.info(
        "Starting %s re-indexing process for date: %s",
        target_index._index._name,
        query_date,
    )

    es = connections.get_connection()
    # Convert the local (PDT) midnight time to UTC
    local_timezone = pytz.timezone(timezone.get_current_timezone_name())
    query_date_local_midnight_localized = local_timezone.localize(query_date)
    query_date_local_midnight_utc = (
        query_date_local_midnight_localized.astimezone(pytz.utc)
    )
    next_day_utc = query_date_local_midnight_utc + datetime.timedelta(days=1)
    query_date_datetime_iso = (
        query_date_local_midnight_utc.isoformat().replace("+00:00", "Z")
    )
    next_day_utc_iso = next_day_utc.isoformat().replace("+00:00", "Z")
    # Re Index API query.
    query = (
        {
            "bool": {
                "should": [
                    # Dockets added/modified today
                    {
                        "bool": {
                            "must": [
                                {
                                    "range": {
                                        "timestamp": {
                                            "gte": query_date_datetime_iso,
                                            "lt": next_day_utc_iso,
                                        }
                                    }
                                },
                                {"term": {"docket_child": "docket"}},
                            ]
                        }
                    },
                    # RECAPDocuments with parents added/modified today
                    {
                        "has_parent": {
                            "parent_type": "docket",
                            "query": {
                                "range": {
                                    "timestamp": {
                                        "gte": query_date_datetime_iso,
                                        "lt": next_day_utc_iso,
                                    }
                                }
                            },
                        }
                    },
                    # RECAPDocuments added/modified today
                    {
                        "bool": {
                            "must": [
                                {
                                    "range": {
                                        "timestamp": {
                                            "gte": query_date_datetime_iso,
                                            "lt": next_day_utc_iso,
                                        }
                                    }
                                },
                                {"term": {"docket_child": "recap_document"}},
                            ]
                        }
                    },
                    # Dockets that are parents of RECAPDocuments added/modified today
                    {
                        "has_child": {
                            "type": "recap_document",
                            "query": {
                                "range": {
                                    "timestamp": {
                                        "gte": query_date_datetime_iso,
                                        "lt": next_day_utc_iso,
                                    }
                                }
                            },
                        }
                    },
                ]
            }
        }
        if not only_rd
        else {
            "bool": {
                "should": [
                    # RECAPDocuments with parents added/modified today
                    {
                        "has_parent": {
                            "parent_type": "docket",
                            "query": {
                                "range": {
                                    "timestamp": {
                                        "gte": query_date_datetime_iso,
                                        "lt": next_day_utc_iso,
                                    }
                                }
                            },
                        }
                    },
                    # RECAPDocuments added/modified today
                    {
                        "bool": {
                            "must": [
                                {
                                    "range": {
                                        "timestamp": {
                                            "gte": query_date_datetime_iso,
                                            "lt": next_day_utc_iso,
                                        }
                                    }
                                },
                                {"term": {"docket_child": "recap_document"}},
                            ]
                        }
                    },
                ]
            }
        }
    )

    if not r.exists("alert_sweep:task_id"):
        # Remove the index from the previous day and create a new one.
        logger.info(
            "Deleting %s index from previous day.", target_index._index._name
        )
        target_index._index.delete(ignore=404)
        target_index.init()
        target_index_name = target_index._index._name

        # In case of a failure, store the task_id in Redis so the command
        # can be resumed.
        params = {
            "source": {"index": source_index_name, "query": query},
            "dest": {"index": target_index_name},
            "wait_for_completion": False,
            "refresh": True,
        }
        if only_rd:
            # Re-index only RECADocument fields to the ESRECAPSweepDocument
            # index
            params["script"] = {
                "source": """
                  def fields = [
                    'id',
                    'docket_entry_id',
                    'description',
                    'entry_number',
                    'entry_date_filed',
                    'short_description',
                    'document_type',
                    'document_number',
                    'pacer_doc_id',
                    'plain_text',
                    'attachment_number',
                    'is_available',
                    'page_count',
                    'filepath_local',
                    'absolute_url',
                    'cites'
                  ];
                  ctx._source.keySet().retainAll(fields);
                """
            }
        response = es.reindex(**params)
        # Store the task ID in Redis
        task_id = response["task"]
        r.set("alert_sweep:task_id", task_id, ex=3600 * 12)
        logger.info(
            "Re-indexing task for index %s scheduled with ID: %s",
            target_index_name,
            task_id,
        )
    else:
        task_id = r.get("alert_sweep:task_id")
        logger.info(
            "Resuming re-index task for index %s with ID: %s",
            target_index._index._name,
            task_id,
        )

    initial_wait = 0.01 if testing else 60.0
    time.sleep(initial_wait)
    task_info = retrieve_task_info(get_task_status(task_id, es))
    iterations_count = 0
    estimated_time_remaining = compute_estimated_remaining_time(
        initial_wait, task_info
    )
    while not task_info.completed:
        logger.info(
            f"Task progress: {task_info.created}/{task_info.total} documents. "
            f"Estimated time to finish: {estimated_time_remaining} seconds."
        )
        task_status = get_task_status(task_id, es)
        task_info = retrieve_task_info(task_status)
        time.sleep(min(estimated_time_remaining, 900))
        if task_info and not task_info.completed:
            estimated_time_remaining = compute_estimated_remaining_time(
                initial_wait, task_info
            )
        if not task_info:
            iterations_count += 1
        if iterations_count > 10:
            logger.error(
                "Re_index alert sweep index task has failed: %s/%s",
                task_info.created,
                task_info.total,
            )
            break

    r.delete("alert_sweep:task_id")
    return task_info.total


def should_docket_hit_be_included(
    r: Redis, alert_id: int, docket_id: int, query_date: datetime.date
) -> bool:
    """Determine if a Docket alert should be triggered based on its
    date_modified and if the docket has triggered the alert previously.

    :param r: The Redis interface.
    :param alert_id: The ID of the alert.
    :param docket_id: The ID of the docket.
    :param query_date: The daily re_index query date.
    :return: True if the Docket alert should be triggered, False otherwise.
    """
    docket = Docket.objects.filter(id=docket_id).only("date_modified").first()
    if not docket:
        return False
    if not has_document_alert_hit_been_triggered(r, alert_id, "d", docket_id):
        # Confirm the docket has been modified during the day we’re sending
        # alerts to avoid triggering docket-only alerts due to RECAPDocuments
        # related to the case being indexed during the day since RD contains
        # docket fields indexed which can trigger docket-only alerts.
        date_modified_localized = dt_as_local_date(docket.date_modified)
        if date_modified_localized == query_date:
            return True
    return False


def filter_rd_alert_hits(
    r: Redis,
    alert_id: int,
    rd_hits: AttrList,
    rd_ids: list[int],
    check_rd_matched=False,
):
    """Filter RECAP document hits based on specified conditions.

    :param r: The Redis interface.
    :param alert_id: The ID of the alert.
    :param rd_hits: A list of RECAPDocument hits to be processed.
    :param rd_ids: A list of RECAPDocument IDs that matched the RECAPDocument
    only query.
    :param check_rd_matched: A boolean indicating whether to check if the RECAP
     document hit from the main query also matches the RECAPDocument-only query
    :return: A list of RECAP document hits that meet all specified conditions.
    """

    rds_to_send = []
    for rd_hit in rd_hits:
        conditions = [
            not has_document_alert_hit_been_triggered(
                r, alert_id, "r", rd_hit["_source"]["id"]
            )
        ]
        if check_rd_matched:
            # Add condition to check if the RD hit is within the RD IDS returned
            # by the RECAPDocument-only query.
            conditions.append(rd_hit["_source"]["id"] in rd_ids)
        if all(conditions):
            rds_to_send.append(rd_hit)
            add_document_hit_to_alert_set(
                r, alert_id, "r", rd_hit["_source"]["id"]
            )
    return rds_to_send


def query_alerts(
    search_params: QueryDict,
) -> tuple[list[Hit] | None, Response | None, Response | None]:
    try:
        search_query = RECAPSweepDocument.search()
        child_search_query = ESRECAPSweepDocument.search()
        return do_es_sweep_alert_query(
            search_query,
            child_search_query,
            search_params,
        )
    except (
        UnbalancedParenthesesQuery,
        UnbalancedQuotesQuery,
        BadProximityQuery,
        DisallowedWildcardPattern,
        TransportError,
        ConnectionError,
        RequestError,
    ):
        traceback.print_exc()
        logger.info(f"Search for this alert failed: {search_params}\n")
        return None, None, None
    except ApiError as e:
        traceback.print_exc()
        logger.warning(
            "ApiError when querying an alert from the sweep index: %s", str(e)
        )
        return None, None, None


def process_alert_hits(
    r: Redis,
    results: list[Hit],
    parent_results: Response | None,
    child_results: Response | None,
    alert_id: int,
    query_date: datetime.date,
) -> list[Hit]:
    """Process alert hits by filtering and prepare the results to send based
    on alert conditions.

    :param r: The Redis instance.
    :param results: A list of Hit objects containing search results.
    :param parent_results: The ES Response for the docket-only query.
    :param child_results: The ES Response for the RECAPDocument-only query.
    :param alert_id: The ID of the alert being processed.
    :param query_date: The daily re_index query date.
    :return: A list of Hit objects that are filtered and prepared to be sent.
    """
    docket_hits = parent_results.hits if parent_results else []
    docket_ids = [int(d.docket_id) for d in docket_hits]

    rd_hits = child_results.hits if child_results else []
    rd_ids = [int(r.id) for r in rd_hits]
    results_to_send = []
    if len(results) > 0:
        for hit in results:
            if hit.docket_id in docket_ids:
                # Possible Docket-only alert
                rds_to_send = filter_rd_alert_hits(
                    r,
                    alert_id,
                    hit["child_docs"],
                    rd_ids,
                    check_rd_matched=True,
                )
                if rds_to_send:
                    # Docket OR RECAPDocument alert.
                    # This includes hits triggered by an alert that can
                    # match Dockets or RECAPDocuments at the same time.
                    # e.g: q=docket_id:34238745 OR pacer_doc_id:1014052133
                    hit["child_docs"] = rds_to_send
                    results_to_send.append(hit)
                    if should_docket_hit_be_included(
                        r, alert_id, hit.docket_id, query_date
                    ):
                        add_document_hit_to_alert_set(
                            r, alert_id, "d", hit.docket_id
                        )

                elif should_docket_hit_be_included(
                    r, alert_id, hit.docket_id, query_date
                ):
                    # Docket-only alert
                    # This alert query matched only Dockets.
                    # e.g: docket_number=23-43434
                    hit["child_docs"] = []
                    results_to_send.append(hit)
                    add_document_hit_to_alert_set(
                        r, alert_id, "d", hit.docket_id
                    )
            else:
                # RECAPDocument-only alerts or cross-object alerts
                # This alert query matched either only RECAPDocuments
                # e.g., document_number:1
                # or a combination of RECAPDocument fields and Docket-level fields,
                # e.g., document_number:1 & docket_number:23-43434
                rds_to_send = filter_rd_alert_hits(
                    r, alert_id, hit["child_docs"], rd_ids
                )
                if rds_to_send:
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
        send_search_alert_webhook_es.delay(
            results_to_send, user_webhook.pk, alert_id
        )


def query_and_send_alerts(
    r: Redis, rate: Literal["rt", "dly"], query_date: datetime.date
) -> None:
    """Query the sweep index and send alerts based on the specified rate
    and date.

    :param r: The Redis interface.
    :param rate: The rate at which to query alerts.
    :param query_date: The daily re_index query date.
    :return: None.
    """
    alert_users: UserProfile.user = User.objects.filter(
        alerts__rate=rate, alerts__alert_type=SEARCH_TYPES.RECAP
    ).distinct()
    total_alerts_sent_count = 0
    now_time = datetime.datetime.now()
    for user in alert_users:
        if rate == Alert.REAL_TIME and not user.profile.is_member:
            continue
        alerts = user.alerts.filter(rate=rate, alert_type=SEARCH_TYPES.RECAP)
        logger.info(
            "Running '%s' alerts for user '%s': %s", rate, user, alerts
        )

        hits = []
        alerts_sent = []
        for alert in alerts:
            search_params = QueryDict(alert.query.encode(), mutable=True)
            results, parent_results, child_results = query_alerts(
                search_params
            )
            if not results:
                continue
            search_type = search_params.get("type", SEARCH_TYPES.RECAP)
            results_to_send = process_alert_hits(
                r, results, parent_results, child_results, alert.pk, query_date
            )
            if not results_to_send:
                continue
            alerts_sent.append(alert.pk)
            hits.append(
                [
                    alert,
                    search_type,
                    results_to_send,
                    len(results_to_send),
                ]
            )
            alert.query_run = search_params.urlencode()  # type: ignore
            alert.date_last_hit = timezone.now()
            alert.save()
            # Send webhooks
            send_search_alert_webhooks(user, results_to_send, alert.pk)

        if hits:
            send_search_alert_emails.delay([(user.pk, hits)])
            total_alerts_sent_count += 1
            logger.info(
                "Sent %s '%s' alerts for user '%s'",
                len(alerts_sent),
                rate,
                user,
            )

        # Update Alert's date_last_hit in bulk.
        Alert.objects.filter(id__in=alerts_sent).update(date_last_hit=now_time)

    # Log and tally the total alerts sent
    async_to_sync(tally_stat)(
        f"alerts.sent.{rate}", inc=total_alerts_sent_count
    )
    logger.info(f"Sent {total_alerts_sent_count} {rate} email alerts.")


def query_and_schedule_alerts(
    r: Redis, rate: Literal["wly", "mly"], query_date: datetime.date
) -> None:
    """Query the sweep index and schedule alerts based on the specified rate
    and date.

    :param r: The Redis interface.
    :param rate: The rate at which to query alerts.
    :param query_date: The daily re_index query date.
    :return: None.
    """

    alert_users = User.objects.filter(
        alerts__rate=rate, alerts__alert_type=SEARCH_TYPES.RECAP
    ).distinct()
    docket_content_type = ContentType.objects.get(
        app_label="search", model="docket"
    )
    for user in alert_users:
        alerts = user.alerts.filter(rate=rate, alert_type=SEARCH_TYPES.RECAP)
        logger.info(
            f"Running '%s' alerts for user '%s': %s", rate, user, alerts
        )
        scheduled_hits_to_create = []
        for alert in alerts:
            search_params = QueryDict(alert.query.encode(), mutable=True)
            results, parent_results, child_results = query_alerts(
                search_params
            )
            if not results:
                continue

            results_to_send = process_alert_hits(
                r, results, parent_results, child_results, alert.pk, query_date
            )
            if not results_to_send:
                continue
            for hit in results_to_send:
                # Schedule DAILY, WEEKLY and MONTHLY Alerts
                if scheduled_alert_hits_limit_reached(alert.pk, user.pk):
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
                        content_type=docket_content_type,
                        object_id=hit_copy.docket_id,
                    )
                )
                # Send webhooks
                send_search_alert_webhooks(user, results_to_send, alert.pk)

        # Create scheduled WEEKLY and MONTHLY Alerts in bulk.
        if scheduled_hits_to_create:
            ScheduledAlertHit.objects.bulk_create(scheduled_hits_to_create)
            logger.info(
                "Scheduled %s '%s' alerts for user '%s'",
                len(scheduled_hits_to_create),
                rate,
                user,
            )


def get_day_before_query_date() -> datetime.datetime:
    """Get the datetime representing the day before the current local date.

    :return: A naive datetime object representing midnight of the day before
    the current local date.
    """
    local_now = timezone.localtime().replace(tzinfo=None)
    local_midnight = local_now.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return local_midnight - datetime.timedelta(days=1)


class Command(VerboseCommand):
    """Query and re-index (into the RECAP sweep index) all the RECAP content
    that has changed during the current period, along with their related
    documents. Then use the RECAP sweep index to query and send real-time and
    daily RECAP alerts. Finally, schedule weekly and monthly RECAP alerts.
    """

    help = "Send RECAP Search Alerts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--testing-mode",
            action="store_true",
            default=False,
            help="Use this flag for testing purposes.",
        )
        parser.add_argument(
            "--query-date",
            type=valid_date_time,
            help="Query date in ISO-8601 format.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        testing_mode = options["testing_mode"]
        r = get_redis_interface("CACHE")
        query_date: datetime.datetime | None = options["query_date"]

        if query_date is not None:
            # Convert the provided query_date to midnight.
            query_date = query_date.replace(
                hour=0, minute=0, second=0, microsecond=0
            ).replace(tzinfo=None)
        else:
            # Date query from previous day since the command currently runs
            # early each day.
            query_date = get_day_before_query_date()

        index_daily_recap_documents(
            r,
            DocketDocument._index._name,
            RECAPSweepDocument,
            query_date,
            testing=testing_mode,
        )
        if not testing_mode:
            # main_re_index_completed key so the main re_index task can be
            # omitted in case of a failure.
            r.set("alert_sweep:main_re_index_completed", 1, ex=3600 * 12)
        index_daily_recap_documents(
            r,
            DocketDocument._index._name,
            ESRECAPSweepDocument,
            query_date,
            testing=testing_mode,
            only_rd=True,
        )
        if not testing_mode:
            # rd_re_index_completed key so the RECAPDocument re_index task
            # can be omitted in case of a failure.
            r.set("alert_sweep:rd_re_index_completed", 1, ex=3600 * 12)

        date_to_query = query_date.date()
        query_and_send_alerts(r, Alert.REAL_TIME, date_to_query)
        query_and_send_alerts(r, Alert.DAILY, date_to_query)
        query_and_schedule_alerts(r, Alert.WEEKLY, date_to_query)
        query_and_schedule_alerts(r, Alert.MONTHLY, date_to_query)
        r.delete("alert_sweep:main_re_index_completed")
        r.delete("alert_sweep:rd_re_index_completed")
