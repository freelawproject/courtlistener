from functools import partial

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from cl.corpus_importer.tasks import make_docket_by_iquery_sweep
from cl.corpus_importer.utils import get_iquery_pacer_courts_to_scrape
from cl.lib.command_utils import logger
from cl.lib.redis_utils import (
    acquire_redis_lock,
    get_redis_interface,
    make_update_pacer_case_id_key,
    release_redis_lock,
)
from cl.search.models import Docket


def update_latest_case_id_and_schedule_iquery_sweep(
    docket: Docket | None,
    court_pk: str | None = None,
    fixed_case_id_sweep: int | None = None,
) -> None:
    """Updates the latest PACER case ID and schedules iquery retrieval tasks.

    Note: Provide either a Docket instance or a court_id with fixed_case_id_sweep.

    :param docket: The Docket instance, if triggered by a Docket post_save signal.
    :param court_pk: The court ID, if triggered in fixed sweep mode.
    :param fixed_case_id_sweep: The target case ID for performing a fixed sweep.
    :return: None
    """

    r = get_redis_interface("CACHE")
    court_id: str
    incoming_pacer_case_id: int
    if docket is not None:
        court_id = docket.court_id
        incoming_pacer_case_id = int(docket.pacer_case_id)
    elif court_pk is not None and fixed_case_id_sweep is not None:
        court_id = court_pk
        incoming_pacer_case_id = fixed_case_id_sweep
    else:
        raise ValueError(
            "Provide either a Docket instance or court_id + fixed_case_id_sweep"
        )

    # Get the latest pacer_case_id from Redis using a lock to avoid race conditions
    # when getting and updating it.
    update_lock_key = make_update_pacer_case_id_key(court_id)
    # ttl one hour.
    lock_value = acquire_redis_lock(r, update_lock_key, 60 * 1000)

    highest_known_pacer_case_id = int(
        r.hget("iquery:highest_known_pacer_case_id", court_id) or 0
    )
    iquery_pacer_case_id_current = int(
        r.hget("iquery:pacer_case_id_current", court_id) or 0
    )
    found_higher_case_id = False
    if incoming_pacer_case_id > highest_known_pacer_case_id:
        found_higher_case_id = True

    if found_higher_case_id:
        tasks_to_schedule = (
            incoming_pacer_case_id - iquery_pacer_case_id_current
        )
        logger.info(
            "Found %s %s tasks to schedule for pacer case IDs ranging from %s to %s.",
            tasks_to_schedule,
            court_id,
            iquery_pacer_case_id_current,
            incoming_pacer_case_id,
        )
        if (
            tasks_to_schedule
            > settings.IQUERY_PROBE_MAX_OFFSET + settings.IQUERY_MAX_PROBE
        ):
            # Don't schedule more than IQUERY_PROBE_MAX_OFFSET tasks at a time
            # to prevent Redis from being filled up.
            # It's safer to abort if more than 600 tasks are attempted to be
            # scheduled. This could indicate an issue with retrieving the
            # highest_known_pacer_case_id or a loss of the
            # iquery_pacer_case_id_current for the court in Redis.
            logger.error(
                "Tried to schedule more than %s iquery pages to scrape for "
                "court %s; aborting to avoid Redis memory exhaustion.",
                tasks_to_schedule,
                court_id,
            )
            release_redis_lock(r, update_lock_key, lock_value)
            return None

        r.hset(
            "iquery:highest_known_pacer_case_id",
            court_id,
            incoming_pacer_case_id,
        )
        task_to_schedule_count = 0
        while iquery_pacer_case_id_current + 1 < incoming_pacer_case_id:
            iquery_pacer_case_id_current += 1
            task_to_schedule_count += 1
            # Schedule the next task.
            make_docket_by_iquery_sweep.apply_async(
                args=(court_id, iquery_pacer_case_id_current),
                kwargs={"skip_iquery_sweep": True},
                queue=settings.CELERY_IQUERY_QUEUE,
            )
            logger.info(
                "Enqueued %s iquery docket with case ID: %s for court %s",
                task_to_schedule_count,
                iquery_pacer_case_id_current,
                court_id,
            )

        # Update the iquery_pacer_case_id_current in Redis
        r.hset(
            "iquery:pacer_case_id_current",
            court_id,
            iquery_pacer_case_id_current,
        )

    # Release the lock once the whole process is complete.
    release_redis_lock(r, update_lock_key, lock_value)


@receiver(
    post_save,
    sender=Docket,
    dispatch_uid="handle_update_latest_case_id_and_schedule_iquery_sweep",
)
def handle_update_latest_case_id_and_schedule_iquery_sweep(
    sender, instance: Docket, created=False, update_fields=None, **kwargs
) -> None:
    """post_save Docket signal receiver to handle
    update_latest_case_id_and_schedule_iquery_sweep
    """

    if not settings.IQUERY_SWEEP_UPLOADS_SIGNAL_ENABLED and getattr(
        instance, "skip_iquery_sweep", True
    ):
        # If the signal is disabled for uploads in general and the instance
        # doesn't have skip_iquery_sweep set, abort it. This is a Docket
        # created by an upload or another RECAP source different from the
        # iquery probe daemon.
        return None

    if getattr(instance, "skip_iquery_sweep", False):
        # This is an instance added by the probe_or_scrape_iquery_pages task
        # or the iquery sweep scraper that should be ignored (no the highest
        # pacer_case_id)
        return None

    # Only call update_latest_case_id_and_schedule_iquery_sweep if:
    # - The docket belongs to a RECAP district or bankruptcy court,
    # - The docket has a pacer_case_id,
    # - The docket was newly created (when IQUERY_SWEEP_UPLOADS_SIGNAL_ENABLED=True), or
    # - The docket was created or updated by the last probe iteration from probe_or_scrape_iquery_pages.
    check_probe_or_created = (
        not getattr(instance, "skip_iquery_sweep", False) or created
    )
    if (
        check_probe_or_created
        and instance.pacer_case_id
        and instance.court_id in get_iquery_pacer_courts_to_scrape()
    ):
        transaction.on_commit(
            partial(update_latest_case_id_and_schedule_iquery_sweep, instance)
        )


if settings.TESTING:
    # Disconnect handle_update_latest_case_id_and_schedule_iquery_sweep
    # for all tests. It will be enabled only for tests where it is required.
    post_save.disconnect(
        sender=Docket,
        dispatch_uid="handle_update_latest_case_id_and_schedule_iquery_sweep",
    )
