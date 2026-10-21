"""Check expired Neon memberships for updates that webhooks may have missed.

This command runs daily and checks expired memberships against the Neon API.
If a member renewed but the renewal webhook was missed, it updates the local
record and rebuilds the member's API throttles.

Memberships keep their benefits for NEON_MEMBERSHIP_GRACE_PERIOD_DAYS after
their termination date. That grace period is what gives this command time to
catch a missed renewal before access drops, so it selects memberships by
their raw termination date, not by whether benefits have ended, and should
run at least daily with --min-hours-expired well below the grace period.

Memberships that Neon confirms have no active membership are deleted after a
week. The membership history is kept by pghistory, and a later renewal creates
a new record through the createMembership webhook.
"""

import logging
from collections import Counter
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import requests
from django.conf import settings
from django.core.management.base import CommandError
from django.db import models, transaction
from django.db.models import QuerySet
from django.utils import timezone

from cl.api.utils import (
    apply_membership_throttles,
    clear_membership_throttles,
)
from cl.donate.models import (
    MembershipPaymentStatus,
    NeonMembership,
    NeonMembershipLevel,
)
from cl.lib.command_utils import VerboseCommand
from cl.lib.neon_utils import NeonClient
from cl.users.tasks import tag_zoho_record_for_membership

logger = logging.getLogger(__name__)


class SyncResult(Enum):
    """Outcome of checking one membership against Neon."""

    # Neon had newer data and the local record was updated.
    UPDATED = "updated"
    # Neon matches our record or has nothing for the user; no new information.
    UNCHANGED = "unchanged"
    # Neon has data we can't apply yet or at all (payment still in progress,
    # unexpected status, no term end date, unknown level, EDU without a .edu
    # email, no Neon account id); the record is left alone and never deleted.
    SKIPPED = "skipped"
    # Neon confirmed the lapse and the local record was deleted.
    DELETED = "deleted"
    # The check itself failed (Neon request error or an unexpected error);
    # nothing was written and the record is retried on the next run.
    FAILED = "failed"


# Neon membership statuses the command understands. SUCCEEDED is the only
# state copied locally. PENDING and FAILED mean a payment is still being
# processed or retried, so the local record is left alone and re-checked on
# the next run. Anything else is reported for manual review.
NEON_STATUS_SUCCEEDED = "SUCCEEDED"
NEON_STATUSES_IN_PROGRESS = frozenset({"PENDING", "FAILED"})


