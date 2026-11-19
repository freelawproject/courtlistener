"""Scheduling of RECAP Fetch API requests.

The API puts new requests in the Redis waiting room (see
cl.recap.fetch_queue), and the scheduler daemon hands them to Celery when
their court is ready for them. This module holds the pieces that need the
database and Celery: scheduling a new request, handing requests off, and
failing the ones that waited too long.
"""

import logging
from datetime import datetime, timedelta
from functools import partial

from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.http import HttpRequest
from django.utils.timezone import now
from redis.exceptions import RedisError
from sentry_sdk import capture_exception
from waffle import flag_is_active

from cl.lib.pacer_session import get_pacer_cookie_from_cache
from cl.recap.fetch_queue import (
    clear_pending_fetch,
    daemon_is_alive,
    enqueue_fetch,
    estimate_delay,
    get_courts_with_waiting_fetches,
    get_pending_fetches,
    get_queued_fetches,
    mark_fetch_started,
    pop_next_fetch,
    remove_fetch,
)
from cl.recap.models import PROCESSING_STATUS, PacerFetchQueue
from cl.recap.tasks import do_pacer_fetch, mark_fq_status, send_fq_webhooks
from cl.recap.utils import get_court_id_from_fetch_queue

logger = logging.getLogger(__name__)

# Waffle flag that sends a user's new Fetch API requests through the waiting
# room. It is a flag rather than a switch so it can be turned on for a few
# users first. While it is off, requests go straight to Celery as before.
SCHEDULER_FLAG = "recap_fetch_scheduler"

# The queue writes one of these at the start of the message of each request
# it holds: the first while the request waits in line, the second once it is
# handed to Celery. Requests from other flows (recap.email, pacer_bulk_fetch)
# never carry them, so the sweeper uses them to tell the queue's own requests
# apart, even if Redis is lost. A fetch task replaces the message when it
# starts.
QUEUED_MESSAGE_PREFIX = "Waiting in the queue for court"
HANDED_OFF_MESSAGE_PREFIX = "Sent to our workers for court"

# The sweeper leaves a queued request alone until the queue last touched it
# this long ago: when it joined the line, or when it was handed to Celery.
# The user's PACER cookies are cached for an hour, and Celery retries a
# failing task for a few minutes, so a younger request may well still
# succeed.
STALE_AFTER = timedelta(minutes=70)

# The sweeper ignores requests created before this. It runs every minute, and
# the bound lets PostgreSQL skip the years of old rows of this table. No
# queued request waits this long while its session is alive, so only a daemon
# that was down for longer would leave rows behind.
SWEEP_LOOKBACK = timedelta(days=7)

SESSION_EXPIRED_MESSAGE = (
    "Your PACER session expired while this request waited in the queue, so "
    "it was cancelled before anything was requested from PACER. Please "
    "submit it again."
)

LOST_MESSAGE = (
    "This request was lost from the queue and was cancelled before anything "
    "was requested from PACER. Please submit it again."
)

# A handed-off task may have reached PACER before it was lost or rolled back,
# so unlike the messages above, this one makes no promise about that.
STALLED_MESSAGE = (
    "This request was sent to our workers but did not finish, so it was "
    "cancelled. Please submit it again."
)


def should_schedule(request: HttpRequest) -> bool:
    """Decide whether a new Fetch API request goes through the waiting room.

    Requests are only queued while the scheduler daemon is running. If the
    flag is on but the daemon is down or Redis can't be reached, they go
    straight to Celery as before, so they don't sit in Redis with nothing to
    hand them off.

    Args:
        request: The Django request that is creating the fetch, with its user
            already authenticated, so the flag can target that user.

    Returns:
        True if the request should be put in the waiting room.
    """
    if not flag_is_active(request, SCHEDULER_FLAG):
        return False
    try:
        alive = daemon_is_alive()
    except RedisError:
        logger.warning("Unable to reach Redis. Sending the request to Celery.")
        return False
    if not alive:
        logger.warning(
            "The %s flag is on but the scheduler daemon is not running. "
            "Sending the request straight to Celery.",
            SCHEDULER_FLAG,
        )
    return alive


