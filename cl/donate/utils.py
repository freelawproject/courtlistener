from datetime import datetime

from django.db import models
from django.utils import timezone

from cl.donate.models import MembershipPaymentStatus


def parse_neon_date(value: str) -> datetime:
    """Parse a date string from Neon into a timezone-aware datetime.

    Neon sends bare dates such as ``2026-11-07`` in webhooks and may add a
    time or offset in API responses. Django's field parser handles both, and
    a naive result is made aware in the current time zone, which is exactly
    what Django would do when saving the raw string. Parsing up front keeps
    the model typed and avoids the naive-datetime warning on save.

    :param value: The date string returned by Neon.
    :return: The parsed datetime, made timezone-aware if needed.
    """
    parsed = models.DateTimeField().to_python(value)
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed


def map_payment_status_value(status: str) -> int:
    """
    Maps a payment status string into its corresponding
    integer value defined in the `MembershipPaymentStatus` class.

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
