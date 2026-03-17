"""
Cycle through all of our read databases for API requests.

This code borrows from the https://github.com/jbalogh/django-multidb-router/
package, but instead of using that whole package, we just create a little tool
for cycling over read databases defined in API_READ_DATABASES.

The big difference here is that we can implement this *without* doing a router
that affects queries across the entire system. That means we don't have to
think about pinning users to specific databases, we don't have to think about
replication lag, and we can just apply this with the `using` argument wherever
we want. Much simpler, though perhaps less elegant.
"""

import itertools
import random

from django.conf import settings

replicas = None


def _get_replica_list():
    global replicas
    if replicas is not None:
        return replicas

    dbs = settings.API_READ_DATABASES
    if isinstance(dbs, str):
        dbs = [dbs]

    # Filter out any aliases not actually configured in DATABASES.
    dbs = [db for db in dbs if db in settings.DATABASES]
    if not dbs:
        dbs = ["default"]

    # Shuffle the list so the first database isn't slammed during startup.
    random.shuffle(dbs)

    replicas = itertools.cycle(dbs)
    return replicas


def get_api_read_db() -> str:
    """Return the alias of a read database.

    Falls back to ``"default"`` when no replicas are configured.
    """
    return next(_get_replica_list())
