import time

from django.http import HttpRequest

# Session keys set when somebody signs in through SSO.
SSO_ORGANIZATION_KEY = "sso_organization_id"
SSO_AUTHENTICATED_AT_KEY = "sso_authenticated_at"


def mark_sso_session(request: HttpRequest, organization_id: int) -> None:
    """Record in the session that this login came through an IdP.

    :param request: The request the login happened in.
    :param organization_id: The organization whose IdP it was.
    """
    request.session[SSO_ORGANIZATION_KEY] = organization_id
    request.session[SSO_AUTHENTICATED_AT_KEY] = int(time.time())


def is_sso_session(request: HttpRequest) -> bool:
    """Whether the current session started with an SSO login.

    :param request: The current request.
    :return: True for SSO sessions.
    """
    return SSO_ORGANIZATION_KEY in request.session


def sso_authenticated_within(request: HttpRequest, seconds: int) -> bool:
    """Whether the person signed in through their IdP recently.

    Used in place of a password re-prompt for accounts that have no
    password.

    :param request: The current request.
    :param seconds: How recent counts.
    :return: True if the last SSO login was within that many seconds.
    """
    signed_in_at = request.session.get(SSO_AUTHENTICATED_AT_KEY)
    return bool(signed_in_at) and time.time() - signed_in_at <= seconds
