from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import QuerySet

from cl.citations.group_parentheticals import compute_parenthetical_groups
from cl.search.models import OpinionCluster, ParentheticalGroup


async def get_or_create_parenthetical_groups(
    cluster: OpinionCluster,
) -> QuerySet[ParentheticalGroup]:
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
