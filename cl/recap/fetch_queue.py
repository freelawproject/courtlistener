"""Redis waiting room for RECAP Fetch API requests.

Requests made through the Fetch API wait here until the scheduler daemon
hands them to Celery. Only the PK of each PacerFetchQueue row is kept here;
PostgreSQL remains the source of truth for the request itself. The daemon and
the API live in cl.recap.fetch_scheduler; this module only deals with Redis,
so the fetch tasks can import it without a circular import.

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

import logging
import time
from dataclasses import dataclass

from django.conf import settings
from redis.exceptions import RedisError

from cl.lib.ratelimiter import parse_rate
from cl.lib.redis_utils import get_redis_interface, release_redis_lock

logger = logging.getLogger(__name__)

KEY_PREFIX = "recap_fetch"

# How long a court waits for a handed-off request to start before it gives up
# and allows the next one. Without this, a request lost between Redis and
# Celery would block its court forever.
PENDING_TTL_SECONDS = 5 * 60

# How long a court's next key outlives its interval. The key only needs to
# exist until the interval ends; the margin keeps clock drift between servers
# from expiring it early.
NEXT_KEY_GRACE_MS = 60 * 1000

# The daemon renews its heartbeat every cycle, about twice a second. If it
# goes this long without one, we assume it is down and stop queueing.
HEARTBEAT_TTL_SECONDS = 30

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

# Start a court's interval and release it, but only if the request that
# started is the one the court is waiting on. Requests that didn't come
# through the queue, or that the court already gave up on, change nothing.
# The next key expires a little after the interval ends, so idle courts leave
# nothing behind. Only its value decides when the court is ready.
#
# KEYS: the court's pending key, the court's next key
# ARGV: the PK that started, the time the court may be sent its next request
#       (ms), how long the next key lives (ms)
START_SCRIPT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call('SET', KEYS[2], ARGV[2], 'PX', ARGV[3])
redis.call('DEL', KEYS[1])
return 1
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


def _user_list_key(court_id: str, user_id: int | str) -> str:
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


def _heartbeat_key() -> str:
    """Return the key the scheduler daemon keeps alive while it runs."""
    return f"{KEY_PREFIX}:daemon_heartbeat"


def touch_daemon_heartbeat() -> None:
    """Record that the scheduler daemon is running.

    The daemon calls this on every cycle. The key expires on its own, so a
    daemon that dies or hangs stops counting as alive after
    HEARTBEAT_TTL_SECONDS.
    """
    get_redis_interface("CACHE").set(
        _heartbeat_key(), 1, ex=HEARTBEAT_TTL_SECONDS
    )


def daemon_is_alive() -> bool:
    """Check whether the scheduler daemon has run recently.

    Nothing but the daemon hands queued requests to Celery, so new requests
    must not be queued while it is down.

    Returns:
        True if the daemon renewed its heartbeat in the last
        HEARTBEAT_TTL_SECONDS.
    """
    return bool(get_redis_interface("CACHE").exists(_heartbeat_key()))


def get_court_interval_ms(court_id: str) -> int:
    """Get the minimum time between two requests to a court.

    Args:
        court_id: The court to look up.

    Returns:
        The interval in milliseconds, from the court's own rate if it has
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

    Args:
        court_id: The court to change.
        rate: A rate like "1/2s" or "30/m", as understood by parse_rate.
            None removes the court's own rate, returning it to the default.

    Raises:
        ValueError, KeyError: If the rate cannot be parsed or allows no
            requests at all.
    """
    r = get_redis_interface("CACHE")
    if rate is None:
        r.hdel(_rates_key(), court_id)
        return
    # Reject a bad rate here, rather than every time the court is scheduled.
    # A rate of zero would make get_court_interval_ms divide by zero.
    num_requests, duration = parse_rate(rate)
    if num_requests <= 0 or duration <= 0:
        raise ValueError(f"The rate must allow some requests: {rate}")
    r.hset(_rates_key(), court_id, rate)


def get_court_rates() -> dict[str, str]:
    """List the courts that have their own rate.

    Returns:
        A dict of court ID to rate. Courts not in it use
        settings.RECAP_FETCH_DEFAULT_COURT_RATE.
    """
    r = get_redis_interface("CACHE")
    return {
        str(court): str(rate)
        for court, rate in r.hgetall(_rates_key()).items()
    }


@dataclass
class CourtQueueStatus:
    """A snapshot of one court's queue, for people operating it."""

    court_id: str
    # User ID to the number of requests they have waiting.
    depth_by_user: dict[int, int]
    pending_pk: int | None
    # Milliseconds until the court may be sent its next request.
    next_in_ms: int
    interval_ms: int


