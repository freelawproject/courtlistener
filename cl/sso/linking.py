"""What happens when somebody signs in through an organization's IdP.

``resolve_sso_login`` runs before allauth logs anybody in. It finds or
creates the CourtListener account for the IdP identity, links them, and
records the person's place in the organization. Two of its rules are easy
to miss:

- A new link is only ever made to a *confirmed* account. Anybody can point
  an account at an address they don't own; only somebody who reads that
  address can confirm it. Linking to an unconfirmed account would hand an
  SSO user an account somebody else may have planted (and still holds the
  API token for), so in that case a fresh account is made and support is
  told about the duplicate.
- An account already linked to a *different* identity from the same IdP is
  never linked automatically. IdPs reuse addresses when people leave, so a
  new person with an old address must not inherit the old person's account.
"""

import logging
import re
import secrets
from dataclasses import dataclass
from typing import cast

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import mail_managers, send_mail
from django.db import transaction
from django.db.models import F
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.utils import timezone

from cl.lib.auth import filter_by_email
from cl.lib.AuthenticationBackend import accounts_for_email
from cl.sso.emails import emails
from cl.sso.events import record_auth_event
from cl.sso.models import (
    AuthMethod,
    AuthOutcome,
    MembershipRole,
    MembershipSource,
    Organization,
    OrganizationMembership,
    SSOConnection,
)
from cl.sso.policy import email_domain, sso_start_url
from cl.sso.throttles import sync_user_throttles
from cl.users.models import UserProfile
from cl.users.tasks import create_neon_account

logger = logging.getLogger(__name__)

# The request attribute that carries what happened from resolve_sso_login to
# the user_logged_in handler in cl.sso.signals.
SSO_LOGIN_ATTR = "_cl_sso_login"


@dataclass
class SSOLoginResult:
    """What ``resolve_sso_login`` decided, for the post-login handler."""

    connection: SSOConnection
    outcome: str
    newly_linked: bool = False


class SSORefusal(Exception):
    """Raised inside ``resolve_sso_login`` to stop a login.

    Caught outside the database transaction, so the audit record of the
    refusal survives the rollback of anything the login had started.
    """

    def __init__(
        self,
        reason: str,
        detail: str,
        connection: SSOConnection | None = None,
        user: User | None = None,
    ) -> None:
        """Describe the refusal.

        :param reason: A message for the person, shown on the error page.
        :param detail: A note for the audit log.
        :param connection: The connection the login came through, if known.
        :param user: The account involved, if any.
        """
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.connection = connection
        self.user = user


def refusal_response(
    request: HttpRequest, refusal: SSORefusal
) -> ImmediateHttpResponse:
    """Log a refused SSO login and build the error page that stops it.

    :param request: The current request.
    :param refusal: Why the login was refused.
    :return: An ImmediateHttpResponse for the caller to raise.
    """
    record_auth_event(
        request=request,
        method=AuthMethod.SSO,
        outcome=AuthOutcome.REFUSED,
        # The account may have been created in the rolled-back transaction.
        user=refusal.user if refusal.user and refusal.user.pk else None,
        connection=refusal.connection,
        detail=refusal.detail,
    )
    response = TemplateResponse(
        request,
        "sso/error.html",
        {"reason": refusal.reason, "private": True},
        status=403,
    )
    return ImmediateHttpResponse(response)


def get_connection(sociallogin: SocialLogin) -> SSOConnection | None:
    """Find the enabled organization connection a login came through.

    :param sociallogin: The pending login.
    :return: The connection, or None if the IdP isn't tied to an
    organization, is switched off, or shares its provider ID with another
    connection.
    """
    # allauth keys identities on (provider ID, uid), so two IdPs sharing a
    # provider ID could sign in as each other's people.
    connections = list(
        SSOConnection.objects.filter(
            social_app__provider_id=sociallogin.account.provider,
            is_enabled=True,
        ).select_related("organization", "social_app")[:2]
    )
    return connections[0] if len(connections) == 1 else None


