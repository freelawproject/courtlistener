"""Scheduling of RECAP Fetch API requests.

The API puts new requests in the Redis waiting room (see
cl.recap.fetch_queue), and the scheduler daemon hands them to Celery when
their court is ready for them. This module holds the pieces that need the
database and Celery: scheduling a new request, handing requests off, and
failing the ones that waited too long.
"""

import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.http import HttpRequest
from django.utils.timezone import now
from sentry_sdk import capture_exception
from waffle import flag_is_active

from cl.api.webhooks import send_recap_fetch_webhooks
from cl.recap.fetch_queue import (
    clear_pending_fetch,
    daemon_is_alive,
    enqueue_fetch,
    estimate_delay,
    get_courts_with_waiting_fetches,
    get_pending_fetch,
    mark_fetch_started,
    pop_next_fetch,
    remove_fetch,
)
from cl.recap.models import PROCESSING_STATUS, PacerFetchQueue
from cl.recap.tasks import do_pacer_fetch, mark_fq_status
from cl.recap.utils import get_court_id_from_fetch_queue

logger = logging.getLogger(__name__)

# Waffle flag that sends a user's new Fetch API requests through the waiting
# room. It is a flag rather than a switch so it can be turned on for a few
# users first. While it is off, requests go straight to Celery as before.
SCHEDULER_FLAG = "recap_fetch_scheduler"

# A request that has not started this long after it was made is failed. The
# user's PACER cookies are cached for an hour and we never store their
# password, so past that point the request could not succeed anyway.
STALE_AFTER = timedelta(minutes=70)

# Don't fail requests older than this. It keeps the first run in production
# from sending webhooks for rows that have been stuck for months.
SWEEP_LOOKBACK = timedelta(days=1)

STALE_MESSAGE = (
    "This request waited too long to start and was cancelled before "
    "anything was requested from PACER. Please submit it again."
)


def should_schedule(request: HttpRequest) -> bool:
    """Decide whether a new Fetch API request goes through the waiting room.

    Requests are only queued while the scheduler daemon is running. If the
    flag is on but the daemon is down, they go straight to Celery as before,
    so they don't sit in Redis with nothing to hand them off.

    Args:
        request: The Django request that is creating the fetch, with its user
            already authenticated, so the flag can target that user.

    Returns:
        True if the request should be put in the waiting room.
    """
    if not flag_is_active(request, SCHEDULER_FLAG):
        return False
    if not daemon_is_alive():
        logger.warning(
            "The %s flag is on but the scheduler daemon is not running. "
            "Sending the request straight to Celery.",
            SCHEDULER_FLAG,
        )
        return False
    return True


def schedule_fetch(fq: PacerFetchQueue) -> float:
    """Put a new request in line and tell its user how long the wait may be.

    The explanation of the estimate is saved to the request's message, where
    the API returns it.

    Args:
        fq: The PacerFetchQueue row, already saved with status ENQUEUED.

    Returns:
        The estimated wait in seconds. See estimate_delay for what the number
        does and does not promise.
    """
    court_id = get_court_id_from_fetch_queue(fq)
    enqueue_fetch(court_id, fq.user_id, fq.pk)
    delay = estimate_delay(court_id, fq.user_id)
    fq.message = (
        f"Waiting in the queue for court {court_id}. Estimated wait before "
        f"we start this request: {round(delay)} s. That is an estimate of "
        "when we will begin the request to PACER, not of when it will "
        "finish, and it can grow if other users join the queue for this "
        "court, if the court's rate is lowered or if our workers are busy."
    )
    fq.save(update_fields=["message"])
    return delay


def hand_off_fetch(court_id: str, fq_pk: int) -> bool:
    """Send a request that has left the line to Celery.

    If the request cannot be sent it is marked as failed rather than put back
    in line. Putting it back risks running it twice, and every run is billed
    to the user's PACER account.

    Args:
        court_id: The court the request was taken from.
        fq_pk: The PK returned by pop_next_fetch.

    Returns:
        True if the request was sent to Celery.
    """
    fq = PacerFetchQueue.objects.filter(
        pk=fq_pk, status=PROCESSING_STATUS.ENQUEUED
    ).first()
    if fq is None:
        # Deleted or already finished while it waited: nothing to run.
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
    handed_off = 0
    for court_id in get_courts_with_waiting_fetches():
        if (pending_pk := get_pending_fetch(court_id)) is not None:
            still_waiting = PacerFetchQueue.objects.filter(
                pk=pending_pk, status=PROCESSING_STATUS.ENQUEUED
            ).exists()
            if not still_waiting:
                mark_fetch_started(court_id, pending_pk)
            continue

        if (fq_pk := pop_next_fetch(court_id)) is None:
            continue
        if hand_off_fetch(court_id, fq_pk):
            handed_off += 1
    return handed_off


def fail_stale_fetches() -> int:
    """Fail requests that have waited too long to ever succeed.

    This is what guarantees no request stays in ENQUEUED forever, whatever
    happened to it: lost from Redis, lost on the way to Celery, or stuck
    behind workers that never came back.

    Only ENQUEUED rows are touched. Once a task has started, the request
    belongs to Celery and its retries.

    Returns:
        The number of requests that were failed.
    """
    cutoff = now() - STALE_AFTER
    stale_fqs = PacerFetchQueue.objects.filter(
        status=PROCESSING_STATUS.ENQUEUED,
        date_created__lt=cutoff,
        date_created__gt=now() - SWEEP_LOOKBACK,
    )
    failed = 0
    for fq in stale_fqs.iterator():
        # Claim the row only if it is still ENQUEUED, so a task that started
        # between the query above and this line is left alone.
        claimed = PacerFetchQueue.objects.filter(
            pk=fq.pk, status=PROCESSING_STATUS.ENQUEUED
        ).update(
            status=PROCESSING_STATUS.FAILED,
            message=STALE_MESSAGE,
            date_modified=now(),
        )
        if not claimed:
            continue
        failed += 1
        fq.status = PROCESSING_STATUS.FAILED
        fq.message = STALE_MESSAGE
        async_to_sync(send_recap_fetch_webhooks)(fq)
        remove_fetch(get_court_id_from_fetch_queue(fq), fq.user_id, fq.pk)
    return failed
