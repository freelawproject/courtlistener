from collections import defaultdict

from django.db import transaction
from django.db.models import Count, Q

from cl.lib.command_utils import VerboseCommand, logger
from cl.scrapers.exceptions import MergingError
from cl.scrapers.management.commands.merge_opinion_versions import (
    comparable_dockets,
    merge_metadata,
    update_referencing_objects,
)
from cl.search.models import SOURCES, ClusterRedirection, Opinion


def delete_duplicate_opinion(
    opinion_to_keep: Opinion,
    opinion_to_delete: Opinion,
    strict_merging: bool,
    stats: defaultdict,
) -> None:
    """Deletes a duplicate opinion and cluster, saving it's metadata

    :param opinion_to_keep: the opinion to keep
    :param opinion_to_delete: the opinion that will be deleted
    :param strict_merging: raise an error if there is any difference in
        related metadata
    :param stats: a dict to count events

    :return None
    """
    # merge all metadata
    opinion_needs_update = merge_metadata(
        opinion_to_keep, opinion_to_delete, strict_merging
    )
    cluster_needs_update = merge_metadata(
        opinion_to_keep.cluster, opinion_to_delete.cluster, strict_merging
    )
    is_same_docket = (
        opinion_to_keep.cluster.docket.id
        == opinion_to_delete.cluster.docket.id
    )

    if is_same_docket:
        docket_needs_update = False
        stats["same docket"] += 1
    else:
        docket_needs_update = merge_metadata(
            opinion_to_keep.cluster.docket,
            opinion_to_delete.cluster.docket,
            strict_merging,
        )

    update_referencing_objects(
        opinion_to_keep.cluster, opinion_to_delete.cluster
    )
    if not is_same_docket:
        update_referencing_objects(
            opinion_to_keep.cluster.docket, opinion_to_delete.cluster.docket
        )

    # delete opinion
    cluster_to_delete = opinion_to_delete.cluster
    opinion_to_delete.delete()

    # delete cluster
    docket_to_delete = opinion_to_delete.cluster.docket
    ClusterRedirection.create_from_clusters(
        opinion_to_keep.cluster,
        cluster_to_delete,
        ClusterRedirection.DUPLICATE,
    )
    cluster_to_delete.delete()

    stats["deleted opinion"] += 1
    stats["deleted cluster"] += 1

    if not is_same_docket:
        stats["deleted docket"] += 1
        docket_to_delete.delete()

    if opinion_needs_update:
        logger.info("Updating opinion %s", opinion_to_keep.id)
        opinion_to_keep.save()

    if cluster_needs_update:
        logger.info("Updating cluster %s", opinion_to_keep.cluster.id)
        opinion_to_keep.cluster.save()

    if docket_needs_update:
        logger.info("Updating docket %s", opinion_to_keep.cluster.docket.id)
        opinion_to_keep.cluster.docket.save()


def delete_same_hash_duplicates(stats: defaultdict) -> None:
    """Delete opinions with the same hash, and their related objects

    :param stats: a dictionary to count events
    :return None
    """
    # Group opinions by hash
    # From scraped sources only
    # Keep the groups with a single hash, and more than 1 row
    # these are same-hash duplicates
    qs = (
        Opinion.objects.filter(cluster__source=SOURCES.COURT_WEBSITE)
        .exclude(
            Q(download_url="") | Q(download_url__isnull=True) | Q(sha1="")
        )
        .values("sha1")
        .annotate(
            number_of_rows=Count("sha1"),
        )
        .order_by()
        .filter(number_of_rows__gte=2)
    )
    logger.info("Groups to process %s", qs.count())

    # for each group, we will keep a single opinion; let's prefer the latest
    for group in qs:
        logger.info("Processing group %s", group)

        op_to_keep, *to_delete = (
            Opinion.objects.filter(sha1=group["sha1"])
            .order_by("-date_created")
            .select_related("cluster", "cluster__docket")
        )

        for op_to_delete in to_delete:
            # check that they have the me docket
            if not comparable_dockets(
                op_to_keep.cluster.docket, op_to_delete.cluster.docket
            ):
                logger.info(
                    "Not the same docket. Docket to keep: %s. Docket to delete: %s",
                    op_to_keep.cluster.docket.id,
                    op_to_delete.cluster.docket.id,
                )
                stats["not comparable docket"] += 1
                continue

            try:
                with transaction.atomic():
                    delete_duplicate_opinion(
                        op_to_keep, op_to_delete, True, stats
                    )
            except MergingError:
                stats["merging error"] += 1


class Command(VerboseCommand):
    help = "Find and merge Opinion objects that are versions of each other"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "method",
            choices=["same_hash"],
            help="""Currently we only support deleting same-hash duplicates
            """,
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        stats = defaultdict(lambda: 0)

        if options["method"] == "same_hash":
            try:
                delete_same_hash_duplicates(stats)
            finally:
                logger.info(stats)

        else:
            raise ValueError("Only `same_hash` method is supported, for now")