def get_expired_memberships(
    min_hours_expired: int, max_days_expired: int | None
) -> QuerySet[NeonMembership]:
    """Return memberships that expired within the given time window.

    The lower bound gives Neon time to process auto-renewals and deliver the
    matching webhooks before we poll. The upper bound keeps the number of
    Neon API calls per daily run proportional to recent lapses, including
    records the command can't fix and would otherwise re-check forever.
    The window is based on the termination date itself, so memberships still
    inside the grace period are checked while their benefits are intact.

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
    updated: the local record takes Neon's membership ID, level and term end
    date, its payment status is marked SUCCEEDED, and the user's
    MEMBERSHIP-source API throttles are rebuilt for the new level.

    Only a SUCCEEDED Neon membership whose term ends in the future, and later
    than the local record, is applied. A record that is no newer than ours is
    reported as unchanged so the caller can decide whether to delete the
    local row. Memberships still PENDING or FAILED in Neon are left alone to
    be re-checked on the next run. Anything else (no term end date, a
    cancelled or refunded membership, an unknown level, an EDU membership
    without a ``.edu`` email) is skipped and logged for a human.

    The caller loads memberships once per run, so by the time we write, a
    webhook may already have changed or deleted the row. In that case the
    webhook had newer data: nothing is written and the record is skipped.

    :param membership: The local membership to update.
    :param neon_membership: A membership record as returned by the Neon API.
    :return: Whether the record was updated, left unchanged, or skipped.
    """
    user = membership.user
    neon_id = str(neon_membership["id"])
    status = neon_membership.get("status")
    # ``payments`` is an unordered list that can include earlier failed
    # attempts of a renewal that eventually succeeded.
    payments = neon_membership.get("payments") or []
    raw_payment_status = (
        (payments[0].get("paymentStatus") or "") if payments else ""
    )

    term_end_date = neon_membership.get("termEndDate")
    if not term_end_date:
        logger.error(
            "Neon membership %s for user %s has no termEndDate (status %s, "
            "paymentStatus %r); skipping.",
            neon_id,
            user.username,
            status,
            raw_payment_status,
        )
        return SyncResult.SKIPPED

    termination_date = parse_neon_date(term_end_date)
    new_date = timezone.localdate(termination_date)
    current_date = (
        timezone.localdate(membership.termination_date)
        if membership.termination_date
        else None
    )
    if new_date < timezone.localdate() or (
        current_date and new_date <= current_date
    ):
        # Neon's record grants nothing beyond what we already have: it is
        # either expired as well or the same term we already stored. Dates
        # are compared in the current time zone, like NeonMembership.is_active.
        return SyncResult.UNCHANGED

    if status in NEON_STATUSES_IN_PROGRESS:
        logger.warning(
            "Neon membership %s for user %s is %s (paymentStatus %r); "
            "leaving the local record for the next run.",
            neon_id,
            user.username,
            status,
            raw_payment_status,
        )
        return SyncResult.SKIPPED

    if status != NEON_STATUS_SUCCEEDED:
        logger.error(
            "Neon membership %s for user %s has unexpected status %s "
            "(paymentStatus %r, termEndDate %s); skipping.",
            neon_id,
            user.username,
            status,
            raw_payment_status,
            term_end_date,
        )
        return SyncResult.SKIPPED

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

    payment_status = MembershipPaymentStatus.SUCCEEDED
    logger.info(
        "Syncing membership for user %s from Neon: id %s -> %s, level %s -> "
        "%s, termination %s -> %s, payment status %s -> %s",
        user.username,
        membership.neon_id,
        neon_id,
        membership.level,
        level,
        current_date,
        new_date,
        membership.payment_status,
        payment_status,
    )
    with transaction.atomic():
        # date_modified detects webhook updates that happened while we were
        # talking to Neon. The lock makes subsequent webhook updates wait
        # until we commit. no_key is used since we don't change the
        # primary key or user, and it doesn't block foreign key references.
        locked = (
            NeonMembership.objects.select_for_update(no_key=True)
            .filter(pk=membership.pk, date_modified=membership.date_modified)
            .first()
        )
        if locked is None:
            logger.info(
                "Membership for user %s changed or was deleted by a webhook "
                "since this run started; skipping.",
                user.username,
            )
            return SyncResult.SKIPPED
        locked.neon_id = neon_id
        locked.level = level
        locked.termination_date = termination_date
        locked.payment_status = payment_status
        locked.save()
        apply_membership_throttles(user, level)
    tag_zoho_record_for_membership.delay(user.pk, level)
    return SyncResult.UPDATED


def delete_expired_membership(membership: NeonMembership) -> bool:
    """Delete an expired membership and its membership-based API throttles.

    Only call this after Neon confirms there is no active membership.
    Manual throttles are preserved, and pghistory keeps the deleted record.
    If the user renews later, the createMembership webhook recreates the
    record from scratch.

    The delete only happens if no webhook changed or removed the row since
    it was loaded; otherwise the webhook had newer data and nothing is
    touched. The throttle override cache is left to expire on its own
    rather than cleared, since clearing it costs a Redis scan and the
    membership was already inactive.

    :param membership: The expired membership to delete.
    :return: True if the membership was deleted, False if a webhook got
        there first.
    """
    with transaction.atomic():
        deleted, _ = NeonMembership.objects.filter(
            pk=membership.pk, date_modified=membership.date_modified
        ).delete()
        if not deleted:
            logger.info(
                "Membership for user %s changed or was deleted by a webhook "
                "since this run started; not deleting.",
                membership.user.username,
            )
            return False
        clear_membership_throttles(membership.user, clear_cache=False)
    logger.info(
        "Deleted expired membership for user %s: it ended on %s and Neon "
        "had nothing newer.",
        membership.user.username,
        membership.termination_date
        and timezone.localdate(membership.termination_date),
    )
    return True


