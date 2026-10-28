import time

from asgiref.sync import iscoroutinefunction, sync_to_async
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import SESSION_KEY, logout
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.utils.decorators import sync_and_async_middleware

from cl.sso.events import record_auth_event
from cl.sso.models import AuthMethod, AuthOutcome
from cl.sso.policy import refusal_message, requirement_for_user, sso_start_url
from cl.sso.sessions import SSO_ORGANIZATION_KEY

# When the session's account was last checked against the SSO policy.
POLICY_CHECKED_AT_KEY = "sso_policy_checked_at"


def enforce_sso_session(request: HttpRequest) -> HttpResponse | None:
    """End sessions that the SSO policy no longer allows.

    Turning on SSO enforcement (for a domain, or for staff) mustn't leave
    people who signed in with a password still signed in. Each session is
    checked at most every SSO_POLICY_RECHECK_SECONDS, so most requests cost
    nothing beyond reading the session.

    A session is allowed if no requirement applies, or if it came from the
    IdP of the organization the requirement names.

    :param request: The current request.
    :return: A redirect to the SSO page if the session was ended, else None.
    """
    session = getattr(request, "session", None)
    if session is None or SESSION_KEY not in session:
        return None
    now = time.time()
    last_checked = session.get(POLICY_CHECKED_AT_KEY, 0)
    if now - last_checked < settings.SSO_POLICY_RECHECK_SECONDS:
        return None

    user = request.user
    if not user.is_authenticated:
        return None
    requirement = requirement_for_user(user)  # type: ignore[arg-type]
    if requirement is None or (
        session.get(SSO_ORGANIZATION_KEY) == requirement.organization.pk
    ):
        session[POLICY_CHECKED_AT_KEY] = int(now)
        return None

    record_auth_event(
        request=request,
        method=AuthMethod.PASSWORD,
        outcome=AuthOutcome.REFUSED,
        user=user,  # type: ignore[arg-type]
        detail="ended a session SSO policy no longer allows",
    )
    email = user.email  # type: ignore[union-attr]
    logout(request)
    messages.warning(request, refusal_message(requirement, email))
    return HttpResponseRedirect(
        sso_start_url(email=email, next_url=request.get_full_path())
    )


@sync_and_async_middleware
def SSOSessionMiddleware(get_response):
    """Run ``enforce_sso_session`` on every request.

    Supports both sync and async views, so it doesn't force async views
    through a thread.
    """
    if iscoroutinefunction(get_response):

        async def async_middleware(request: HttpRequest) -> HttpResponse:
            """Enforce SSO, then await the next handler."""
            response = await sync_to_async(enforce_sso_session)(request)
            return response or await get_response(request)

        return async_middleware

    def middleware(request: HttpRequest) -> HttpResponse:
        """Enforce SSO, then call the next handler."""
        return enforce_sso_session(request) or get_response(request)

    return middleware
