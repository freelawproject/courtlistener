from collections.abc import Awaitable

from asgiref.sync import iscoroutinefunction
from django.http import HttpRequest, HttpResponseBase
from waffle import flag_is_active

from cl.api.routers import (
    SAFE_METHODS,
    is_replica_configured,
    reset_replica_routing,
    set_replica_routing,
)


class ReplicaRoutingMiddleware:
    """Route API read requests to a database replica.

    Uses a Waffle Flag (``replica-reads``) for percentage-based rollout
    and per-user targeting.
    Only affects requests to ``/api/rest/`` endpoints with safe HTTP methods.

    Supports both sync (WSGI) and async (ASGI) modes.
    """

    sync_capable = True
    async_capable = True

    def __init__(self, get_response) -> None:
        self.get_response = get_response
        self.async_mode = iscoroutinefunction(self.get_response)

    def _reset_auth_replica_token(self, request: HttpRequest) -> None:
        """Disable replica routing enabled by DRF auth classes."""
        if getattr(request, "_replica_routing_token", None) is not None:
            set_replica_routing(False)

    def __call__(
        self, request: HttpRequest
    ) -> HttpResponseBase | Awaitable[HttpResponseBase]:
        if self.async_mode:
            return self.__acall__(request)
        if self._should_route_to_replica(request):
            token = set_replica_routing(True)
            try:
                return self.get_response(request)
            finally:
                reset_replica_routing(token)

        try:
            return self.get_response(request)
        finally:
            self._reset_auth_replica_token(request)

    async def __acall__(self, request: HttpRequest) -> HttpResponseBase:
        if self._should_route_to_replica(request):
            token = set_replica_routing(True)
            try:
                return await self.get_response(request)
            finally:
                reset_replica_routing(token)

        try:
            return await self.get_response(request)
        finally:
            self._reset_auth_replica_token(request)

    def _should_route_to_replica(self, request: HttpRequest) -> bool:
        if request.method not in SAFE_METHODS:
            return False
        if not request.path.startswith("/api/rest/"):
            return False
        if not is_replica_configured():
            return False
        return bool(flag_is_active(request, "replica-reads"))
