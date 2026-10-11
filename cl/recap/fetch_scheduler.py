"""Waiting room for RECAP Fetch API requests.

Requests made through the Fetch API wait here, in Redis, until the scheduler
daemon hands them to Celery. Only the PK of each PacerFetchQueue row is kept
here; PostgreSQL remains the source of truth for the request itself.
"""

from cl.lib.redis_utils import get_redis_interface
from cl.recap.models import PacerFetchQueue
from cl.recap.tasks import do_pacer_fetch

# Waffle switch that sends new Fetch API requests through this waiting room.
# While it is off, requests go straight to Celery as they did before.
SCHEDULER_SWITCH = "recap-fetch-scheduler"

QUEUE_KEY = "recap_fetch:queue"


def enqueue_fetch(fq_pk: int) -> None:
    """Put a request at the back of the line.

    :param fq_pk: The PK of the PacerFetchQueue row to schedule.
    """
    r = get_redis_interface("CACHE")
    r.rpush(QUEUE_KEY, fq_pk)


def pop_next_fetch() -> int | None:
    """Take the request at the front of the line.

    The caller MUST hand the returned request to Celery: it has left the line,
    and nothing else will run it.

    :return: The PK of the PacerFetchQueue row, or None if nothing is waiting.
    """
    r = get_redis_interface("CACHE")
    fq_pk = r.lpop(QUEUE_KEY)
    return int(str(fq_pk)) if fq_pk else None


def hand_off_fetch(fq_pk: int) -> None:
    """Send a request that has left the line to Celery.

    :param fq_pk: The PK returned by pop_next_fetch.
    """
    fq = PacerFetchQueue.objects.filter(pk=fq_pk).first()
    if fq is None:
        # The row was deleted while it waited, so there is nothing to run.
        return
    do_pacer_fetch(fq)


def run_dispatch_cycle() -> int:
    """Hand every waiting request to Celery, in the order they arrived.

    :return: The number of requests handed off.
    """
    handed_off = 0
    while (fq_pk := pop_next_fetch()) is not None:
        hand_off_fetch(fq_pk)
        handed_off += 1
    return handed_off