def get_court_queue_status(
    court_id: str, now_ms: int | None = None
) -> CourtQueueStatus:
    """Read how many requests wait in a court, and when the next one goes.

    The numbers are read with separate commands, so they can be a moment out
    of step with each other while the daemon runs.

    Args:
        court_id: The court to look at.
        now_ms: The current time in milliseconds. Only tests should set it.

    Returns:
        The court's queue status.
    """
    now_ms = _now_ms() if now_ms is None else now_ms
    r = get_redis_interface("CACHE")
    users = [str(user) for user in r.zrange(_users_key(court_id), 0, -1)]
    pipe = r.pipeline()
    pipe.get(_pending_key(court_id))
    pipe.get(_next_key(court_id))
    for user in users:
        pipe.llen(_user_list_key(court_id, user))
    pending, next_ms, *depths = pipe.execute()
    return CourtQueueStatus(
        court_id=court_id,
        depth_by_user={
            int(user): depth for user, depth in zip(users, depths) if depth
        },
        pending_pk=int(pending) if pending else None,
        next_in_ms=max(int(next_ms or 0) - now_ms, 0),
        interval_ms=get_court_interval_ms(court_id),
    )


def enqueue_fetch(
    court_id: str, user_id: int, fq_pk: int, now_ms: int | None = None
) -> None:
    """Put a request at the back of its user's line in a court.

    A user with nothing else waiting in the court joins behind the users who
    are already waiting there. A user who is already waiting keeps their place.

    Args:
        court_id: The court the request will be sent to.
        user_id: The user who made the request.
        fq_pk: The PK of the PacerFetchQueue row to schedule.
        now_ms: The current time in milliseconds. Only tests should set it.
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

    The caller must hand the returned request to Celery: it has left the
    line, and nothing else will run it. The court then accepts no other
    request until this one starts (see mark_fetch_started) and its interval
    passes, or until PENDING_TTL_SECONDS pass.

    Safe to call from any number of processes at once: between them they get
    at most one request per court.

    Args:
        court_id: The court to take a request from.
        now_ms: The current time in milliseconds. Only tests should set it.

    Returns:
        The PK of the PacerFetchQueue row, or None if nothing is waiting, the
        court's previous request has not started, or the court is still
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


def get_pending_fetches(court_ids: list[str]) -> dict[str, int]:
    """Get the requests that courts have handed to Celery and not started.

    Args:
        court_ids: The courts to look up.

    Returns:
        A dict of court ID to the PK of its handed-off PacerFetchQueue row.
        Courts with no such request are left out.
    """
    if not court_ids:
        return {}
    pipe = get_redis_interface("CACHE").pipeline(transaction=False)
    for court_id in court_ids:
        pipe.get(_pending_key(court_id))
    return {
        court_id: int(str(fq_pk))
        for court_id, fq_pk in zip(court_ids, pipe.execute())
        if fq_pk
    }


def mark_fetch_started(
    court_id: str, fq_pk: int, now_ms: int | None = None
) -> bool:
    """Record that a court's handed-off request has started running.

    The court's interval is counted from this moment. Nothing happens unless
    the court is waiting on this exact request, so it is safe to call for
    any fetch, queued or not, and more than once.

    Args:
        court_id: The court the request was sent to.
        fq_pk: The PK of the PacerFetchQueue row that started.
        now_ms: The current time in milliseconds. Only tests should set it.

    Returns:
        True if the court was waiting on this request and is now released.
    """
    now_ms = _now_ms() if now_ms is None else now_ms
    interval_ms = get_court_interval_ms(court_id)
    r = get_redis_interface("CACHE")
    started = r.eval(
        START_SCRIPT,
        2,
        _pending_key(court_id),
        _next_key(court_id),
        str(fq_pk),
        now_ms + interval_ms,
        interval_ms + NEXT_KEY_GRACE_MS,
    )
    return bool(started)


def report_fetch_started(court_id: str, fq_pk: int) -> None:
    """Tell the queue that a fetch task is about to query PACER.

    Fetch tasks call this so their court is released right away. Several of
    them run inside a database transaction, so the daemon can't see their
    status change until they finish.

    It never raises: if Redis is unreachable, the daemon still releases the
    court once it sees the task's status, or after PENDING_TTL_SECONDS.

    Args:
        court_id: The court the task is querying.
        fq_pk: The PK of the PacerFetchQueue row the task is processing.
    """
    try:
        mark_fetch_started(court_id, fq_pk)
    except RedisError:
        logger.warning(
            "Unable to tell the fetch queue that request %s started.", fq_pk
        )


def clear_pending_fetch(court_id: str, fq_pk: int) -> None:
    """Free a court whose taken request will not be handed to Celery.

    Unlike mark_fetch_started, this does not start the court's interval,
    because nothing was sent to PACER.

    Args:
        court_id: The court the request was taken from.
        fq_pk: The PK of the PacerFetchQueue row that was taken.
    """
    r = get_redis_interface("CACHE")
    release_redis_lock(r, _pending_key(court_id), str(fq_pk))


def remove_fetch(court_id: str, user_id: int, fq_pk: int) -> bool:
    """Take a waiting request out of the queue without running it.

    Args:
        court_id: The court the request is waiting in.
        user_id: The user who made the request.
        fq_pk: The PK of the PacerFetchQueue row.

    Returns:
        True if the request was still waiting and has been removed. False
        means it had already been handed off or was never queued.
    """
    r = get_redis_interface("CACHE")
    return bool(r.lrem(_user_list_key(court_id, user_id), 0, str(fq_pk)))


def get_queued_fetches(court_id: str, user_id: int) -> set[int]:
    """List a user's requests the queue still knows about in a court.

    That is the requests waiting in the user's line, plus the court's
    handed-off request if it belongs to them and has not started yet.

    Args:
        court_id: The court to look in.
        user_id: The user whose requests to list.

    Returns:
        The PKs of the PacerFetchQueue rows.
    """
    r = get_redis_interface("CACHE")
    pipe = r.pipeline()
    pipe.lrange(_user_list_key(court_id, user_id), 0, -1)
    pipe.get(_pending_key(court_id))
    waiting, pending = pipe.execute()
    # The pending PK may belong to another user. That's harmless here, since
    # callers only look up their own user's PKs in the result.
    return {int(fq_pk) for fq_pk in waiting} | (
        {int(pending)} if pending else set()
    )


def get_courts_with_waiting_fetches() -> list[str]:
    """List the courts that may have requests waiting.

    A court can linger here briefly after its last request leaves; it is
    dropped the next time pop_next_fetch finds nobody waiting there.

    Returns:
        The court IDs, in no particular order.
    """
    r = get_redis_interface("CACHE")
    return [str(court_id) for court_id in r.smembers(_courts_key())]


def estimate_delay(
    court_id: str,
    user_id: int,
    now_ms: int | None = None,
    not_yet_queued: int = 0,
) -> float:
    """Estimate how long a user's newest request will wait before it starts.

    Call it right after enqueue_fetch for the same court and user, or right
    before it with not_yet_queued=1.

    This is an estimate of when we begin the request to PACER, not of when it
    completes, and it is not a promise. It assumes every other waiting user
    takes each turn they are entitled to before this request's own turn comes,
    which is the worst case for the users waiting now. It will be too low if
    more users join the court's queue afterwards, if the court's rate is
    lowered, or if Celery workers are too busy to start requests promptly.

    Args:
        court_id: The court the request will be sent to.
        user_id: The user who made the request.
        now_ms: The current time in milliseconds. Only tests should set it.
        not_yet_queued: How many of the user's requests are about to join
            the line but are not in Redis yet.

    Returns:
        The estimated wait in seconds.
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
        pipe.llen(_user_list_key(court_id, user))
    own_depth, next_ms, *other_depths = pipe.execute()
    own_depth += not_yet_queued

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
