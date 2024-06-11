from functools import partial

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from cl.corpus_importer.tasks import make_docket_by_iquery_sweep
from cl.lib.redis_utils import (
    acquire_redis_lock,
    get_redis_interface,
    make_update_pacer_case_id_key,
    release_redis_lock,
)
from cl.search.models import Court, Docket


def update_latest_case_id_and_schedule_iquery_sweep(docket: Docket) -> None:
    """Updates the latest PACER case ID and schedules iquery retrieval tasks.

    :param docket: The incoming Docket instance.
    :return: None
    """

    r = get_redis_interface("CACHE")
    court_id = str(docket.court_id)
    # Get the latest pacer_case_id from Redis using a lock to avoid race conditions
    # when getting and updating it.
    update_lock_key = make_update_pacer_case_id_key(court_id)
    # ttl one hour.
    lock_value = acquire_redis_lock(r, update_lock_key, 60 * 1000)

    highest_known_pacer_case_id = int(
        r.hget("highest_known_pacer_case_id", court_id) or 0
    )
    iquery_pacer_case_id_current = int(
        r.hget("iquery_pacer_case_id_current", court_id) or 0
    )
    incoming_pacer_case_id = int(docket.pacer_case_id)
    found_higher_case_id = False
    if incoming_pacer_case_id > highest_known_pacer_case_id:
        r.hset("highest_known_pacer_case_id", court_id, incoming_pacer_case_id)
        found_higher_case_id = True

    if found_higher_case_id:
        task_scheduled_countdown = 0

        while iquery_pacer_case_id_current + 1 < incoming_pacer_case_id:
            iquery_pacer_case_id_current += 1
            task_scheduled_countdown += 1
            # Schedule the next task with a 1-second countdown increment
            make_docket_by_iquery_sweep.apply_async(
                args=(court_id, iquery_pacer_case_id_current),
                kwargs={"avoid_trigger_signal": True},
                countdown=task_scheduled_countdown,
                queue=settings.CELERY_IQUERY_QUEUE,
            )

        # Update the iquery_pacer_case_id_current in Redis
        r.hset(
            "iquery_pacer_case_id_current",
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
        instance, "avoid_trigger_signal", True
    ):
        # If the signal is disabled for uploads in general and the instance
        # doesn't have avoid_trigger_signal set, abort it. This is a Docket
        # created by an upload or another RECAP source different from the
        # iquery probe daemon.
        return None

    if getattr(instance, "avoid_trigger_signal", False):
        # This is an instance added by the iquery_pages_probe task
        # or the iquery sweep scraper that should be ignored (no the highest
        # pacer_case_id)
        return None

    # Only call update_latest_case_id_and_schedule_iquery_sweep if this is a
    # new RECAP district or bankruptcy docket with pacer_case_id not added by
    # iquery sweep tasks.
    if (
        created
        and instance.pacer_case_id
        and getattr(instance, "court", None)
        and instance.court_id
        in list(
            Court.federal_courts.district_or_bankruptcy_pacer_courts()
            .exclude(pk__in=["uscfc", "arb", "cit"])
            .values_list("pk", flat=True)
        )
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
