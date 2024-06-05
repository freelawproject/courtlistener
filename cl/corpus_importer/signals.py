from functools import partial

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from cl.corpus_importer.tasks import make_docket_by_iquery
from cl.lib.redis_utils import (
    acquire_atomic_redis_lock,
    get_redis_interface,
    make_update_pacer_case_id_key,
    release_atomic_redis_lock,
)
from cl.search.models import Court, Docket


def update_latest_case_id_and_schedule_iquery_sweep(docket: Docket) -> None:
    """Updates the latest PACER case ID and schedules iquery retrieval tasks.

    :param docket: The incoming Docket instance.
    :return: None
    """

    r = get_redis_interface("CACHE")
    court_id = docket.court.pk
    # Get the latest pacer_case_id from Redis using a lock to avoid race conditions
    # when getting and updating it.
    update_lock_key = make_update_pacer_case_id_key(court_id)
    # ttl one hour.
    lock_value = acquire_atomic_redis_lock(r, update_lock_key, 60 * 60 * 1000)

    current_iquery_pacer_case_id_final = int(
        r.hget("iquery_pacer_case_id_final", court_id) or 0
    )
    iquery_pacer_case_id_status = int(
        r.hget("iquery_pacer_case_id_status", court_id) or 0
    )
    incoming_pacer_case_id = int(docket.pacer_case_id)
    updated_pacer_case_id = False
    if incoming_pacer_case_id > current_iquery_pacer_case_id_final:
        r.hset("iquery_pacer_case_id_final", court_id, incoming_pacer_case_id)
        updated_pacer_case_id = True

    if updated_pacer_case_id:
        task_scheduled_countdown = 0

        while iquery_pacer_case_id_status + 1 < incoming_pacer_case_id:
            tasks_processed_in_this_batch = 0

            # Schedule tasks in batches of IQUERY_SWEEP_BATCH_SIZE to avoid
            # a celery runaway scheduling tasks with countdowns larger than
            # the celery visibility_timeout.
            while (
                tasks_processed_in_this_batch
                < settings.IQUERY_SWEEP_BATCH_SIZE
                and iquery_pacer_case_id_status + 1 < incoming_pacer_case_id
            ):
                iquery_pacer_case_id_status += 1
                tasks_processed_in_this_batch += 1
                task_scheduled_countdown += 1
                # Schedule the next task with a 1-second countdown increment
                make_docket_by_iquery.apply_async(
                    args=(court_id, iquery_pacer_case_id_status),
                    kwargs={"from_iquery_scrape": True},
                    countdown=task_scheduled_countdown,
                )

            # Update the status in Redis after each batch
            r.hset(
                "iquery_pacer_case_id_status",
                court_id,
                iquery_pacer_case_id_status,
            )

    # Release the lock once the whole process is complete.
    release_atomic_redis_lock(r, update_lock_key, lock_value)


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

    if hasattr(instance, "from_iquery_scrape") and instance.from_iquery_scrape:
        # Early abort if this is an instance added by the iquery probing task
        # or the iquery sweep scraper.
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
