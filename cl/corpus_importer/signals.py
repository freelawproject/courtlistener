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
from cl.search.models import Docket


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
    lock_value = acquire_atomic_redis_lock(r, update_lock_key, 1000)

    current_pacer_case_id_final = int(
        r.hget("pacer_case_id_final", court_id) or 0
    )
    incoming_pacer_case_id = int(docket.pacer_case_id)
    updated_pacer_case_id = False
    if incoming_pacer_case_id > current_pacer_case_id_final:
        r.hset("pacer_case_id_final", court_id, incoming_pacer_case_id)
        updated_pacer_case_id = True
    # Release the lock once the pacer_case_id_final update process is complete.
    release_atomic_redis_lock(r, update_lock_key, lock_value)

    if updated_pacer_case_id:
        task_scheduled_countdown = 0
        while current_pacer_case_id_final + 1 < incoming_pacer_case_id:
            current_pacer_case_id_final += 1
            task_scheduled_countdown += 1
            make_docket_by_iquery.apply_async(
                args=(court_id, current_pacer_case_id_final),
                kwargs={"from_iquery_sweep": True},
                countdown=task_scheduled_countdown,
            )


@receiver(
    post_save,
    sender=Docket,
    dispatch_uid="handle_update_latest_case_id_and_schedule_iquery_sweep",
)
def handle_update_latest_case_id_and_schedule_iquery_sweep(
    sender, instance: Docket, created=False, update_fields=None, **kwargs
):
    """post_save Docket signal receiver to handle
    update_latest_case_id_and_schedule_iquery_sweep
    """

    from_iquery_sweep = False
    if hasattr(instance, "from_iquery_sweep"):
        from_iquery_sweep = instance.from_iquery_sweep

    # Only call update_latest_case_id_and_schedule_iquery_sweep if this is a
    # new RECAP docket with pacer_case_id not added by iquery sweep tasks or
    # iquery_pages_probing.
    if (
        created
        and not from_iquery_sweep
        and instance.source in Docket.RECAP_SOURCES()
        and instance.pacer_case_id
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
