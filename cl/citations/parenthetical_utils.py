import logging

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import QuerySet
from django.db.models.signals import post_delete, post_save

from cl.citations.group_parentheticals import compute_parenthetical_groups
from cl.search.models import OpinionCluster, ParentheticalGroup

logger = logging.getLogger(__name__)


async def get_or_create_parenthetical_groups(
    cluster: OpinionCluster,
) -> QuerySet[ParentheticalGroup, ParentheticalGroup]:
    """
    Given a cluster, return its existing ParentheticalGroup's from the database
    or compute and store new ones if they do not yet exist or need to be updated.

    :param cluster: An OpinionCluster object
    :return: A list of ParentheticalGroup's for the given cluster
    """
    if await cluster.parentheticals.filter(group__isnull=True).acount():
        await atomic_create_parenthetical_groups(cluster)
    return cluster.parenthetical_groups


@sync_to_async
@transaction.atomic
def atomic_create_parenthetical_groups(cluster: OpinionCluster) -> None:
    create_parenthetical_groups(cluster)


def create_parenthetical_groups(cluster: OpinionCluster) -> None:
    """
    Given a cluster, (re)computes the parenthetical groups for its parentheticals
    and stores them in the database

    :param cluster: An OpinionCluster object
    """
    parentheticals = list(cluster.parentheticals)
    computed_groups = compute_parenthetical_groups(parentheticals)
    # Delete existing parenthetical groups for this cluster
    cluster.parenthetical_groups.delete()
    for cg in computed_groups:
        group_to_create = ParentheticalGroup(
            opinion=cg.representative.described_opinion,
            representative=cg.representative,
            score=cg.score,
            size=cg.size,
        )
        group_to_create.save()
        group_to_create.parentheticals.set(cg.parentheticals)


def disconnect_parenthetical_group_signals() -> None:
    """Disconnect ParentheticalGroup ES indexing on save and delete

    Useful for batch `citations.commands.find_citations` jobs, that use the
    `find_citations_and_parentheticals_for_opinion_by_pks`
    If you use this function somewhere else, use a `try` block with a
    `reconnect_parenthetical_group_signals` on the `finally` clause
    """
    # these functions should be in cl.search.signals; Putting them here to
    # prevent circular imports between cl.search.signals and cl.citations.tasks
    from cl.search.signals import pa_signal_processor

    logger.warning(
        "Disconnecting ParentheticalGroup ES signals. You will need to handle indexing of ParentheticalGroupDocuments yourself"
    )

    model_name = ParentheticalGroup.__name__.lower()
    save_uid = pa_signal_processor.save_uid_template.format(model_name)
    delete_uid = pa_signal_processor.delete_uid_template.format(model_name)
    post_save.disconnect(
        sender=ParentheticalGroup, dispatch_uid=f"{save_uid}_{model_name}"
    )
    post_delete.disconnect(
        sender=ParentheticalGroup, dispatch_uid=f"{delete_uid}_{model_name}"
    )


def reconnect_parenthetical_group_signals() -> None:
    """Reconnect ParentheticalGroup ES indexing on save and delete

    Useful for batch `find_citations` jobs
    """
    # prevent circular imports
    from cl.search.signals import pa_signal_processor

    model_name = ParentheticalGroup.__name__.lower()
    save_uid = pa_signal_processor.save_uid_template.format(model_name)
    delete_uid = pa_signal_processor.delete_uid_template.format(model_name)
    post_save.connect(
        pa_signal_processor.handle_save,
        sender=ParentheticalGroup,
        dispatch_uid=f"{save_uid}_{model_name}",
    )
    post_delete.connect(
        pa_signal_processor.handle_delete,
        sender=ParentheticalGroup,
        dispatch_uid=f"{delete_uid}_{model_name}",
    )
