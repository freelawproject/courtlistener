"""Waiting room for RECAP Fetch API requests.

Requests made through the Fetch API wait here, in Redis, until the scheduler
daemon hands them to Celery. Only the PK of each PacerFetchQueue row is kept
here; PostgreSQL remains the source of truth for the request itself.

Each court has its own clock, because each court has its own PACER server, so
that we never send it requests faster than its rate allows.

Within a court, each user has their own line and users take turns. The next
request always belongs to the user who has waited longest since their last
turn, so one user's large batch cannot hold up another user's single request.

    recap_fetch:courts                  SET of courts with requests waiting
    recap_fetch:{court}:users           ZSET of users with requests waiting,
                                        scored by the time of their last turn
    recap_fetch:{court}:user:{user_id}  LIST of that user's request PKs, FIFO
    recap_fetch:{court}:next            Earliest time the court may be sent
                                        its next request, in milliseconds
    recap_fetch:rates                   HASH of court ID to rate, for the
                                        courts that don't use the default rate
"""

import time

from django.conf import settings

from cl.lib.ratelimiter import parse_rate
from cl.lib.redis_utils import get_redis_interface
from cl.recap.models import PacerFetchQueue
from cl.recap.tasks import do_pacer_fetch
from cl.recap.utils import get_court_id_from_fetch_queue

# Waffle switch that sends new Fetch API requests through this waiting room.
# While it is off, requests go straight to Celery as they did before.
SCHEDULER_SWITCH = "recap-fetch-scheduler"

KEY_PREFIX = "recap_fetch"

# Atomically take the next request for a court, if the court is ready for one.
# This has to be a script because it reads the court's clock, decides, and
# then writes. Done as separate commands, two processes could both read the
# clock before either one moved it forward, and both would send a request.
#
# KEYS: the court's users ZSET, the court's next key, the courts SET
# ARGV: now (ms), the court's next allowed time if a request is taken (ms),
#       the court ID, the prefix of the court's per-user LIST keys
POP_NEXT_SCRIPT = """
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
redis.call('SET', KEYS[2], ARGV[2])
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

    Taking a request starts the court's interval: nothing else can be taken
    for that court until the interval has passed.

    The caller MUST hand the returned request to Celery: it has left the line,
    and nothing else will run it.

    Safe to call from any number of processes at once: between them they get
    at most one request per court per interval.

    :param court_id: The court to take a request from.
    :param now_ms: The current time in milliseconds. Only tests should set it.
    :return: The PK of the PacerFetchQueue row, or None if nothing is waiting
    or the court is still inside its interval.
    """
    now_ms = _now_ms() if now_ms is None else now_ms
    r = get_redis_interface("CACHE")
    fq_pk = r.eval(
        POP_NEXT_SCRIPT,
        3,
        _users_key(court_id),
        _next_key(court_id),
        _courts_key(),
        now_ms,
        now_ms + get_court_interval_ms(court_id),
        court_id,
        _user_list_prefix(court_id),
    )
    return int(str(fq_pk)) if fq_pk else None


def get_courts_with_waiting_fetches() -> list[str]:
    """List the courts that may have requests waiting.

    A court can linger here briefly after its last request leaves; it is
    dropped the next time pop_next_fetch finds nobody waiting there.

    :return: The court IDs, in no particular order.
    """
    r = get_redis_interface("CACHE")
    return [str(court_id) for court_id in r.smembers(_courts_key())]


def schedule_fetch(fq: PacerFetchQueue) -> None:
    """Put a new request in the line for its court.

    :param fq: The PacerFetchQueue row, already saved with status ENQUEUED.
    """
    enqueue_fetch(get_court_id_from_fetch_queue(fq), fq.user_id, fq.pk)


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
    """Hand off at most one request per court, for each court that is ready.

    :return: The number of requests handed off.
    """
    handed_off = 0
    for court_id in get_courts_with_waiting_fetches():
        if (fq_pk := pop_next_fetch(court_id)) is not None:
            hand_off_fetch(fq_pk)
            handed_off += 1
    return handed_off
