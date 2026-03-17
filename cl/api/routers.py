"""
Cycle through all of our read databases for API requests.

This code borrows from the https://github.com/jbalogh/django-multidb-router/
package, but instead of using that whole package, we just create a little tool
for cycling over read databases defined in API_READ_DATABASES.

``ReplicaRouter`` is a Django DATABASE_ROUTER that checks a ``ContextVar``
set by the ``ReplicaRoutingMiddleware``.  When the var is truthy, all reads are
directed to a replica; writes always fall through to the default database.
"""

import itertools
import random
from contextvars import ContextVar, Token

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


# ---------------------------------------------------------------------------
# ContextVar helpers — used by ReplicaRoutingMiddleware
# ---------------------------------------------------------------------------

_use_replica: ContextVar[bool] = ContextVar("_use_replica", default=False)


def set_replica_routing(enabled: bool) -> Token[bool]:
    """Set whether the current context should route reads to a replica.

    Returns a token that can be used to reset the context var.
    """
    return _use_replica.set(enabled)


def reset_replica_routing(token: Token[bool]) -> None:
    """Reset the replica routing context var."""
    _use_replica.reset(token)


# ---------------------------------------------------------------------------
# Django database router
# ---------------------------------------------------------------------------


class ReplicaRouter:
    """Direct reads to a replica when ``ReplicaRoutingMiddleware`` opts in.

    Activation is controlled per-request by the middleware, which sets a
    ``ContextVar`` when the request qualifies for replica routing.
    """

    def db_for_read(self, model, **hints) -> str | None:
        if _use_replica.get(False):
            return get_api_read_db()
        return None

    def db_for_write(self, model, **hints) -> str | None:
        return None

    def allow_relation(self, obj1, obj2, **hints) -> bool | None:
        return True

    def allow_migrate(
        self, db, app_label, model_name=None, **hints
    ) -> bool | None:
        return None
