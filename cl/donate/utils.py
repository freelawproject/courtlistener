"""Helpers for parsing Neon CRM webhook values."""

from datetime import datetime

from django.db import models
from django.utils import timezone

from cl.donate.models import (
    MembershipPaymentStatus,
    NeonMembership,
    NeonMembershipLevel,
)

# Free Law Project membership URLs. They are used all over the code (alert
# forms, the Search Alerts API, the alert modal and the profile's Membership
# page), so they live here. The upgrade URL is a base path; callers append the
# user's Neon membership id.
FLP_MEMBERSHIP_URL = "https://free.law/membership/"
MEMBERSHIP_UPGRADE_BASE_URL = (
    "https://donate.free.law/constituent/memberships/upgrade/"
)
# Legacy memberships can't be upgraded through Neon's standard flow; sending
# them to MEMBERSHIP_UPGRADE_BASE_URL 404s (see #7136). Route them to a help
# page that explains how to get more features instead (e.g. cancel the legacy
# membership and join again).
LEGACY_MEMBERSHIP_HELP_URL = "https://wiki.free.law/c/courtlistener/help/memberships/individual-memberships/legacy-memberships"
# Where members sign in to Neon to change their plan, payment frequency,
# profile or contact information.
DONOR_PORTAL_URL = "https://donate.free.law/login"


def parse_neon_date(value: str) -> datetime:
    """Parse a date string from Neon into a timezone-aware datetime.

    Neon sends bare dates such as ``2026-11-07`` in webhooks and may add a
    time or offset in API responses. Django's field parser handles both, and
    a naive result is made aware in the current time zone, which is exactly
    what Django would do when saving the raw string. Parsing up front keeps
    the model typed and avoids the naive-datetime warning on save.

    Args:
        value: The date string returned by Neon.

    Returns:
        The parsed datetime, made timezone-aware if needed.
    """
    parsed = models.DateTimeField().to_python(value)
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed


def map_payment_status_value(status: str) -> int:
    """Maps a payment status string into its corresponding integer value defined in the `MembershipPaymentStatus` class.

    An empty status means Neon attached no payment info to the membership.
    That happens for free tiers and for memberships granted manually in
    Neon, treat both as SUCCEEDED so they don't stick in "Awaiting payment
    processing".

    Args:
        status (str): The payment status string (e.g., "succeeded", "failed").

    Returns:
        int: The mapped constant value from `MembershipPaymentStatus`.
            Defaults to `PENDING` for unrecognized values.
    """
    match status:
        case "succeeded" | "":
            payment_status = MembershipPaymentStatus.SUCCEEDED
        case "failed":
            payment_status = MembershipPaymentStatus.FAILED
        case _:
            payment_status = MembershipPaymentStatus.PENDING

    return payment_status


def get_membership_upgrade_url(membership: NeonMembership) -> str:
    """Get the best place for a member to go to get more from their plan.

    Legacy memberships can't be upgraded through Neon's upgrade flow (it 404s,
    see #7136), so they are sent to a help page that explains the alternatives.
    A membership without a Neon ID can't be used to build the upgrade URL, so
    those members are sent to the donor portal instead.

    Args:
        membership: The member's membership.

    Returns:
        A URL the member can follow to upgrade or manage their plan.
    """
    if membership.level == NeonMembershipLevel.LEGACY:
        return LEGACY_MEMBERSHIP_HELP_URL
    if not membership.neon_id:
        return DONOR_PORTAL_URL
    return f"{MEMBERSHIP_UPGRADE_BASE_URL}{membership.neon_id}"
