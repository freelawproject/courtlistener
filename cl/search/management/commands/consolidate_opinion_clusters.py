from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from cl.lib.command_utils import logger
from cl.scrapers.management.commands.merge_opinion_versions import (
    merge_metadata,
    update_referencing_objects,
)
from cl.search.models import (
    SOURCES,
    ClusterRedirection,
    Opinion,
    OpinionCluster,
)

# Courts that support ClusterSite in juriscraper (non-exhaustive list):
# - conn (Connecticut Supreme Court)
# - connctapp (Connecticut Appellate Court)
# - michctapp (Michigan Court of Appeals)
# - tex (Texas Supreme Court)
# - texapp (Texas Courts of Appeals)
# - wva (West Virginia Supreme Court of Appeals)
# - wvactapp (West Virginia Intermediate Court of Appeals)
# - haw (Hawaii Supreme Court)
# - hawctapp (Hawaii Intermediate Court of Appeals)


class Command(BaseCommand):
    help = "Consolidates spread opinion clusters into a single cluster."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "court_id",
            help="The court id to process (e.g. texapp)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the command without making any changes to the database.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Limit the number of groups to process.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        court_id = options["court_id"]
        dry_run = options["dry_run"]
        limit = options["limit"]

        logger.info("Finding candidates for consolidation in %s...", court_id)

        # We find groups of clusters that share the same date_filed, case_name, and docket_number
        # and were scraped from the court website.
        candidate_groups = (
            OpinionCluster.objects.filter(
                docket__court_id=court_id, source=SOURCES.COURT_WEBSITE
            )
            .values("date_filed", "case_name", "docket__docket_number")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
            .order_by("-date_filed")
        )

        if limit:
            candidate_groups = candidate_groups[:limit]

        logger.info("Found %s groups to process.", len(candidate_groups))

        for candidate_group in candidate_groups:
            self.consolidate_group(candidate_group, court_id, dry_run)

    def consolidate_group(
        self, candidate_group: dict[str, Any], court_id: str, dry_run: bool
    ) -> None:
        """Consolidate a group of opinion clusters into a single one.

        :param candidate_group: a dictionary with the fields that define the group
        :param court_id: the court id of the group
        :param dry_run: if True, do not save changes to the database
        :return: None
        """
        date_filed = candidate_group["date_filed"]
        case_name = candidate_group["case_name"]
        docket_number = candidate_group["docket__docket_number"]

        # Fetch the clusters in the group
        clusters = (
            OpinionCluster.objects.filter(
                date_filed=date_filed,
                case_name=case_name,
                docket__docket_number=docket_number,
                docket__court_id=court_id,
                source=SOURCES.COURT_WEBSITE,
            )
            .order_by("id")
            .prefetch_related("sub_opinions")
        )

        if len(clusters) < 2:
            return

        logger.info(
            "Processing group: %s (%s) - %s - %s clusters",
            case_name,
            date_filed,
            docket_number,
            len(clusters),
        )

        all_opinions = []
        cluster_to_keep, *clusters_to_delete = list(clusters)
        for cluster in clusters:
            for opinion in cluster.sub_opinions.all():
                opinion.cluster = cluster_to_keep

                # We need to assign the type in order to set the proper
                # ordering_key. Ordering should wait until we have all the types
                if opinion.type != Opinion.COMBINED:
                    opinion.type = self.parse_opinion_type_from_text(opinion)

                opinion.ordering_key = None
                all_opinions.append(opinion)

        # Fix ordering based on Opinion.type
        # Order: combined < lead < concurrence < dissent
        all_opinions.sort(key=lambda o: (o.type, o.id))
        current_ordering_key = 1
        for opinion in all_opinions:
            opinion.ordering_key = current_ordering_key
            current_ordering_key += 1

        if dry_run:
            logger.info(
                "  [DRY RUN] Would keep cluster %s and merge %s clusters into it.",
                cluster_to_keep.id,
                len(clusters_to_delete),
            )
            return

        with transaction.atomic():
            try:
                self.consolidate_clusters(
                    cluster_to_keep, clusters_to_delete, all_opinions
                )
            except Exception as e:
                logger.error("Error consolidating clusters", exc_info=e)

    def consolidate_clusters(
        self,
        cluster_to_keep: OpinionCluster,
        clusters_to_delete: list[OpinionCluster],
        all_opinions: list[Opinion],
    ) -> None:
        """Merge metadata; update referencing objects; delete orphaned clusters and dockets

        :param cluster_to_keep: the cluster that will remain
        :param clusters_to_delete: the clusters that will be deleted
        :param all_opinions: the list of opinions that will be saved
        :return: None
        """
        # let's try to save everything
        changed_main_cluster = False
        changed_main_docket = False

        for cluster in clusters_to_delete:
            # set error_on_diff = True, although there may be some clusters with
            # different date_filed (see example)
            changed_main_cluster = (
                merge_metadata(cluster_to_keep, cluster, True)
                or changed_main_cluster
            )

            # we know docket numbers and court ids are the same
            if cluster_to_keep.docket_id != cluster.docket_id:
                changed_main_docket = (
                    merge_metadata(
                        cluster_to_keep.docket, cluster.docket, True
                    )
                    or changed_main_docket
                )

        # there were no merging conflicts, let's start saving everything
        # this may cause an IntegrityError if any of the opinions already had
        # an ordering_key value. But this shouldn't be the case
        for op in all_opinions:
            op.save()

        if changed_main_cluster:
            cluster_to_keep.save()

        if changed_main_docket:
            cluster_to_keep.docket.save()

        for cluster in clusters_to_delete:
            cluster_id = cluster.id
            update_referencing_objects(cluster_to_keep, cluster)

            if cluster_to_keep.docket_id != cluster.docket_id:
                update_referencing_objects(
                    cluster_to_keep.docket, cluster.docket
                )
                docket_id = cluster.docket.id
                cluster.docket.delete()
                logger.info("  Merged and deleted docket %s", docket_id)

            ClusterRedirection.create_from_clusters(
                cluster_to_keep=cluster_to_keep,
                cluster_to_delete=cluster,
                reason=ClusterRedirection.CONSOLIDATION,
            )

            logger.info("  Merged and deleted cluster %s", cluster_id)
            cluster.delete()

    def parse_opinion_type_from_text(self, opinion: Opinion) -> str:
        """Parse the opinion type from the text. This has to be implemented in
        a per court basis

        :param opinion: the opinion object
        :return: the guessed opinion type
        """
        # TODO: Implement more robust type extraction from text
        text = opinion.html_with_citations or opinion.plain_text or ""
        if not text:
            return Opinion.COMBINED

        head = text[:3000].lower()

        # Simple heuristics based on common patterns
        if "dissent" in head:
            return Opinion.DISSENT
        if "concur" in head:
            return Opinion.CONCURRENCE
        if "majority" in head or "opinion of the court" in head:
            return Opinion.LEAD

        return Opinion.COMBINED