def social_user(sociallogin: SocialLogin) -> User:
    """Return the account a pending login carries.

    allauth always fills this in before ``pre_social_login``: the linked
    account for a known identity, or an unsaved ``User`` built from the
    IdP's claims for a new one.

    :param sociallogin: The pending login.
    :return: The account.
    """
    return cast(User, sociallogin.user)


def asserted_email(sociallogin: SocialLogin) -> str:
    """Return the address the IdP vouched for, lowercased.

    allauth never copies it onto ``sociallogin.user``, because
    ACCOUNT_USER_MODEL_EMAIL_FIELD is None.

    :param sociallogin: The pending login.
    :return: The address, or "" if the IdP sent none.
    """
    if sociallogin.email_addresses:
        return sociallogin.email_addresses[0].email.strip().lower()
    return ""


def generate_username(email: str) -> str:
    """Make an unused username for an account created by SSO.

    Based on the address's local part, restricted to the characters
    registration allows, and never shaped like an address (see
    ``validate_username_is_not_an_email``).

    :param email: The person's address.
    :return: A username nobody has.
    """
    base = re.sub(r"[^A-Za-z0-9_.+-]", "", email.partition("@")[0])[:30]
    base = base or "user"
    candidate = base
    while User.objects.filter(username=candidate).exists():
        candidate = f"{base}-{secrets.randbelow(10**6):06d}"
    return candidate


def best_confirmed_account(email: str) -> tuple[User | None, int]:
    """Pick the existing account an SSO login should link to.

    The same choice sign-in makes (``EmailOrUsernameModelBackend``): most
    recently used first, among accounts that confirmed the address.

    :param email: The address the IdP vouched for.
    :return: The account (or None) and how many confirmed accounts matched.
    """
    candidates = list(
        accounts_for_email(email)
        .filter(profile__email_confirmed=True)
        .order_by(F("last_login").desc(nulls_last=True))
    )
    return (candidates[0] if candidates else None), len(candidates)


def upgrade_stub(stub: User, sociallogin: SocialLogin, email: str) -> User:
    """Turn a stub account (a donor or Neon member) into a real one.

    The same upgrade ``register`` does, without a password: the person signs
    in through their IdP.

    :param stub: The stub account holding the address.
    :param sociallogin: The pending login, for the person's name.
    :param email: The address the IdP vouched for.
    :return: The upgraded account.
    """
    stub.username = generate_username(email)
    stub.is_active = True
    person = social_user(sociallogin)
    stub.first_name = person.first_name or stub.first_name
    stub.last_name = person.last_name or stub.last_name
    stub.set_unusable_password()
    stub.save()
    profile = UserProfile.objects.get(user=stub)
    profile.stub_account = False
    profile.email_confirmed = True
    profile.save()
    return stub


def create_account(sociallogin: SocialLogin, email: str) -> User:
    """Create a confirmed account for somebody new to CourtListener.

    The IdP and the domain verification vouch for the address, so it starts
    confirmed. There is no password; the person signs in through their IdP.

    :param sociallogin: The pending login, for the person's name.
    :param email: The address the IdP vouched for.
    :return: The new account.
    """
    user = User.objects.create_user(
        generate_username(email),
        email,
        first_name=social_user(sociallogin).first_name or "",
        last_name=social_user(sociallogin).last_name or "",
    )
    user.set_unusable_password()
    user.save()
    UserProfile.objects.create(user=user, email_confirmed=True)
    return user


def flag_for_support(
    request: HttpRequest,
    connection: SSOConnection,
    user: User,
    detail: str,
) -> None:
    """Tell FLP support about an account that needs a person to look at it.

    :param request: The current request.
    :param connection: The connection the login came through.
    :param user: The account that was linked or created.
    :param detail: What support should look at.
    """
    record_auth_event(
        request=request,
        method=AuthMethod.SSO,
        outcome=AuthOutcome.FLAGGED,
        user=user,
        connection=connection,
        detail=detail,
    )
    subject = f"SSO: duplicate accounts for {user.email}"
    body = (
        f"{detail}\n\nAccount used: {user.username} (id {user.pk}), "
        f"organization: {connection.organization}.\n\nSee the duplicate "
        "accounts SOP on wiki.free.law."
    )
    # Only once the link is committed; a refused login sends nothing.
    transaction.on_commit(lambda: mail_managers(subject, body))


