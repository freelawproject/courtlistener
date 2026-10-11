"""Waiting room for RECAP Fetch API requests.

Requests made through the Fetch API wait here, in Redis, until the scheduler
daemon hands them to Celery. Only the PK of each PacerFetchQueue row is kept
here; PostgreSQL remains the source of truth for the request itself.

Each court has its own clock, because each court has its own PACER server, so
that we never send it requests faster than its rate allows. The clock counts
from when a request starts running, not from when it is handed to Celery, and
a court never has more than one request handed off but not yet started.
Otherwise requests that pile up in Celery while workers are busy would all
start together once the workers free up.

Within a court, each user has their own line and users take turns. The next
request always belongs to the user who has waited longest since their last
turn, so one user's large batch cannot hold up another user's single request.

    recap_fetch:courts                  SET of courts with requests waiting
    recap_fetch:{court}:users           ZSET of users with requests waiting,
                                        scored by the time of their last turn
    recap_fetch:{court}:user:{user_id}  LIST of that user's request PKs, FIFO
    recap_fetch:{court}:pending         PK handed to Celery that has not
                                        started yet
    recap_fetch:{court}:next            Earliest time the court may be sent
                                        its next request, in milliseconds
    recap_fetch:rates                   HASH of court ID to rate, for the
                                        courts that don't use the default rate
"""

import time

from django.conf import settings

from cl.lib.ratelimiter import parse_rate
from cl.lib.redis_utils import get_redis_interface, release_redis_lock
from cl.recap.models import PROCESSING_STATUS, PacerFetchQueue
from cl.recap.tasks import do_pacer_fetch
from cl.recap.utils import get_court_id_from_fetch_queue

# Waffle switch that sends new Fetch API requests through this waiting room.
# While it is off, requests go straight to Celery as they did before.
SCHEDULER_SWITCH = "recap-fetch-scheduler"

KEY_PREFIX = "recap_fetch"

# How long a court waits for a handed-off request to start before it gives up
# and allows the next one. Without this, a request lost between Redis and
# Celery would block its court forever.
PENDING_TTL_SECONDS = 5 * 60

# Atomically take the next request for a court, if the court is ready for one.
# This has to be a script because it reads the court's clock, decides, and
# then writes. Done as separate commands, two processes could both read the
# clock before either one moved it forward, and both would send a request.
#
# KEYS: the court's users ZSET, the court's next key, the courts SET, the
#       court's pending key
# ARGV: now (ms), how long the pending marker lives (s), the court ID, the
#       prefix of the court's per-user LIST keys
POP_NEXT_SCRIPT = """
if redis.call('EXISTS', KEYS[4]) == 1 then
    return false
end
if tonumber(ARGV[1]) < tonumber(redis.call('GET', KEYS[2]) or '0') then
    return false
end
local user = redis.call('ZRANGE', KEYS[1], 0, 0)[1]
if not user then
    redis.call('SREM', KEYS[3], ARGV[3])
    return false
end
local user_list = ARGV[4] .. user
local pk = redis.call('LPOP', user_list)
if not pk then
    redis.call('ZREM', KEYS[1], user)
    return false
end
if redis.call('LLEN', user_list) > 0 then
    redis.call('ZADD', KEYS[1], ARGV[1], user)
else
    redis.call('ZREM', KEYS[1], user)
end
redis.call('SET', KEYS[4], pk, 'EX', tonumber(ARGV[2]))
return pk
"""


def _now_ms() -> int:
    """Return the current time in milliseconds."""
    return int(time.time() * 1000)


def _courts_key() -> str:
    """Return the key of the SET of courts with requests waiting."""
    return f"{KEY_PREFIX}:courts"


def _users_key(court_id: str) -> str:
    """Return the key of the ZSET of users waiting in a court."""
    return f"{KEY_PREFIX}:{court_id}:users"


def _user_list_prefix(court_id: str) -> str:
    """Return the prefix shared by every per-user LIST key in a court."""
    return f"{KEY_PREFIX}:{court_id}:user:"


def _user_list_key(court_id: str, user_id: int) -> str:
    """Return the key of the LIST of one user's waiting requests in a court."""
    return f"{_user_list_prefix(court_id)}{user_id}"


def _pending_key(court_id: str) -> str:
    """Return the key holding the court's handed-off, not yet started PK."""
    return f"{KEY_PREFIX}:{court_id}:pending"


