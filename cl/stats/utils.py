from collections import OrderedDict

import redis
import requests
from django.conf import settings
from django.db import OperationalError, connections
from django.db.models import F
from django.utils.timezone import now

from cl.lib.db_tools import fetchall_as_dict
from cl.lib.redis_utils import make_redis_interface
from cl.stats.models import Stat

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


def tally_stat(name, inc=1, date_logged=None):
    """Tally an event's occurrence to the database.

    Will assume the following overridable values:
       - the event happened today.
       - the event happened once.
    """
    if date_logged is None:
        date_logged = now()
    stat, created = Stat.objects.get_or_create(
        name=name, date_logged=date_logged, defaults={"count": inc}
    )
    if created:
        return stat.count
    else:
        count_cache = stat.count
        stat.count = F("count") + inc
        stat.save()
        # stat doesn't have the new value when it's updated with a F object, so
        # we fake the return value instead of looking it up again for the user.
        return count_cache + inc


def check_redis() -> bool:
    r = make_redis_interface("STATS")
    try:
        r.ping()
    except (redis.exceptions.ConnectionError, ConnectionRefusedError):
        return False
    return True


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


def check_solr() -> bool:
    """Check if we can connect to Solr"""
    s = requests.Session()
    for domain in {settings.SOLR_HOST, settings.SOLR_RECAP_HOST}:
        try:
            s.get(f"{domain}/solr/admin/ping?wt=json", timeout=2)
        except ConnectionError:
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