def find_or_create_account(
    request: HttpRequest,
    sociallogin: SocialLogin,
    connection: SSOConnection,
    email: str,
) -> tuple[User, str]:
    """Find the account a newly seen IdP identity belongs to, or make one.

    :param request: The current request.
    :param sociallogin: The pending login.
    :param connection: The connection it came through.
    :param email: The address the IdP vouched for.
    :return: The account and the ``AuthOutcome`` (LINKED or CREATED).
    :raises SSORefusal: If the account can't be linked safely.
    """
    user, confirmed_count = best_confirmed_account(email)
    if user is not None:
        already_linked = SocialAccount.objects.filter(
            user=user, provider=connection.provider_id
        ).exists()
        if already_linked:
            raise SSORefusal(
                "This address belongs to a CourtListener account that is "
                "already linked to a different person in your "
                "organization's sign-on. Please contact support@free.law.",
                "address already linked to another IdP subject",
                connection=connection,
                user=user,
            )
        if confirmed_count > 1:
            flag_for_support(
                request,
                connection,
                user,
                f"{confirmed_count} confirmed accounts share this address. "
                "SSO linked the most recently used one.",
            )
        return user, AuthOutcome.LINKED

    stub = (
        filter_by_email(User.objects.filter(profile__stub_account=True), email)
        .select_related("profile")
        .order_by("pk")
        .first()
    )
    if stub is not None:
        return upgrade_stub(stub, sociallogin, email), AuthOutcome.CREATED

    user = create_account(sociallogin, email)
    if accounts_for_email(email).exclude(pk=user.pk).exists():
        flag_for_support(
            request,
            connection,
            user,
            "Unconfirmed accounts already used this address, so SSO made a "
            "new account instead of linking one of them.",
        )
    if not settings.DEVELOPMENT:
        transaction.on_commit(lambda: create_neon_account.delay(user.pk))
    return user, AuthOutcome.CREATED


def join_organization(
    user: User, organization: Organization
) -> OrganizationMembership:
    """Record an SSO login in the person's organization membership.

    Creates the membership on the first login, gives the person a seat if
    one is free, and notifies the organization's admins and FLP when the
    seats run out.

    :param user: Who signed in.
    :param organization: The organization they signed in through.
    :return: The membership.
    """
    membership, created = OrganizationMembership.objects.get_or_create(
        organization=organization,
        user=user,
        defaults={"source": MembershipSource.SSO, "has_seat": False},
    )
    gained_seat = False
    if not membership.has_seat and organization.has_free_seat():
        membership.has_seat = True
        gained_seat = True
    membership.last_sso_login = timezone.now()
    membership.save()

    if gained_seat:
        transaction.on_commit(lambda: sync_user_throttles(user))
    elif created:
        transaction.on_commit(lambda: notify_seat_limit(user, organization))
    return membership


def notify_seat_limit(user: User, organization: Organization) -> None:
    """Tell the organization's admins and FLP that the seats ran out.

    :param user: The person who didn't get a seat.
    :param organization: Their organization.
    """
    admins = list(
        organization.memberships.filter(role=MembershipRole.ADMIN)
        .select_related("user")
        .values_list("user__email", flat=True)
    )
    email = emails["seat_limit_reached"]
    subject = email["subject"] % organization.name
    body = email["body"] % (
        user.email,
        organization.name,
        organization.seat_limit,
    )
    if admins:
        send_mail(subject, body, email["from_email"], admins)
    mail_managers(subject, body)