def _next_key(court_id: str) -> str:
    """Return the key holding when a court may next be sent a request."""
    return f"{KEY_PREFIX}:{court_id}:next"


def _rates_key() -> str:
    """Return the key of the HASH of per-court rate overrides."""
    return f"{KEY_PREFIX}:rates"


def get_court_interval_ms(court_id: str) -> int:
    """Get the minimum time between two requests to a court.

    :param court_id: The court to look up.
    :return: The interval in milliseconds, from the court's own rate if it has
    one, otherwise from settings.RECAP_FETCH_DEFAULT_COURT_RATE.
    """
    r = get_redis_interface("CACHE")
    rate = r.hget(_rates_key(), court_id)
    num_requests, duration = parse_rate(
        str(rate) if rate else settings.RECAP_FETCH_DEFAULT_COURT_RATE
    )
    return duration * 1000 // num_requests


def set_court_rate(court_id: str, rate: str | None) -> None:
    """Change how fast we send requests to a court.

    Takes effect on the next request taken for the court, including requests
    that were already waiting. No deploy or restart is needed.

    :param court_id: The court to change.
    :param rate: A rate like "1/2s" or "30/m", as understood by parse_rate.
    None removes the court's own rate, returning it to the default.
    :raises ValueError, KeyError: If the rate cannot be parsed.
    """
    r = get_redis_interface("CACHE")
    if rate is None:
        r.hdel(_rates_key(), court_id)
        return
    # Reject a bad rate here, rather than every time the court is scheduled.
    parse_rate(rate)
    r.hset(_rates_key(), court_id, rate)


def enqueue_fetch(
    court_id: str, user_id: int, fq_pk: int, now_ms: int | None = None
) -> None:
    """Put a request at the back of its user's line in a court.

    A user with nothing else waiting in the court joins behind the users who
    are already waiting there. A user who is already waiting keeps their place.

    :param court_id: The court the request will be sent to.
    :param user_id: The user who made the request.
    :param fq_pk: The PK of the PacerFetchQueue row to schedule.
    :param now_ms: The current time in milliseconds. Only tests should set it.
    """
    now_ms = _now_ms() if now_ms is None else now_ms
    r = get_redis_interface("CACHE")
    # None of these commands depends on a value read beforehand, so a
    # MULTI/EXEC transaction is enough to apply them as one step.
    pipe = r.pipeline()
    pipe.rpush(_user_list_key(court_id, user_id), fq_pk)
    pipe.zadd(_users_key(court_id), {str(user_id): now_ms}, nx=True)
    pipe.sadd(_courts_key(), court_id)
    pipe.execute()


def pop_next_fetch(court_id: str, now_ms: int | None = None) -> int | None:
    """Take the next request for a court, if the court is ready for one.

    The request comes from the user who has waited longest since their last
    turn in the court, and is that user's oldest one.

    The caller MUST hand the returned request to Celery: it has left the line,
    and nothing else will run it. The court then accepts no other request
    until this one starts (see mark_fetch_started) and its interval passes,
    or until PENDING_TTL_SECONDS pass.

    Safe to call from any number of processes at once: between them they get
    at most one request per court.

    :param court_id: The court to take a request from.
    :param now_ms: The current time in milliseconds. Only tests should set it.
    :return: The PK of the PacerFetchQueue row, or None if nothing is waiting,
    the court's previous request has not started, or the court is still
    inside its interval.
    """
    now_ms = _now_ms() if now_ms is None else now_ms
    r = get_redis_interface("CACHE")
    fq_pk = r.eval(
        POP_NEXT_SCRIPT,
        4,
        _users_key(court_id),
        _next_key(court_id),
        _courts_key(),
        _pending_key(court_id),
        now_ms,
        PENDING_TTL_SECONDS,
        court_id,
        _user_list_prefix(court_id),
    )
    return int(str(fq_pk)) if fq_pk else None


def get_pending_fetch(court_id: str) -> int | None:
    """Get the request a court has handed to Celery that has not started.

    :param court_id: The court to look up.
    :return: The PK of the PacerFetchQueue row, or None if there is none.
    """
    fq_pk = get_redis_interface("CACHE").get(_pending_key(court_id))
    return int(str(fq_pk)) if fq_pk else None


