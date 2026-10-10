"""Check expired Neon memberships for updates that webhooks may have missed.

This command runs daily and checks expired memberships against the Neon API.
If a member renewed but the renewal webhook was missed, it updates the local
record and rebuilds the member's API throttles.

Memberships that Neon confirms have no active membership are deleted after a
week. The membership history is kept by pghistory, and a later renewal creates
a new record through the createMembership webhook.
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import requests
from django.db import models, transaction
from django.db.models import QuerySet
from django.utils import timezone

from cl.api.utils import (
    apply_membership_throttles,
    clear_membership_throttles,
)
from cl.donate.models import NeonMembership, NeonMembershipLevel
from cl.donate.utils import map_payment_status_value
from cl.lib.command_utils import VerboseCommand
from cl.lib.neon_utils import NeonClient
from cl.users.tasks import tag_zoho_record_for_membership

logger = logging.getLogger(__name__)


class SyncResult(Enum):
    """Result of syncing a membership with Neon."""

    # Neon had newer data and the local record was updated.
    UPDATED = "updated"
    # Neon matches our record or has nothing for the user; no new information.
    UNCHANGED = "unchanged"
    # Neon has data we can't apply (unknown level, EDU without a .edu email);
    # the record is left alone for a human to look at.
    SKIPPED = "skipped"


def get_expired_memberships(
    min_hours_expired: int, max_days_expired: int | None
) -> QuerySet[NeonMembership]:
    """Return memberships that expired within the given time window.

    The lower bound gives Neon time to process auto-renewals and deliver the
    matching webhooks before we poll. The upper bound keeps the number of
    Neon API calls per daily run proportional to recent lapses, including
    records the command can't fix and would otherwise re-check forever.

    :param min_hours_expired: Minimum hours since the membership expired.
    :param max_days_expired: Maximum days since expiration, or None for no
           upper limit.
    :return: Memberships ordered by expiration date, with the user and
           profile loaded.
    """
    right_now = timezone.now()
    queryset = NeonMembership.objects.filter(
        termination_date__lt=right_now - timedelta(hours=min_hours_expired)
    )
    if max_days_expired is not None:
        queryset = queryset.filter(
            termination_date__gte=right_now - timedelta(days=max_days_expired)
        )
    return queryset.select_related("user__profile").order_by(
        "termination_date"
    )


def parse_neon_date(value: str) -> datetime:
    """Parse a date string from Neon into a timezone-aware datetime.

    Neon can send dates with or without a UTC offset. Using Django's date
    parser keeps the result consistent with the webhook handlers.

    :param value: The date string returned by Neon.
    :return: The parsed datetime, made timezone-aware if needed.
    """
    parsed = models.DateTimeField().to_python(value)
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed


def sync_membership_from_neon(
    membership: NeonMembership, neon_membership: dict[str, Any]
) -> SyncResult:
    """Update a local membership to match a membership record from Neon.

    Mirrors what the webhook handlers do when a membership is created or
    updated: the local record takes Neon's membership ID, level, term end
    date and payment status, and the user's MEMBERSHIP-source API throttles
    are rebuilt for the new level. Nothing is written when Neon's record
    already matches ours, so the command is safe to run repeatedly.

    EDU memberships are only honored for ``.edu`` email addresses, like the
    webhook does, and Memberships with unknown levels are skipped.

    :param membership: The local membership to update.
    :param neon_membership: A membership record as returned by the Neon API.
    :return: Whether the record was updated, left unchanged, or skipped.
    """
    user = membership.user
    level_name = neon_membership["membershipLevel"]["name"]
    level = NeonMembershipLevel.TYPES_INVERTED.get(level_name)
    if level is None:
        logger.warning(
            "Unknown Neon membership level %r for user %s; skipping.",
            level_name,
            user.username,
        )
        return SyncResult.SKIPPED

    if level == NeonMembershipLevel.EDU and not user.email.endswith(".edu"):
        logger.warning(
            "User %s has an EDU membership in Neon but no .edu email; "
            "skipping.",
            user.username,
        )
        return SyncResult.SKIPPED

    payments = neon_membership.get("payments") or []
    payment_status = map_payment_status_value(
        payments[0].get("paymentStatus", "").lower() if payments else ""
    )

    term_end_date = neon_membership.get("termEndDate")
    termination_date = (
        parse_neon_date(term_end_date) if term_end_date else None
    )
    current_date = (
        membership.termination_date.date()
        if membership.termination_date
        else None
    )
    new_date = termination_date.date() if termination_date else None
    unchanged = (
        membership.neon_id == str(neon_membership["id"])
        and membership.level == level
        and membership.payment_status == payment_status
        and current_date == new_date
    )
    if unchanged:
        return SyncResult.UNCHANGED

    logger.info(
        "Syncing membership for user %s from Neon: id %s -> %s, level %s -> "
        "%s, termination %s -> %s, payment status %s -> %s",
        user.username,
        membership.neon_id,
        neon_membership["id"],
        membership.level,
        level,
        current_date,
        new_date,
        membership.payment_status,
        payment_status,
    )
    with transaction.atomic():
        membership.neon_id = str(neon_membership["id"])
        membership.level = level
        membership.termination_date = termination_date
        membership.payment_status = payment_status
        membership.save()
        apply_membership_throttles(user, level)
    tag_zoho_record_for_membership.delay(user.pk, level)
    return SyncResult.UPDATED


def delete_expired_membership(membership: NeonMembership) -> None:
    """Delete an expired membership and its membership-based API throttles.

    Only call this after Neon confirms there is no active membership.
    Manual throttles are preserved, and pghistory keeps the deleted record.
    If the user renews later, the createMembership webhook recreates the
    record from scratch.

    The throttle override cache is left to expire on its own rather than
    cleared, since clearing it costs a Redis scan and the membership was
    already inactive.

    :param membership: The expired membership to delete.
    """
    with transaction.atomic():
        clear_membership_throttles(membership.user, clear_cache=False)
        membership.delete()


def sync_expired_memberships(
    min_hours_expired: int,
    max_days_expired: int | None,
    delete_after_days: int,
) -> tuple[int, int, int]:
    """Check expired memberships against the Neon API and sync their data.

    Each membership requires one API request. If a request fails, the user
    has no Neon account ID, or the membership cannot be updated safely, the
    command skips that membership and continues.

    Memberships confirmed to have no active membership are deleted once
    they have been expired for at least delete_after_days. Set this value
    to 0 to disable deletion.

    :param min_hours_expired: See `get_expired_memberships`.
    :param max_days_expired: See `get_expired_memberships`.
    :param delete_after_days: Age in days past the termination date after
        which a confirmed-expired membership is deleted. 0 disables deletion.
    :return: A three-tuple of memberships checked, updated and deleted.
    """
    client = NeonClient()
    delete_before = (
        timezone.now() - timedelta(days=delete_after_days)
        if delete_after_days > 0
        else None
    )
    checked = updated = deleted = 0
    for membership in get_expired_memberships(
        min_hours_expired, max_days_expired
    ):
        checked += 1
        account_id = membership.user.profile.neon_account_id  # type: ignore
        if not account_id:
            logger.warning(
                "User %s has a membership but no Neon account ID; skipping.",
                membership.user.username,
            )
            continue

        try:
            neon_membership = client.get_primary_active_membership(account_id)
        except requests.RequestException as e:
            logger.warning(
                "Neon API request failed for account %s (user %s): %s",
                account_id,
                membership.user.username,
                e,
            )
            continue

        if neon_membership is None:
            logger.debug(
                "Neon reports no active membership for user %s.",
                membership.user.username,
            )
            result = SyncResult.UNCHANGED
        else:
            result = sync_membership_from_neon(membership, neon_membership)

        if result is SyncResult.UPDATED:
            updated += 1
        elif (
            result is SyncResult.UNCHANGED
            and delete_before is not None
            and membership.termination_date
            and membership.termination_date < delete_before
        ):
            logger.info(
                "Deleting expired membership for user %s: expired on %s and "
                "Neon has nothing newer.",
                membership.user.username,
                membership.termination_date.date(),
            )
            delete_expired_membership(membership)
            deleted += 1

    return checked, updated, deleted


class Command(VerboseCommand):
    """Re-sync expired Neon memberships that webhooks may have missed."""

    help = (
        "Check expired memberships against the Neon API, update the local "
        "record and API throttles when Neon shows a newer membership, and "
        "delete expired memberships Neon confirms once they are a week old. "
        "Meant to run daily as a safety net for lost webhooks."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-hours-expired",
            type=int,
            default=24,
            help="Only check memberships that expired at least this many "
            "hours ago, giving Neon time to process auto-renewals and send "
            "webhooks first. Default: 24.",
        )
        parser.add_argument(
            "--max-days-expired",
            type=int,
            default=90,
            help="Only check memberships that expired at most this many "
            "days ago, bounding the number of Neon API calls per run. Pass "
            "0 to remove the limit for a full clean-up. Default: 90.",
        )
        parser.add_argument(
            "--delete-after-days",
            type=int,
            default=7,
            help="Delete expired memberships that Neon confirms have nothing "
            "newer once they expired at least this many days ago. 0 "
            "disables deletion. Default: 7.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        max_days_expired = options["max_days_expired"]
        checked, updated, deleted = sync_expired_memberships(
            options["min_hours_expired"],
            max_days_expired if max_days_expired > 0 else None,
            options["delete_after_days"],
        )
        self.stdout.write(
            f"Checked {checked} expired memberships, updated {updated}, "
            f"deleted {deleted}."
        )
