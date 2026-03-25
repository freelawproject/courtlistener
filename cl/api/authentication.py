from contextvars import Token

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.http import HttpRequest
from rest_framework.authentication import (
    BasicAuthentication,
    SessionAuthentication,
    TokenAuthentication,
)
from rest_framework.request import Request
from waffle import flag_is_active

from cl.api.routers import (
    SAFE_METHODS,
    is_replica_configured,
    set_replica_routing,
)


def _activate_replica_routing(
    request: Request,
    user: AbstractBaseUser | AnonymousUser | None = None,
) -> None:
    """
    Enables replica routing for eligible requests.

    This helper evaluates whether the current request should be routed to
    a read replica. It is intended to be called *after* DRF authentication,
    when the effective user is known, so per-user feature flag targeting
    behaves correctly.

    If enabled, the resulting ContextVar token is stored on the underlying
    Django request object so that middleware can reset it after the response.

    :param request: The DRF request instance.
    :param user: The authenticated user resolved by DRF. Must be passed
        explicitly because ``request.user`` is not yet assigned when
        ``authenticate()`` returns.
    """
    django_request: HttpRequest = request._request

    if django_request.method not in SAFE_METHODS:
        return
    if not is_replica_configured():
        return

    # Temporarily override the request user so waffle flag evaluation
    # can use the authenticated user for targeting.
    original_user = getattr(django_request, "user", None)
    if user is not None and user.is_authenticated:
        django_request.user = user  # type: ignore[assignment]

    try:
        if not flag_is_active(django_request, "replica-reads"):
            return
    finally:
        # Always restore the original user to avoid side effects.
        django_request.user = original_user  # type: ignore[assignment]

    # Enable replica routing via ContextVar and store the token so it
    # can be reset later
    token: Token[bool] = set_replica_routing(True)
    django_request._replica_routing_token = token  # type: ignore[attr-defined]


class ReplicaRoutingBasicAuthentication(BasicAuthentication):
    """BasicAuthentication that activates replica routing after auth."""

    def authenticate(self, request: Request):
        result = super().authenticate(request)
        if result is not None:
            _activate_replica_routing(request, result[0])
        return result


class ReplicaRoutingTokenAuthentication(TokenAuthentication):
    """TokenAuthentication that activates replica routing after auth."""

    def authenticate(self, request: Request):
        result = super().authenticate(request)
        if result is not None:
            _activate_replica_routing(request, result[0])
        return result


class ReplicaRoutingSessionAuthentication(SessionAuthentication):
    """SessionAuthentication that activates replica routing after auth.

    This MUST be the last class in DEFAULT_AUTHENTICATION_CLASSES.
    Calls the helper unconditionally so anonymous users (where all
    auth classes return None) also get replica routing.
    """

    def authenticate(self, request: Request):
        result = super().authenticate(request)
        _activate_replica_routing(
            request, result[0] if result is not None else None
        )
        return result
