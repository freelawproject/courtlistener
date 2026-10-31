"""Who has to use single sign-on, and where they should be sent.

Every enforcement point (registration, email change, password sign-in,
password reset, HTTP Basic auth and existing sessions) asks the functions in
this module, so the rules live in one place.
"""

from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.safestring import SafeString

from cl.sso.models import (
    Enforcement,
    MembershipSource,
    Organization,
    OrganizationDomain,
    SSOConnection,
    SSOEmailException,
)


class RequirementReason:
    """Why somebody must sign in with SSO."""

    DOMAIN = "domain"
    LINKED = "linked"
    STAFF = "staff"


@dataclass(frozen=True)
class SSORequirement:
    """A rule that says a person must sign in through an organization's IdP.

    ``connection`` is where to send them, or None if the organization has no
    enabled connection (a misconfiguration; they can't sign in until staff
    fix it, which is the safe failure).
    """

    organization: Organization
    connection: SSOConnection | None
    reason: str


def email_domain(email: str) -> str:
    """Return the lowercased domain of an address, or "" if it has none.

    :param email: An email address.
    :return: The part after the last "@", lowercased.
    """
    _, at, domain = email.strip().rpartition("@")
    return domain.lower() if at else ""


def enabled_connection(organization: Organization) -> SSOConnection | None:
    """Pick the IdP connection to send an organization's people to.

    :param organization: The organization.
    :return: Its oldest enabled connection, or None.
    """
    return (
        organization.connections.filter(is_enabled=True)
        .select_related("social_app")
        .order_by("pk")
        .first()
    )


def verified_domain_for_email(email: str) -> OrganizationDomain | None:
    """Find the verified organization domain an address is on.

    :param email: An email address.
    :return: The verified domain record, or None.
    """
    if not (domain := email_domain(email)):
        return None
    return (
        OrganizationDomain.objects.filter(
            domain=domain, verified_at__isnull=False
        )
        .select_related("organization")
        .first()
    )


def is_email_exception(organization: Organization, email: str) -> bool:
    """Whether staff have allowed this address to keep using a password.

    :param organization: The organization that owns the address's domain.
    :param email: The address.
    :return: True if it is on the organization's exception list.
    """
    return SSOEmailException.objects.filter(
        organization=organization, email__iexact=email.strip()
    ).exists()


def sso_option_for_email(
    email: str,
) -> tuple[OrganizationDomain, SSOConnection] | None:
    """Find the SSO login to offer somebody who typed this address.

    Used by the "sign in with SSO" page. Domains with enforcement off aren't
    offered, so organizations can test their setup before people see it.

    :param email: The address the person typed.
    :return: The domain and the connection to send them to, or None.
    """
    domain = verified_domain_for_email(email)
    if domain is None or domain.enforcement == Enforcement.OFF:
        return None
    if (connection := enabled_connection(domain.organization)) is None:
        return None
    return domain, connection


def requirement_for_email(email: str) -> SSORequirement | None:
    """Whether an address may only be used through SSO.

    True for addresses on a verified domain whose enforcement is "required",
    unless the address is on the organization's exception list. Whether the
    domain uses SSO isn't secret, so callers may tell people about it.

    :param email: The address.
    :return: The requirement, or None if passwords are allowed.
    """
    domain = verified_domain_for_email(email)
    if domain is None or domain.enforcement != Enforcement.REQUIRED:
        return None
    organization = domain.organization
    if is_email_exception(organization, email):
        return None
    return SSORequirement(
        organization=organization,
        connection=enabled_connection(organization),
        reason=RequirementReason.DOMAIN,
    )


def requirement_for_user(user: User) -> SSORequirement | None:
    """Whether an account may only sign in through SSO.

    An account must use SSO if any of these is true:

    - Staff SSO is required (SSO_REQUIRED_FOR_STAFF) and the account is
      staff or a superuser. They must use the staff organization's IdP.
    - Its address is covered by ``requirement_for_email``.
    - It was linked by SSO to an organization that requires SSO on any of
      its domains. Moving the account to another address doesn't let a
      linked person get around their organization's policy.

    :param user: The account.
    :return: The first requirement that applies, or None.
    """
    if settings.SSO_REQUIRED_FOR_STAFF and (
        user.is_staff or user.is_superuser
    ):
        staff_org = Organization.objects.filter(
            is_staff_organization=True
        ).first()
        # Without a staff organization there is nowhere to send staff, and
        # refusing their passwords would lock everybody out of the admin.
        # check_staff_sso reports this misconfiguration.
        if staff_org is not None:
            return SSORequirement(
                organization=staff_org,
                connection=enabled_connection(staff_org),
                reason=RequirementReason.STAFF,
            )

    if user.email and (requirement := requirement_for_email(user.email)):
        return requirement

    linked_org = (
        Organization.objects.filter(
            memberships__user=user,
            memberships__source=MembershipSource.SSO,
            domains__enforcement=Enforcement.REQUIRED,
            domains__verified_at__isnull=False,
        )
        .distinct()
        .first()
    )
    if linked_org is None:
        return None
    if user.email and is_email_exception(linked_org, user.email):
        return None
    return SSORequirement(
        organization=linked_org,
        connection=enabled_connection(linked_org),
        reason=RequirementReason.LINKED,
    )


def sso_start_url(email: str = "", next_url: str = "") -> str:
    """Build a link to the "sign in with SSO" page.

    :param email: An address to fill in for the person.
    :param next_url: Where to go after signing in.
    :return: A path with the given query parameters.
    """
    params = {k: v for k, v in (("email", email), ("next", next_url)) if v}
    url = reverse("sso_start")
    return f"{url}?{urlencode(params)}" if params else url


def refusal_message(
    requirement: SSORequirement, email: str = ""
) -> SafeString:
    """Explain to somebody that they have to sign in with SSO.

    :param requirement: Why they have to.
    :param email: Their address, to carry over to the SSO page.
    :return: An HTML message safe to show on a page.
    """
    return format_html(
        '{} requires single sign-on. <a href="{}">Sign in with {} SSO</a> '
        "instead.",
        requirement.organization.name,
        sso_start_url(email=email),
        requirement.organization.name,
    )
