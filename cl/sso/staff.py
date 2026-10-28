"""Checks behind the SOC 2 control that staff sign in through FLP's IdP."""

from dataclasses import dataclass, field

from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework.authtoken.models import Token

from cl.sso.models import Organization


@dataclass
class StaffSSOReport:
    """What ``build_staff_sso_report`` found.

    ``problems`` are things an auditor would flag; ``notes`` are for
    review but expected.
    """

    staff_organization: Organization | None
    unlinked: list[User] = field(default_factory=list)
    token_holders: list[User] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def staff_accounts():
    """Active accounts that can use the Django admin.

    These are the accounts SSO_REQUIRED_FOR_STAFF applies to.

    :return: Active staff and superusers.
    """
    return (
        User.objects.filter(is_active=True)
        .filter(Q(is_staff=True) | Q(is_superuser=True))
        .order_by("username")
    )


def permission_holders():
    """Active non-staff accounts holding permissions, e.g. API write access.

    :return: Accounts with a permission granted directly or through a group.
    """
    return (
        User.objects.filter(is_active=True, is_staff=False, is_superuser=False)
        .filter(
            Q(user_permissions__isnull=False)
            | Q(groups__permissions__isnull=False)
        )
        .distinct()
        .order_by("username")
    )


def build_staff_sso_report() -> StaffSSOReport:
    """Check that staff can only get in through FLP's IdP.

    :return: The findings.
    """
    staff_org = Organization.objects.filter(is_staff_organization=True).first()
    report = StaffSSOReport(staff_organization=staff_org)

    if staff_org is None:
        report.problems.append(
            "No organization is marked as the staff organization, so staff "
            "SSO can't be enforced."
        )
        linked_ids: set[int] = set()
    else:
        provider_ids = [c.provider_id for c in staff_org.connections.all()]
        linked_ids = set(
            SocialAccount.objects.filter(
                provider__in=provider_ids
            ).values_list("user_id", flat=True)
        )
        if not provider_ids:
            report.problems.append(
                f"{staff_org} has no SSO connection to sign staff in through."
            )

    service = set(settings.SSO_SERVICE_ACCOUNT_USERNAMES)
    for user in staff_accounts():
        if user.username in service:
            continue
        if user.pk not in linked_ids:
            report.unlinked.append(user)

    # Service accounts authenticate with API tokens. A usable password on
    # one is a way in that no IdP protects.
    with_passwords = [
        u.username
        for u in User.objects.filter(username__in=service, is_active=True)
        if u.has_usable_password()
    ]
    if with_passwords:
        report.problems.append(
            "Service account(s) with a usable password: "
            + ", ".join(with_passwords)
            + ". Set an unusable password; they should only use API tokens."
        )
    others = [
        u.username for u in permission_holders() if u.username not in service
    ]
    if others:
        report.notes.append(
            "Non-staff accounts holding permissions (review, or list them in "
            "SSO_SERVICE_ACCOUNT_USERNAMES): " + ", ".join(others)
        )
    if report.unlinked:
        report.problems.append(
            f"{len(report.unlinked)} staff account(s) aren't linked to the "
            "staff IdP: " + ", ".join(u.username for u in report.unlinked)
        )

    if not settings.SSO_REQUIRED_FOR_STAFF:
        report.problems.append(
            "SSO_REQUIRED_FOR_STAFF is off, so staff can still sign in with "
            "a password."
        )

    # A DRF token issued before MFA isn't an MFA-protected credential, so
    # every staff token needs a decision (see the SOC 2 checklist).
    report.token_holders = list(
        User.objects.filter(
            pk__in=Token.objects.filter(user__in=staff_accounts()).values(
                "user_id"
            )
        ).order_by("username")
    )
    if report.token_holders:
        report.notes.append(
            f"{len(report.token_holders)} staff account(s) hold API tokens: "
            + ", ".join(u.username for u in report.token_holders)
        )

    return report
