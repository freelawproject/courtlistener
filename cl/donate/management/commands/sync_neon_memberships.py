"""Reconcile local memberships with Neon to recover missed webhooks.

This command checks local memberships against the Neon API. When a renewal
webhook is missed, it updates the local membership and rebuilds the member's
API throttles.

Neon merges duplicate accounts. The old account ID keeps answering, with the
surviving account's record, but lists no memberships. So the command resolves
the account before reading its memberships and adopts the surviving ID when
it differs. An account that is gone, or whose survivor already belongs to
another local user, is reported for a human and left alone.

A member can also hold a duplicate account that Neon has not merged yet, with
the membership bought under the one we don't store. When the account lists no
memberships, the membership we store is fetched by ID and the account that
holds it is adopted under the same rules.

Members retain their benefits for NEON_MEMBERSHIP_GRACE_PERIOD_DAYS after
their termination date. To allow time to recover missed renewals before
access expires, the command selects memberships by their raw termination
date rather than when their benefits end.

Memberships whose payment status is not SUCCEEDED are also checked,
regardless of their termination date. A failed auto-renewal can leave a
membership with a future term end date but a FAILED payment status, causing
the member to lose access until Neon successfully retries the payment.
If the success webhook is missed, this command restores the membership.

Memberships that Neon confirms are no longer active are deleted after
a week. Their history is retained by pghistory, and any subsequent renewal
creates a new local record through the createMembership webhook.
"""

import logging
from collections import Counter
from datetime import date, datetime, timedelta
from enum import Enum
from http import HTTPStatus
from typing import Any

import requests
from django.conf import settings
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import Q, QuerySet
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
from cl.donate.utils import parse_neon_date
from cl.lib.command_utils import VerboseCommand
from cl.lib.neon_utils import NeonClient
from cl.users.models import UserProfile
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


def get_memberships_to_check(
    min_hours: int, max_days: int | None
) -> QuerySet[NeonMembership]:
    """Return the memberships worth checking against Neon this run.

    Selects two groups of memberships:
    - Expired memberships, based on their termination date. This includes
      memberships still within the grace period, while benefits remain active.
    - Unpaid memberships, whose payment status is not SUCCEEDED, based on
      when the record last changed. Failed renewals can leave a future term
      end date with an unsuccessful payment status.

    The lower bound gives Neon time to process auto-renewals, retry failed
    charges and deliver the matching webhooks before we poll. The upper
    bound on termination date keeps the number of Neon API calls per daily
    run proportional to recent activity, including records the command
    can't fix and would otherwise re-check forever.

    :param min_hours: Minimum hours since the membership expired, or since
           an unpaid membership last changed.
    :param max_days: Maximum days since the termination date, or None for
           no upper limit.
    :return: Memberships ordered by termination date, with the user and
           profile loaded.
    """
    right_now = timezone.now()
    lower = right_now - timedelta(hours=min_hours)
    expired = Q(termination_date__lt=lower)
    unpaid = ~Q(payment_status=MembershipPaymentStatus.SUCCEEDED) & Q(
        date_modified__lt=lower
    )
    queryset = NeonMembership.objects.filter(expired | unpaid)
    if max_days is not None:
        queryset = queryset.filter(
            termination_date__gte=right_now - timedelta(days=max_days)
        )
    return queryset.select_related("user__profile").order_by(
        "termination_date"
    )