def _link_in_transaction(
    request: HttpRequest,
    sociallogin: SocialLogin,
    connection: SSOConnection,
    email: str,
) -> tuple[User, str]:
    """Do the database work of ``resolve_sso_login``.

    Runs inside a transaction, so a refusal raised part way through undoes
    any account it created or linked.

    :param request: The current request.
    :param sociallogin: The pending login.
    :param connection: The connection it came through.
    :param email: The address the IdP vouched for.
    :return: The account and the ``AuthOutcome``.
    :raises SSORefusal: If the login must not go ahead.
    """
    organization = connection.organization
    on_verified_domain = organization.domains.filter(
        domain=email_domain(email), verified_at__isnull=False
    ).exists()

    if sociallogin.is_existing:
        user = social_user(sociallogin)
        outcome = AuthOutcome.SUCCESS
    else:
        # A new identity may only claim an address on a domain this
        # organization has proven it controls. Otherwise any IdP could
        # assert anybody's address and take over their account.
        if not email or not on_verified_domain:
            raise SSORefusal(
                "Your sign-on returned an address that isn't on one of "
                f"{organization.name}'s verified domains, so it can't be "
                "used with CourtListener. Please contact your IT team.",
                f"unverified domain {email_domain(email)!r}",
                connection=connection,
            )
        user, outcome = find_or_create_account(
            request, sociallogin, connection, email
        )
        sociallogin.connect(request, user)

    profile = UserProfile.objects.filter(user=user).first()
    if not user.is_active or profile is None or profile.stub_account:
        raise SSORefusal(
            "This CourtListener account has been deactivated or deleted. "
            "Please contact support@free.law.",
            "inactive or stub account",
            connection=connection,
            user=user,
        )

    # The IdP vouches for the address on its organization's verified
    # domain, which is as good as clicking a confirmation link.
    if (
        not profile.email_confirmed
        and on_verified_domain
        and user.email.strip().lower() == email
    ):
        profile.email_confirmed = True
        profile.save(update_fields=["email_confirmed"])

    join_organization(user, organization)
    return user, outcome


def resolve_sso_login(request: HttpRequest, sociallogin: SocialLogin) -> None:
    """Decide which account an SSO login signs in to, and link it.

    Called from ``SocialAccountAdapter.pre_social_login``. On return,
    ``sociallogin`` is backed by a saved, linked account and allauth goes on
    to log it in. What happened is left on the request for the
    ``user_logged_in`` handler in ``cl.sso.signals``.

    :param request: The current request.
    :param sociallogin: The pending login.
    :raises ImmediateHttpResponse: To stop the login with an error page.
    """
    connection = get_connection(sociallogin)
    if connection is None:
        raise refusal_response(
            request,
            SSORefusal(
                "Single sign-on isn't set up for this organization. Please "
                "contact support@free.law.",
                "no enabled connection for provider "
                f"{sociallogin.account.provider}",
            ),
        )
    email = asserted_email(sociallogin)

    try:
        with transaction.atomic():
            user, outcome = _link_in_transaction(
                request, sociallogin, connection, email
            )
    except SSORefusal as refusal:
        raise refusal_response(request, refusal)

    if outcome != AuthOutcome.SUCCESS:
        record_auth_event(
            request=request,
            method=AuthMethod.SSO,
            outcome=outcome,
            user=user,
            connection=connection,
        )
    setattr(
        request,
        SSO_LOGIN_ATTR,
        SSOLoginResult(
            connection=connection,
            outcome=outcome,
            newly_linked=outcome == AuthOutcome.LINKED,
        ),
    )


def send_linked_email(user: User, connection: SSOConnection) -> None:
    """Tell somebody their existing account is now linked to SSO.

    :param user: The account that was linked.
    :param connection: The connection it was linked to.
    """
    email = emails["account_linked"]
    name = connection.organization.name
    send_mail(
        email["subject"] % name,
        email["body"]
        % (
            user.first_name or user.username,
            name,
            user.username,
            sso_start_url(),
        ),
        email["from_email"],
        [user.email],
    )