def schedule_fetch(fq: PacerFetchQueue) -> float | None:
    """Put a new request in line and tell its user how long the wait may be.

    The explanation of the estimate is saved to the request's message, where
    the API returns it. The request only joins the line in Redis once the
    current transaction commits, so the daemon never takes a PK whose row it
    can't read yet.

    Args:
        fq: The PacerFetchQueue row, already saved with status ENQUEUED.

    Returns:
        The estimated wait in seconds, or None if Redis could not be reached
        before anything was queued. The caller must then send the request to
        Celery itself. See estimate_delay for what the number does and does
        not promise.
    """
    court_id = get_court_id_from_fetch_queue(fq)
    try:
        delay = estimate_delay(court_id, fq.user_id, not_yet_queued=1)
    except RedisError:
        logger.warning(
            "Unable to reach Redis to queue fetch request %s.", fq.pk
        )
        return None
    fq.message = (
        f"{QUEUED_MESSAGE_PREFIX} {court_id}. Estimated wait before we "
        f"start this request: {round(delay)} s. That is an estimate of when "
        "we will begin the request to PACER, not of when it will finish, "
        "and it can grow if other users join the queue for this court, if "
        "the court's rate is lowered or if our workers are busy."
    )
    fq.save(update_fields=["message"])
    transaction.on_commit(partial(enqueue_fetch, court_id, fq.user_id, fq.pk))
    return delay


def _has_pacer_session(user_id: int) -> bool:
    """Check whether a user's PACER session is still cached.

    Fetch tasks run with these cookies, since we never store the user's
    password. Without them a queued request can't succeed.

    Args:
        user_id: The user who made the request.

    Returns:
        True if the user's PACER cookies are still in the cache.
    """
    return async_to_sync(get_pacer_cookie_from_cache)(user_id) is not None


def _fail_queued_fetch(
    fq_pk: int, read_date_modified: datetime, message: str
) -> bool:
    """Fail a request that is still waiting, and tell its user.

    Args:
        fq_pk: The PK of the PacerFetchQueue row to fail.
        read_date_modified: The row's date_modified when the caller read it.
        message: Why it failed, for the user.

    Returns:
        True if the row was failed. False means something changed it since
        it was read, e.g. the daemon handed it off or its task started, and
        it was left alone.
    """
    with transaction.atomic(using="default"):
        # Claim the row only if nothing touched it since it was read. A row
        # that is locked belongs to a task that is running right now: PDF and
        # attachment tasks hold the lock until they finish, and we read the
        # row as ENQUEUED only because their changes aren't committed yet.
        # Skip it rather than stall the daemon until the task ends.
        claimed = list(
            PacerFetchQueue.objects.using("default")
            .select_for_update(skip_locked=True)
            .filter(
                pk=fq_pk,
                status=PROCESSING_STATUS.ENQUEUED,
                date_modified=read_date_modified,
            )
            .values_list("pk", flat=True)
        )
        if not claimed:
            return False
        PacerFetchQueue.objects.using("default").filter(pk=fq_pk).update(
            status=PROCESSING_STATUS.FAILED,
            message=message,
            date_modified=now(),
        )
        # Webhooks go through Celery, so a slow endpoint can't hold up the
        # daemon.
        transaction.on_commit(
            partial(send_fq_webhooks.delay, fq_pk), using="default"
        )
    return True


def hand_off_fetch(court_id: str, fq_pk: int) -> bool:
    """Send a request that has left the line to Celery.

    If the request cannot be sent it is marked as failed rather than put back
    in line. Putting it back risks running it twice, and every run is billed
    to the user's PACER account.

    A request whose user's PACER session expired while it waited is failed
    here too, without using the court's turn: its task would only fail once
    it started.

    Args:
        court_id: The court the request was taken from.
        fq_pk: The PK returned by pop_next_fetch.

    Returns:
        True if the request was sent to Celery.
    """
    # The daemon never sets up replica routing, so these queries go to the
    # primary database. Saying so keeps it that way if routing changes.
    fq = (
        PacerFetchQueue.objects.using("default")
        .filter(pk=fq_pk, status=PROCESSING_STATUS.ENQUEUED)
        .first()
    )
    if fq is None:
        # Deleted or already finished while it waited: nothing to run.
        clear_pending_fetch(court_id, fq_pk)
        return False

    if not _has_pacer_session(fq.user_id):
        _fail_queued_fetch(fq.pk, fq.date_modified, SESSION_EXPIRED_MESSAGE)
        clear_pending_fetch(court_id, fq_pk)
        return False

    # Record the hand-off before Celery can pick the task up. The sweeper
    # then knows the request may have reached PACER, and gives its task a
    # full STALE_AFTER from now to finish, even if a retry rolls back the
    # task's own status changes.
    claimed = (
        PacerFetchQueue.objects.using("default")
        .filter(pk=fq_pk, status=PROCESSING_STATUS.ENQUEUED)
        .update(
            message=f"{HANDED_OFF_MESSAGE_PREFIX} {court_id}. Waiting for "
            "one of them to start it.",
            date_modified=now(),
        )
    )
    if not claimed:
        clear_pending_fetch(court_id, fq_pk)
        return False

    try:
        do_pacer_fetch(fq)
    except Exception as e:
        logger.exception("Unable to send fetch request %s to Celery.", fq_pk)
        capture_exception(e)
        async_to_sync(mark_fq_status)(
            fq,
            "We were unable to schedule this request. Please submit it again.",
            PROCESSING_STATUS.FAILED,
        )
        clear_pending_fetch(court_id, fq_pk)
        return False
    return True


