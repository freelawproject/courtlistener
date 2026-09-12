import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Exists, OuterRef, QuerySet
from django.utils import timezone
from oauth2_provider.models import (
    clear_expired,
    get_access_token_model,
    get_application_model,
    get_grant_model,
    get_id_token_model,
    get_refresh_token_model,
)
from oauth2_provider.settings import oauth2_settings

logger = logging.getLogger(__name__)

Application = get_application_model()
TOKEN_MODELS = (
    get_grant_model(),
    get_access_token_model(),
    get_refresh_token_model(),
    get_id_token_model(),
)


def _delete_in_batches(
    candidates: QuerySet,
    *,
    what: str,
    batch_size: int,
    pause_seconds: float,
    dry_run: bool,
) -> int:
    """Delete ``candidates`` in pk-ordered batches and return how many rows of
    its model were (or, with ``dry_run``, would be) deleted.
    """
    if dry_run:
        count = candidates.count()
        logger.info("Dry run: %s %s would be deleted.", count, what)
        return count

    label = candidates.model._meta.label
    total = 0
    while pks := list(
        candidates.order_by("pk").values_list("pk", flat=True)[:batch_size]
    ):
        # Re-apply filter so that rows that stopped qualifying aren't deleted.
        _, deleted_by_model = candidates.filter(pk__in=pks).delete()
        deleted = deleted_by_model.get(label, 0)
        total += deleted
        logger.info("Deleted %s %s (%s this pass).", deleted, what, total)
        if len(pks) < batch_size:
            break
        time.sleep(pause_seconds)
    return total


def unconfirmed_applications(
    min_age: timedelta, max_age: timedelta | None = None
) -> QuerySet:
    """DCR applications no user ever authorized: no owner, no
    ``skip_authorization``, no grant or token rows, older than ``min_age``,
    younger than ``max_age``.
    """
    if max_age is not None and max_age <= min_age:
        logger.warning(
            "max_age (%s) is not greater than min_age (%s); no application "
            "can match both bounds and none will be deleted.",
            max_age,
            min_age,
        )
    now = timezone.now()
    candidates = Application.objects.filter(
        user__isnull=True,
        skip_authorization=False,
        created__lt=now - min_age,
    )
    if max_age is not None:
        candidates = candidates.filter(created__gte=now - max_age)
    for model in TOKEN_MODELS:
        candidates = candidates.filter(
            ~Exists(model.objects.filter(application_id=OuterRef("pk")))
        )
    return candidates


def delete_unconfirmed_applications(
    *,
    min_age: timedelta,
    max_age: timedelta | None = None,
    batch_size: int,
    pause_seconds: float,
    dry_run: bool = False,
) -> int:
    """Delete never-authorized DCR applications in batches."""
    return _delete_in_batches(
        unconfirmed_applications(min_age, max_age),
        what="unconfirmed OAuth applications",
        batch_size=batch_size,
        pause_seconds=pause_seconds,
        dry_run=dry_run,
    )


def refresh_token_lifetime() -> timedelta | None:
    """Return the configured refresh-token lifetime as a timedelta.

    This reads from ``oauth2_settings`` to stay consistent with
    ``clear_expired()``, which reads the same setting when deciding whether
    expired refresh tokens should be removed.

    If the setting is unset or falsy, return ``None`` to match the toolkit's
    default. In that case, ``clear_expired()`` does not expire refresh tokens,
    so no lifetime cap is needed.
    """

    lifetime = oauth2_settings.REFRESH_TOKEN_EXPIRE_SECONDS
    if not lifetime:
        return None
    if isinstance(lifetime, timedelta):
        return lifetime
    if isinstance(lifetime, int | float):
        return timedelta(seconds=lifetime)
    # Mirror clear_expired()'s own error, which would otherwise surface later
    # in the pass, after applications had already been deleted.
    raise ImproperlyConfigured(
        "REFRESH_TOKEN_EXPIRE_SECONDS must be either a timedelta or seconds"
    )


def clear_expired_tokens() -> None:
    """Run django-oauth-toolkit's ``clear_expired()`` and log the elapsed time."""
    start = time.monotonic()
    clear_expired()
    logger.info("clear_expired() finished in %.1fs.", time.monotonic() - start)


def run_cleanup_pass(*, dry_run: bool = False) -> None:
    """One cleanup pass over the OAuth tables."""
    delete_unconfirmed_applications(
        min_age=timedelta(
            hours=settings.OAUTH_CLEANUP_UNCONFIRMED_APP_MIN_AGE_HOURS
        ),
        # See issue #7796. In the follow-up PR, we will use this:
        # max_age=timedelta(
        #     seconds=settings.OAUTH2_PROVIDER["REFRESH_TOKEN_EXPIRE_SECONDS"]
        # ),
        max_age=None,
        batch_size=settings.OAUTH_CLEANUP_BATCH_SIZE,
        pause_seconds=settings.OAUTH_CLEANUP_BATCH_PAUSE,
        dry_run=dry_run,
    )
    # See issue #7796. In the follow-up PR, we will uncomment this:
    # if not dry_run:
    #     clear_expired_tokens()