def check_membership(
    client: NeonClient,
    membership: NeonMembership,
    delete_before: datetime | None,
) -> SyncResult:
    """Check one expired membership against Neon and apply what it finds.

    Fetches the account's primary active membership, syncs it into the local
    record when it is newer, and deletes the local record when Neon confirms
    the lapse and the membership ended before ``delete_before``. A failed
    Neon request is logged and reported as FAILED so the caller can move on
    to the next member; any other exception propagates to the caller.

    :param client: The Neon API client.
    :param membership: The local membership to check, with its user and
        profile loaded.
    :param delete_before: Delete confirmed lapses that ended before this
        instant, or None to never delete.
    :return: What happened to the membership.
    """
    user = membership.user
    account_id = user.profile.neon_account_id  # type: ignore
    if not account_id:
        logger.warning(
            "User %s has a membership but no Neon account ID; skipping.",
            user.username,
        )
        return SyncResult.SKIPPED

    try:
        neon_membership = client.get_primary_active_membership(account_id)
    except requests.RequestException as e:
        logger.warning(
            "Neon API request failed for account %s (user %s): %s",
            account_id,
            user.username,
            e,
        )
        return SyncResult.FAILED

    if neon_membership is None:
        logger.debug(
            "Neon reports no active membership for user %s.", user.username
        )
        result = SyncResult.UNCHANGED
    else:
        result = sync_membership_from_neon(membership, neon_membership)

    if (
        result is SyncResult.UNCHANGED
        and delete_before is not None
        and membership.termination_date
        and membership.termination_date < delete_before
        and delete_expired_membership(membership)
    ):
        return SyncResult.DELETED
    return result


def sync_expired_memberships(
    min_hours_expired: int,
    max_days_expired: int | None,
    delete_after_days: int,
) -> Counter[SyncResult]:
    """Check expired memberships against the Neon API and sync their data.

    Each membership costs one API request. One bad record must not stop the
    run: a failed Neon request is logged as a warning, and any other error
    while handling a membership is logged with its traceback, so it reaches
    Sentry, and counted as FAILED.

    Memberships confirmed to have no active membership are deleted once
    they have been expired for at least delete_after_days. Set this value
    to 0 to disable deletion.

    :param min_hours_expired: See `get_expired_memberships`.
    :param max_days_expired: See `get_expired_memberships`.
    :param delete_after_days: Age in days past the termination date after
        which a confirmed-expired membership is deleted. 0 disables deletion.
    :return: How many memberships ended in each ``SyncResult``.
    """
    client = NeonClient()
    delete_before = (
        timezone.now() - timedelta(days=delete_after_days)
        if delete_after_days > 0
        else None
    )
    counts: Counter[SyncResult] = Counter()
    for membership in get_expired_memberships(
        min_hours_expired, max_days_expired
    ):
        try:
            result = check_membership(client, membership, delete_before)
        except Exception:
            logger.exception(
                "Unexpected error while syncing the membership of user %s; "
                "leaving it for the next run.",
                membership.user.username,
            )
            result = SyncResult.FAILED
        counts[result] += 1
    return counts


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
            "newer once they expired at least this many days ago. Must be "
            "greater than NEON_MEMBERSHIP_GRACE_PERIOD_DAYS so members are "
            "never deleted while still inside the grace period. 0 disables "
            "deletion. Default: 7.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        delete_after_days = options["delete_after_days"]
        grace_days = settings.NEON_MEMBERSHIP_GRACE_PERIOD_DAYS
        if 0 < delete_after_days <= grace_days:
            # Deleting the row also deletes its MEMBERSHIP throttles, so a
            # delete inside the grace period would cut access early.
            raise CommandError(
                "--delete-after-days must be greater than the membership "
                f"grace period ({grace_days} days) or 0 to disable deletion."
            )
        max_days_expired = options["max_days_expired"]
        counts = sync_expired_memberships(
            options["min_hours_expired"],
            max_days_expired if max_days_expired > 0 else None,
            delete_after_days,
        )
        self.stdout.write(
            f"Checked {sum(counts.values())} expired memberships: "
            f"{counts[SyncResult.UPDATED]} updated, "
            f"{counts[SyncResult.DELETED]} deleted, "
            f"{counts[SyncResult.SKIPPED]} skipped, "
            f"{counts[SyncResult.FAILED]} failed."
        )