def mark_fetch_started(
    court_id: str, fq_pk: int, now_ms: int | None = None
) -> None:
    """Record that a court's handed-off request has started running.

    The court's interval is counted from this moment.

    :param court_id: The court the request was sent to.
    :param fq_pk: The PK of the PacerFetchQueue row that started.
    :param now_ms: The current time in milliseconds. Only tests should set it.
    """
    now_ms = _now_ms() if now_ms is None else now_ms
    r = get_redis_interface("CACHE")
    # Order matters: set the next allowed time before releasing the court, so
    # there is never a moment when the court looks free and unthrottled.
    r.set(_next_key(court_id), now_ms + get_court_interval_ms(court_id))
    # Only clear the marker if it still names this request, so a slow caller
    # cannot release a newer request's hold on the court.
    release_redis_lock(r, _pending_key(court_id), str(fq_pk))


def clear_pending_fetch(court_id: str, fq_pk: int) -> None:
    """Free a court whose taken request will not be handed to Celery.

    Unlike mark_fetch_started, this does not start the court's interval,
    because nothing was sent to PACER.

    :param court_id: The court the request was taken from.
    :param fq_pk: The PK of the PacerFetchQueue row that was taken.
    """
    r = get_redis_interface("CACHE")
    release_redis_lock(r, _pending_key(court_id), str(fq_pk))


def get_courts_with_waiting_fetches() -> list[str]:
    """List the courts that may have requests waiting.

    A court can linger here briefly after its last request leaves; it is
    dropped the next time pop_next_fetch finds nobody waiting there.

    :return: The court IDs, in no particular order.
    """
    r = get_redis_interface("CACHE")
    return [str(court_id) for court_id in r.smembers(_courts_key())]


def schedule_fetch(fq: PacerFetchQueue) -> float:
    """Put a new request in line and tell its user how long the wait may be.

    The explanation of the estimate is saved to the request's message, where
    the API returns it.

    :param fq: The PacerFetchQueue row, already saved with status ENQUEUED.
    :return: The estimated wait in seconds. See estimate_delay for what the
    number does and does not promise.
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

    :param court_id: The court the request was taken from.
    :param fq_pk: The PK returned by pop_next_fetch.
    :return: True if the request was sent to Celery.
    """
    fq = PacerFetchQueue.objects.filter(
        pk=fq_pk, status=PROCESSING_STATUS.ENQUEUED
    ).first()
    if fq is None:
        # Deleted or already finished while it waited: nothing to run.
        clear_pending_fetch(court_id, fq_pk)
        return False
    do_pacer_fetch(fq)
    return True


def run_dispatch_cycle() -> int:
    """Hand off at most one request per court, for each court that is ready.

    A court is ready when its previous request has started and its interval
    has passed since then. "Started" is read from PostgreSQL: the fetch tasks
    move the row out of ENQUEUED as their first step.

    Safe to run from several processes at once.

    :return: The number of requests handed off.
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


def estimate_delay(
    court_id: str, user_id: int, now_ms: int | None = None
) -> float:
    """Estimate how long a user's newest request will wait before it starts.

    Call it right after enqueue_fetch for the same court and user.

    This is an estimate of when we begin the request to PACER, not of when it
    completes, and it is not a promise. It assumes every other waiting user
    takes each turn they are entitled to before this request's own turn comes,
    which is the worst case for the users waiting now. It will be too low if
    more users join the court's queue afterwards, if the court's rate is
    lowered, or if Celery workers are too busy to start requests promptly.

    :param court_id: The court the request will be sent to.
    :param user_id: The user who made the request.
    :param now_ms: The current time in milliseconds. Only tests should set it.
    :return: The estimated wait in seconds.
    """
    now_ms = _now_ms() if now_ms is None else now_ms
    r = get_redis_interface("CACHE")
    other_users = [
        str(user)
        for user in r.zrange(_users_key(court_id), 0, -1)
        if str(user) != str(user_id)
    ]
    pipe = r.pipeline()
    pipe.llen(_user_list_key(court_id, user_id))
    pipe.get(_next_key(court_id))
    for user in other_users:
        pipe.llen(f"{_user_list_prefix(court_id)}{user}")
    own_depth, next_ms, *other_depths = pipe.execute()

    # Users take turns, so before this user's Nth request starts, each other
    # user gets at most N turns, and fewer if they have fewer requests waiting.
    turns_ahead = max(own_depth - 1, 0) + sum(
        min(depth, own_depth) for depth in other_depths
    )
    until_court_is_free = max(int(next_ms or 0) - now_ms, 0)
    delay_ms = until_court_is_free + turns_ahead * get_court_interval_ms(
        court_id
    )
    return delay_ms / 1000
