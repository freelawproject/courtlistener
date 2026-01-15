from collections import OrderedDict
from datetime import datetime, timedelta

import redis
from django.db import OperationalError, connections
from django.utils.timezone import now
from elasticsearch.dsl import connections as es_connections
from elasticsearch.exceptions import (
    ConnectionError,
    ConnectionTimeout,
    RequestError,
)
from waffle import switch_is_active

from cl.lib.db_tools import fetchall_as_dict
from cl.lib.redis_utils import get_redis_interface
from cl.stats.metrics import record_prometheus_metric

MILESTONES = OrderedDict(
    (
        ("XXS", [1e0, 5e0]),  # 1 - 5
        ("XS", [1e1, 2.5e1, 5e1, 1e2, 2.5e2, 5e2]),  # 10 - 500
        ("SM", [1e3, 2.5e3, 5e3, 1e4, 2.5e4, 5e4]),  # 1_000 - 50_000
        ("MD", [1e5, 2.5e5, 5e5]),  # 100_000 - 500_000
        ("LG", [1e6, 2.5e6, 5e6]),  # 1M - 5M
        ("XL", [1e7, 2.5e7, 5e7]),  # 10M - 50M
        ("XXL", [1e8, 2.5e8, 5e8]),  # 100M - 500M
        ("XXXL", [1e9, 2.5e9, 5e9]),  # 1B - 5B
    )
)

MILESTONES_FLAT = sorted(
    item for sublist in MILESTONES.values() for item in sublist
)


def get_milestone_range(start, end):
    """Return the flattened MILESTONES by range of their keys.

    >>> get_milestone_range('MD', 'LG')
    [1e5, 2.5e5, 5e5, 1e6, 2.5e6, 5e6]
    """
    out = []
    extending = False
    for key, values in MILESTONES.items():
        if key == start:
            extending = True
        if extending is True:
            out.extend(values)
            if key == end:
                break
    return out


def _update_cached_stat(key, inc, date_logged):
    r = get_redis_interface("STATS")

    # Compute expiration:
    # Keys live for 10 full days after the date they represent. For example,
    # a key for June 1 will expire at June 12 at 00:00:00.
    midnight_today = datetime.combine(
        date_logged, datetime.min.time(), tzinfo=now().tzinfo
    )
    expire_at_date = midnight_today + timedelta(days=11)

    # Convert to seconds-from-now for Redis EXPIRE
    ttl_seconds = int((expire_at_date - now()).total_seconds())

    # Increment and apply expiration atomically
    pipe = r.pipeline()
    pipe.incrby(key, inc)
    pipe.expire(key, ttl_seconds)
    value, _ = pipe.execute()

    return value


def tally_stat(
    name,
    inc=1,
    date_logged=None,
    prometheus_handler_key="",
) -> int:
    """Tally an event's occurrence to Redis.

    Will assume the following overridable values:
       - the event happened today.
       - the event happened once.
    """
    if not switch_is_active("increment-stats"):
        return

    current_dt = now()
    if date_logged is None:
        date_logged = current_dt.date()

    key = f"{name}.{date_logged.isoformat()}"

    if prometheus_handler_key:
        record_prometheus_metric(prometheus_handler_key, inc)

    return _update_cached_stat(key, inc, date_logged)


def check_redis() -> bool:
    r = get_redis_interface("STATS")
    try:
        r.ping()
    except (redis.exceptions.ConnectionError, ConnectionRefusedError):
        return False
    return True


def check_elasticsearch() -> bool:
    """
    Checks the health of the connected Elasticsearch cluster.

    it retrieves the cluster health information and returns:

    * True:  if the cluster health status is "green" (healthy).
    * False: if the cluster health is not "green" or an error occurs
              during connection or health retrieval.
    """
    try:
        es = es_connections.get_connection()
        cluster_health = es.cluster.health()
    except (
        ConnectionError,
        ConnectionTimeout,
        RequestError,
    ):
        return False

    if cluster_health["status"] == "green":
        return True
    return False


def check_postgresql() -> bool:
    """Just check if we can connect to postgresql"""
    try:
        for alias in connections:
            with connections[alias].cursor() as c:
                c.execute("SELECT 1")
                c.fetchone()
    except OperationalError:
        return False
    return True


def get_replication_statuses() -> dict[str, list[dict[str, str | int]]]:
    """Return the replication status information for all publishers

    The easiest way to detect a problem in a replication set up is to monitor
    the size of the publisher's change lag. That is, how many changes are on
    the publisher that haven't been sent to the subscriber? This function will
    query all DBs set up in the config file and send their replication status
    information.

    :return: The status of all configured publications
    :rtype: A dict of server aliases point to lists of query results dicts:

    {"replica": [{
            slot_name: 'coupa',
            lsn_distance: 33239
        }, {
            slot_name: 'maverick',
            lsn_distance: 393478,
        }],
        "default": [{
            slot_name: 'replica',
            lsn_distance: 490348
        }],
    }
    """
    statuses = {}
    query = """
        SELECT
            slot_name,
            confirmed_flush_lsn,
            pg_current_wal_lsn(),
            (pg_current_wal_lsn() - confirmed_flush_lsn) AS lsn_distance
        FROM pg_replication_slots;
    """
    for alias in connections:
        with connections[alias].cursor() as cursor:
            cursor.execute(query)
            rows = fetchall_as_dict(cursor)
            if rows:
                statuses[alias] = rows
    return statuses
