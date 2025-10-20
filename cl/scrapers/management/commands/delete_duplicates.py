import importlib
from collections import defaultdict

from django.db import transaction
from django.db.models import Count, Q
from django.utils.encoding import force_bytes
from juriscraper.OpinionSite import OpinionSite

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.crypto import sha1
from cl.scrapers.exceptions import MergingError
from cl.scrapers.management.commands.merge_opinion_versions import (
    comparable_dockets,
    get_query_from_url,
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

    # Can happen due to duplicates already being grouped in the same cluster
    # by versioning
    is_same_cluster = (
        opinion_to_keep.cluster.id == opinion_to_delete.cluster.id
    )
    if is_same_cluster:
        cluster_needs_update = False
        stats["same cluster"] += 1
    else:
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

    update_referencing_objects(opinion_to_keep, opinion_to_delete)

    if not is_same_cluster:
        update_referencing_objects(
            opinion_to_keep.cluster, opinion_to_delete.cluster
        )
    if not is_same_docket:
        update_referencing_objects(
            opinion_to_keep.cluster.docket, opinion_to_delete.cluster.docket
        )

    cluster_to_delete = opinion_to_delete.cluster

    # delete opinion
    opinion_to_delete.delete()
    stats["deleted opinion"] += 1

    # delete cluster
    docket_to_delete = cluster_to_delete.docket
    if not is_same_cluster:
        ClusterRedirection.create_from_clusters(
            opinion_to_keep.cluster,
            cluster_to_delete,
            ClusterRedirection.DUPLICATE,
        )
        cluster_to_delete.delete()
        stats["deleted cluster"] += 1

    if not is_same_docket:
        docket_to_delete.delete()
        stats["deleted docket"] += 1

    if opinion_needs_update:
        logger.info("Updating opinion %s", opinion_to_keep.id)
        opinion_to_keep.save()

    if cluster_needs_update:
        logger.info("Updating cluster %s", opinion_to_keep.cluster.id)
        opinion_to_keep.cluster.save()

    if docket_needs_update:
        logger.info("Updating docket %s", opinion_to_keep.cluster.docket.id)
        opinion_to_keep.cluster.docket.save()


def delete_same_hash_duplicates(
    stats: defaultdict, sources: list[str]
) -> None:
    """Delete opinions with the same hash, and their related objects

    :param stats: a dictionary to count events
    :param sources: a list of OpinionCluster.source values

    :return None
    """
    # Group opinions by hash
    # Keep the groups with a single hash, and more than 1 row
    # these are same-hash duplicates
    if len(sources) == 1:
        if sources[0] == "ALL":
            source_filter = {}
        else:
            source_filter = {"cluster__source": sources[0]}
    else:
        source_filter = {"cluster__source__in": sources}

    qs = (
        Opinion.objects.filter(**source_filter)
        .exclude(sha1="")
        .values("sha1")
        .annotate(
            number_of_rows=Count("sha1"),
        )
        .order_by()
        .filter(number_of_rows__gte=2)
    )
    logger.info("Groups to process %s for sources %s", qs.count(), sources)

    for group in qs:
        logger.info("Processing group %s", group)

        duplicate_candidates = list(
            Opinion.objects.filter(sha1=group["sha1"])
            .filter(**source_filter)
            .order_by("-date_created")
            .select_related("cluster", "cluster__docket")
        )

        # for each hash group, try to compare all opinions with the latest
        # opinion. If they are duplicates, delete them. If not, put them apart
        # so they are compared amongst them
        while duplicate_candidates:
            op_to_keep = duplicate_candidates[0]
            candidates_left = []

            for op_to_delete in duplicate_candidates[1:]:
                if not comparable_dockets(
                    op_to_keep.cluster.docket, op_to_delete.cluster.docket
                ):
                    logger.info(
                        "Not the same docket. Docket to keep: %s. Docket to delete: %s",
                        op_to_keep.cluster.docket.id,
                        op_to_delete.cluster.docket.id,
                    )
                    stats["not comparable docket"] += 1
                    candidates_left.append(op_to_delete)
                    continue

                try:
                    with transaction.atomic():
                        delete_duplicate_opinion(
                            op_to_keep, op_to_delete, True, stats
                        )
                except MergingError:
                    stats["merging error"] += 1
                    candidates_left.append(op_to_delete)

            # if nothing was put into `candidates_left`, while loop will exit
            duplicate_candidates = candidates_left


def get_cleaned_content_hash(opinion: Opinion, site: OpinionSite) -> str:
    """Computes the hash over the cleaned up opinion content

    :param opinion: the opinion
    :param site: the juriscraper site
    :return: the sha1 hash
    """
    content = opinion.local_path.read()
    return sha1(force_bytes(site.cleanup_content(content)))


def delete_cleaned_up_content_duplicates(
    stats: defaultdict, court_id: str, site: OpinionSite
) -> None:
    """Get duplicate candidate groups and check if their hashes are the same
    after applying `Site.cleanup_content` from the proper juriscraper module

    This is mostly reusing logic from `merge_opinion_versions_by_download_url`.
    Since this are different hash duplicates, they sort of look like versions,
    since they have different hashes. However, once `Site.cleanup_content` is
    applied, they will be identical, which is the difference

    We filter by `download_url` because grouping by local path will need
    `local_path` string manipulation to drop the index _1, _2, _3 which may
    become costy

    :param stats: stats dictionary for reporting
    :param court_id: a court id to group opinions by
    :param site: a juriscraper Site with a `cleanup_content` method
    """
    qs = (
        Opinion.objects.filter(
            cluster__docket__court_id=court_id,
            cluster__source=SOURCES.COURT_WEBSITE,
        )
        .exclude(Q(download_url="") | Q(download_url__isnull=True))
        .values("download_url")
        .annotate(
            number_of_rows=Count("download_url"),
            number_of_hashes=Count("sha1", distinct=True),
        )
        .order_by()
        .filter(number_of_rows__gte=2, number_of_hashes__gte=2)
    )

    seen_urls = set()

    for group in qs:
        standard_url = group["download_url"].replace("https", "http")
        if standard_url in seen_urls:
            continue
        seen_urls.add(standard_url)

        logger.info("Processing group %s", group)

        download_url_query = get_query_from_url(group["download_url"], "exact")

        duplicate_candidates = (
            Opinion.objects.filter(download_url_query)
            .filter(cluster__source=SOURCES.COURT_WEBSITE)
            .select_related("cluster", "cluster__docket")
            .order_by("-date_created")
        )

        # iteration is ordered by descending date; the first element in each
        # hash group is the most recent opinion and duplicates should be
        # collapsed into it
        hash_groups = defaultdict(lambda: [])
        file_errors = 0
        for opinion in duplicate_candidates:
            try:
                sha1 = get_cleaned_content_hash(opinion, site)
                hash_groups[sha1].append(opinion)
            except FileNotFoundError:
                # See #6400
                logger.error(
                    "Opinion file not found %s '%s'",
                    opinion.id,
                    opinion.local_path,
                    exc_info=True,
                )
                file_errors += 1

        logger.info("%s hash groups", len(hash_groups))
        # log the whole group for debugging different hashes after cleanup
        logger.debug(hash_groups)

        if file_errors:
            logger.info("%s file errors", file_errors)

        for main_opinion, *duplicate_opinions in hash_groups.values():
            for duplicate in duplicate_opinions:
                try:
                    with transaction.atomic():
                        delete_duplicate_opinion(
                            main_opinion, duplicate, True, stats
                        )
                except MergingError:
                    stats["merging error"] += 1


class Command(VerboseCommand):
    help = "Find and merge Opinion objects that are versions of each other"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "method",
            choices=["same_hash", "cleanup_content"],
            help="""Supported duplicate finding methods:
            - 'same_hash' will look for opinions with the exact same hash.
            - 'cleanup_content' will group opinions by `court_id` and `download_url`
            and use the `Site.cleanup_content` in the `juriscraper_module` to
            cleanup the raw content and recompute the hash. If they are the same
            and other checks are OK, it will delete the duplicates.
            """,
        )
        parser.add_argument(
            "--cluster-sources",
            choices=list(SOURCES.parts_to_source_mapper.values()) + ["ALL"],
            default=[SOURCES.COURT_WEBSITE],
            nargs="*",
            help="""`OpinionCluster.source` values to include when finding
            duplicate groups. Pass `ALL` if you want to include all sources.""",
        )
        parser.add_argument(
            "--court-id",
            default="",
            help="""`Docket.court_id` to find duplicate candidate groups when
            using the `cleanup_content` method""",
        )
        parser.add_argument(
            "--juriscraper-module",
            default="",
            help="""Juriscraper path of the `Site.cleanup_content` method that
            will be used when using the `cleanup_content` method""",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        stats = defaultdict(lambda: 0)
        method = options["method"]
        if method == "same_hash":
            try:
                delete_same_hash_duplicates(stats, options["cluster_sources"])
            finally:
                logger.info(stats)

        elif method == "cleanup_content":
            juriscraper_module = options["juriscraper_module"]
            court_id = options["court_id"]
            if not (juriscraper_module and court_id):
                raise ValueError(
                    "Both `juriscraper-path` and `court-id` should have values when using `cleanup_content`"
                )

            # check that the module path is valid
            site = importlib.import_module(juriscraper_module).Site()

            # check that `cleanup_content` is implemented
            if site.cleanup_content == OpinionSite.cleanup_content:
                raise ValueError(
                    f"`cleanup_content` is not implemented for {juriscraper_module}"
                )

            try:
                delete_cleaned_up_content_duplicates(stats, court_id, site)
            finally:
                logger.info(stats)

        else:
            raise ValueError(f"Unsupported `method` value {method}")