def run_dispatch_cycle() -> int:
    """Hand off at most one request per court, for each court that is ready.

    A court is ready when its previous request has started and its interval
    has passed since then. The fetch tasks report their start in Redis (see
    report_fetch_started). As a fallback, a row that has left ENQUEUED in
    PostgreSQL also counts as started.

    Safe to run from several processes at once.

    Returns:
        The number of requests handed off.
    """
    courts = get_courts_with_waiting_fetches()
    pending = get_pending_fetches(courts)
    # One query for every court, rather than one per court and cycle.
    still_waiting = (
        set(
            PacerFetchQueue.objects.using("default")
            .filter(pk__in=pending.values(), status=PROCESSING_STATUS.ENQUEUED)
            .values_list("pk", flat=True)
        )
        if pending
        else set()
    )

    handed_off = 0
    for court_id in courts:
        if (pending_pk := pending.get(court_id)) is not None:
            if pending_pk not in still_waiting:
                mark_fetch_started(court_id, pending_pk)
            continue

        if (fq_pk := pop_next_fetch(court_id)) is None:
            continue
        if hand_off_fetch(court_id, fq_pk):
            handed_off += 1
    return handed_off


def fail_stale_fetches() -> int:
    """Fail queued requests that can no longer succeed.

    This is what guarantees that no request stays in ENQUEUED forever. A
    request the queue last touched more than STALE_AFTER ago is failed when:

    - it is still waiting in line and its user's PACER session has expired,
      so its task would fail anyway,
    - it is still waiting in line but the queue no longer knows about it,
      e.g. because Redis lost it, so nothing would ever run it, or
    - it was handed to Celery and its task never got past the start, e.g.
      because the task was lost, so nothing would ever finish it.

    A request that is still in line with a live session is left alone, even
    if it is old: a user with a large batch keeps their session alive with
    each new request.

    Only requests that went through the queue are touched. Requests from
    other flows (recap.email, pacer_bulk_fetch) and requests whose task has
    started are not.

    Returns:
        The number of requests that were failed.
    """
    candidates = (
        PacerFetchQueue.objects.using("default")
        .filter(
            Q(message__startswith=QUEUED_MESSAGE_PREFIX)
            | Q(message__startswith=HANDED_OFF_MESSAGE_PREFIX),
            status=PROCESSING_STATUS.ENQUEUED,
            date_modified__lt=now() - STALE_AFTER,
            date_created__gt=now() - SWEEP_LOOKBACK,
        )
        # The same court the request was queued under: see
        # get_court_id_from_fetch_queue. Annotating it avoids a query per row.
        .annotate(
            queue_court_id=Coalesce(
                "recap_document__docket_entry__docket__court_id",
                "docket__court_id",
                "court_id",
            )
        )
        .values_list(
            "pk", "user_id", "queue_court_id", "message", "date_modified"
        )
    )
    has_session: dict[int, bool] = {}
    queued: dict[tuple[str, int], set[int]] = {}
    failed = 0
    for (
        fq_pk,
        user_id,
        court_id,
        fq_message,
        date_modified,
    ) in candidates.iterator():
        if fq_message.startswith(HANDED_OFF_MESSAGE_PREFIX):
            message = STALLED_MESSAGE
        else:
            if user_id not in has_session:
                has_session[user_id] = _has_pacer_session(user_id)
            if (court_id, user_id) not in queued:
                queued[court_id, user_id] = get_queued_fetches(
                    court_id, user_id
                )

            if not has_session[user_id]:
                message = SESSION_EXPIRED_MESSAGE
            elif fq_pk not in queued[court_id, user_id]:
                message = LOST_MESSAGE
            else:
                continue

        if _fail_queued_fetch(fq_pk, date_modified, message):
            failed += 1
            # Don't let a failed request use a turn.
            remove_fetch(court_id, user_id, fq_pk)
    return failed