def select_membership_to_sync(
    memberships: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Pick the record worth syncing from an account's membership history.

    A SUCCEEDED membership whose term is running today takes precedence,
    with the latest term end winning when multiple terms overlap.

    Neon charges auto-renewals early and lists the next term first, so
    the newest paid record may not have started yet. Applying it too
    early could advance the term end or membership level.

    If no paid term is currently running, the earliest upcoming paid
    term wins. This handles renewals purchased after a gap.

    If no paid term is available, return the newest record regardless
    of status. Its status helps distinguish an ongoing renewal attempt
    from an account that has fully lapsed.

    :param memberships: The account's memberships, newest first, as
        returned by ``NeonClient.get_account_memberships``.
    :return: The record to hand to ``sync_membership_from_neon``, or None
        when the account has no memberships.
    """
    today = timezone.localdate()
    running: list[tuple[date, dict[str, Any]]] = []
    upcoming: list[tuple[date, dict[str, Any]]] = []
    for record in memberships:
        if record.get("status") != NEON_STATUS_SUCCEEDED:
            continue
        if not (term_end := record.get("termEndDate")):
            continue
        end = timezone.localdate(parse_neon_date(term_end))
        if end < today:
            continue
        term_start = record.get("termStartDate")
        start = (
            timezone.localdate(parse_neon_date(term_start))
            if term_start
            else None
        )
        if start is None or start <= today:
            running.append((end, record))
        else:
            upcoming.append((start, record))
    if running:
        return max(running, key=lambda pair: pair[0])[1]
    if upcoming:
        return min(upcoming, key=lambda pair: pair[0])[1]
    return memberships[0] if memberships else None


def sync_membership_from_neon(
    membership: NeonMembership, neon_membership: dict[str, Any]
) -> SyncResult:
    """Update a local membership to match a membership record from Neon.

    Mirrors what the webhook handlers do when a membership is created or
    updated: the local record takes Neon's membership ID, level and term end
    date, its payment status is marked SUCCEEDED, and the user's
    MEMBERSHIP-source API throttles are rebuilt for the new level.

    Only SUCCEEDED memberships with a future term end date are applied.
    A membership is updated when its term end date is later than the local
    one, or when the dates match but the local payment status is not
    SUCCEEDED. This also repairs renewals that succeeded after a failed
    charge. A record that is no newer than ours is reported as unchanged so
    the caller can decide whether to delete the local row. Memberships still
    PENDING or FAILED in Neon are left alone to be re-checked on the next run.
    Anything else (no term end date, a cancelled or refunded membership, an
    unknown level, an EDU membership without a ``.edu`` email) is skipped and
    logged for a human.

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
    # Use the current time zone, matching NeonMembership.is_active.
    if new_date < timezone.localdate():
        # The Neon membership has expired.
        return SyncResult.UNCHANGED

    if current_date and new_date < current_date:
        # Older than the term we already store.
        return SyncResult.UNCHANGED

    if (
        current_date
        and new_date == current_date
        and membership.payment_status == MembershipPaymentStatus.SUCCEEDED
    ):
        # The term is unchanged and payment has already succeeded.
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
    logger.info(
        "Synced membership for user %s from Neon: id %s -> %s, level %s -> "
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


def adopt_neon_account(
    membership: NeonMembership, account_id: str, reason: str
) -> bool:
    """Point the member's profile at a different Neon account ID.

    Used when Neon reports that the account we store was merged into another
    one, or that the membership we store lives under another account.
    Refuses when a different profile already holds the new ID: the webhook
    handler looks users up by it, and ``neon_account_id`` is not unique, so
    a second holder would make that lookup ambiguous. The refusal is logged
    at ERROR for a human to merge the local accounts.

    :param membership: The membership whose user's profile is updated.
    :param account_id: The Neon account ID to store.
    :param reason: Why the switch is happening, for the log line.
    :return: True if the profile now carries the new ID.
    """
    user = membership.user
    profile: UserProfile = user.profile  # type: ignore
    holder = (
        UserProfile.objects.filter(neon_account_id=account_id)
        .exclude(pk=profile.pk)
        .values_list("user__username", flat=True)
        .first()
    )
    if holder:
        logger.error(
            "Neon account %s already belongs to user %s, not %s (%s); "
            "skipping until the local accounts are merged.",
            account_id,
            holder,
            user.username,
            reason,
        )
        return False
    logger.info(
        "Switching user %s from Neon account %s to %s (%s).",
        user.username,
        profile.neon_account_id,
        account_id,
        reason,
    )
    profile.neon_account_id = account_id
    profile.save(update_fields=["neon_account_id"])
    return True


def resolve_neon_account(
    client: NeonClient, membership: NeonMembership
) -> str | None:
    """Return the Neon account ID to use for a member, repairing a merge.

    Neon answers a merged-away account ID with the surviving account's
    record, which carries a different ``accountId``; the old ID still
    answers but lists no memberships, so the surviving ID is adopted. An
    account Neon no longer has at all is reported for a human. Transport
    and server errors propagate so the caller can retry on the next run.

    :param client: The Neon API client.
    :param membership: The local membership, with its user and profile
        loaded.
    :return: The account ID to use, or None when the row must be skipped.
    """
    user = membership.user
    profile: UserProfile = user.profile  # type: ignore
    try:
        account = client.get_account_by_id(profile.neon_account_id)
    except requests.HTTPError as e:
        if (
            e.response is None
            or e.response.status_code != HTTPStatus.NOT_FOUND
        ):
            raise
        logger.error(
            "Neon account %s for user %s no longer exists; skipping.",
            profile.neon_account_id,
            user.username,
        )
        return None
    account_id = str(account["accountId"])
    if account_id == profile.neon_account_id:
        return account_id
    reason = f"Neon merged account {profile.neon_account_id} into it"
    if adopt_neon_account(membership, account_id, reason):
        return account_id
    return None


def find_membership_account(
    client: NeonClient, membership: NeonMembership
) -> str | None:
    """Return the Neon account that currently holds the membership we store.

    For a member whose account lists no memberships. Duplicate accounts are
    merged by Neon's Account Match only eventually; until then a membership
    bought under the duplicate is invisible from the account we store. The
    membership record names its current account. This is discovery only:
    the caller still picks the membership to sync from that account's list,
    so a replaced membership is not missed.

    :param client: The Neon API client.
    :param membership: The local membership, with its user loaded.
    :return: The holding account's ID, or None when we store no membership
        ID or Neon no longer has the membership.
    """
    if not membership.neon_id:
        return None
    record = client.get_membership(membership.neon_id)
    if record is None:
        logger.debug(
            "Neon no longer has membership %s for user %s.",
            membership.neon_id,
            membership.user.username,
        )
        return None
    return str(record.get("accountId") or "") or None


def check_membership(
    client: NeonClient,
    membership: NeonMembership,
    delete_before: datetime | None,
) -> SyncResult:
    """Check one lapsed or unpaid membership against Neon and apply what it finds.

    Resolves the member's Neon account first, adopting the surviving ID when
    Neon merged ours away. Then lists the account's memberships; when there
    are none, looks up the membership we store and adopts the account that
    holds it, which covers a duplicate account Neon has not merged yet.
    Picks the membership worth syncing (see ``select_membership_to_sync``),
    syncs it into the local record when it is newer or newly paid, and
    deletes the local record when Neon confirms the lapse and the
    membership ended before ``delete_before``. A failed Neon request is
    logged and reported as FAILED so the caller can move on to the next
    member; any other exception propagates to the caller.

    :param client: The Neon API client.
    :param membership: The local membership to check, with its user and
        profile loaded.
    :param delete_before: Delete confirmed lapses that ended before this
        instant, or None to never delete.
    :return: What happened to the membership.
    """
    user = membership.user
    profile: UserProfile = user.profile  # type: ignore
    if not profile.neon_account_id:
        logger.warning(
            "User %s has a membership but no Neon account ID; skipping.",
            user.username,
        )
        return SyncResult.SKIPPED

    try:
        account_id = resolve_neon_account(client, membership)
        if account_id is None:
            return SyncResult.SKIPPED
        memberships = client.get_account_memberships(account_id)
        if not memberships:
            holder_id = find_membership_account(client, membership)
            if holder_id and holder_id != account_id:
                reason = f"it holds membership {membership.neon_id}"
                if not adopt_neon_account(membership, holder_id, reason):
                    return SyncResult.SKIPPED
                memberships = client.get_account_memberships(holder_id)
    except requests.RequestException as e:
        logger.warning(
            "Neon API request failed for account %s (user %s): %s",
            profile.neon_account_id,
            user.username,
            e,
        )
        return SyncResult.FAILED

    neon_membership = select_membership_to_sync(memberships)
    if neon_membership is None:
        logger.debug("Neon has no memberships for user %s.", user.username)
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


def sync_memberships(
    min_hours: int,
    max_days: int | None,
    delete_after_days: int,
) -> Counter[SyncResult]:
    """Check expired and unpaid memberships against Neon and sync their data.

    Each membership costs one API request. One bad record must not stop the
    run: a failed Neon request is logged as a warning, and any other error
    while handling a membership is logged with its traceback, so it reaches
    Sentry, and counted as FAILED.

    Memberships confirmed to have no active membership are deleted once
    they have been expired for at least delete_after_days. Set this value
    to 0 to disable deletion.

    :param min_hours: See `get_memberships_to_check`.
    :param max_days: See `get_memberships_to_check`.
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
    for membership in get_memberships_to_check(min_hours, max_days):
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
    """Re-sync Neon memberships that webhooks may have missed."""

    help = (
        "Check expired memberships, and memberships whose payment is not "
        "SUCCEEDED, against the Neon API; update the local record and API "
        "throttles when Neon shows a newer or newly paid membership, and "
        "delete expired memberships Neon confirms once they are a week old. "
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-hours-expired",
            type=int,
            default=24,
            help="Only check memberships that expired, or whose unpaid "
            "record last changed, at least this many hours ago, giving Neon "
            "time to process auto-renewals, retry charges and send webhooks "
            "first. Default: 24.",
        )
        parser.add_argument(
            "--max-days-expired",
            type=int,
            default=90,
            help="Only check memberships whose termination date is at most "
            "this many days in the past, bounding the number of Neon API "
            "calls per run. Unpaid memberships with a future term always "
            "qualify. Pass 0 to remove the limit for a full clean-up. "
            "Default: 90.",
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
        counts = sync_memberships(
            options["min_hours_expired"],
            max_days_expired if max_days_expired > 0 else None,
            delete_after_days,
        )
        self.stdout.write(
            f"Checked {sum(counts.values())} memberships: "
            f"{counts[SyncResult.UPDATED]} updated, "
            f"{counts[SyncResult.DELETED]} deleted, "
            f"{counts[SyncResult.SKIPPED]} skipped, "
            f"{counts[SyncResult.FAILED]} failed."
        )
