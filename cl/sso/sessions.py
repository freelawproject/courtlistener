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
