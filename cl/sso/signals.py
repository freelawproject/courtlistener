from datetime import timedelta
from typing import Any

from allauth.account.signals import user_logged_in as allauth_user_logged_in
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.http import HttpRequest
from django.utils import timezone

from cl.sso.events import record_auth_event
from cl.sso.linking import SSO_LOGIN_ATTR, SSOLoginResult, send_linked_email
from cl.sso.models import AuthMethod, AuthOutcome, OrganizationMembership
from cl.sso.sessions import mark_sso_session
from cl.sso.throttles import sync_user_throttles


@receiver(allauth_user_logged_in, dispatch_uid="sso_logged_in")
def handle_sso_login(
    sender: Any, request: HttpRequest, user: User, **kwargs: Any
) -> None:
    """Finish an SSO login: mark the session, shorten it, and log it.

    :param sender: The signal sender.
    :param request: The request the login happened in.
    :param user: Who signed in.
    """
    result: SSOLoginResult | None = getattr(request, SSO_LOGIN_ATTR, None)
    if result is None or "sociallogin" not in kwargs:
        return
    organization = result.connection.organization
    mark_sso_session(request, organization.pk)
    # Shorter than a password session, so somebody who has left their
    # organization loses access soon after their IdP account is disabled.
    # A fixed end time; a number of seconds would restart on every save.
    request.session.set_expiry(
        timezone.now() + timedelta(seconds=organization.session_max_age)
    )
    record_auth_event(
        request=request,
        method=AuthMethod.SSO,
        outcome=AuthOutcome.SUCCESS,
        user=user,
        connection=result.connection,
    )
    if result.newly_linked:
        send_linked_email(user, result.connection)


@receiver(user_logged_in, dispatch_uid="sso_audit_password_login")
def audit_password_login(
    sender: Any, request: HttpRequest | None, user: User, **kwargs: Any
) -> None:
    """Log successful password sign-ins.

    SSO logins also pass through Django's login(); those are logged by
    ``handle_sso_login`` instead.

    :param sender: The signal sender.
    :param request: The request the login happened in.
    :param user: Who signed in.
    """
    if request is not None and hasattr(request, SSO_LOGIN_ATTR):
        return
    record_auth_event(
        request=request,
        method=AuthMethod.PASSWORD,
        outcome=AuthOutcome.SUCCESS,
        user=user,
    )


@receiver(user_login_failed, dispatch_uid="sso_audit_failed_login")
def audit_failed_login(
    sender: Any,
    credentials: dict[str, Any],
    request: HttpRequest | None = None,
    **kwargs: Any,
) -> None:
    """Log failed password checks, from the sign-in page or HTTP Basic.

    Only a hash of the submitted identifier is stored. Looking the account
    up here would cost every failed attempt an extra query.

    :param sender: The signal sender.
    :param credentials: What was submitted, with the password masked.
    :param request: The request, if there is one.
    """
    auth_header = request.META.get("HTTP_AUTHORIZATION", "") if request else ""
    method = (
        AuthMethod.BASIC_AUTH
        if auth_header.lower().startswith("basic ")
        else AuthMethod.PASSWORD
    )
    record_auth_event(
        request=request,
        method=method,
        outcome=AuthOutcome.FAILURE,
        identifier=str(credentials.get("username", "")),
    )


@receiver(
    post_delete,
    sender=OrganizationMembership,
    dispatch_uid="sso_membership_removed",
)
def handle_membership_removed(
    sender: type[OrganizationMembership],
    instance: OrganizationMembership,
    **kwargs: Any,
) -> None:
    """Take away organization API rates when somebody leaves.

    :param sender: The model class.
    :param instance: The membership that was deleted.
    """
    # When the whole account is being deleted there's nothing to sync.
    if not User.objects.filter(pk=instance.user_id).exists():
        return
    sync_user_throttles(instance.user)
