import time

from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import OpinionCluster, OpinionsCited


class Command(VerboseCommand):
    help = "Update the citation counts of all items, if they are wrong."

    def add_arguments(self, parser):
        parser.add_argument(
            "--doc-id",
            type=int,
            nargs="*",
            help="ids to process one by one, if desired",
        )
        parser.add_argument(
            "--count-from-opinions-cited",
            action="store_true",
            default=False,
            help="Flag to compute the citation_count from the OpinionsCited table",
        )
        parser.add_argument(
            "--start-cluster-id",
            type=int,
            default=None,
            help="An OpinionCluster.id to start the batch updates from",
        )
        parser.add_argument(
            "--end-cluster-id",
            type=int,
            default=None,
            help="An OpinionCluster.id where the batch updates end",
        )
        parser.add_argument(
            "--step-size",
            type=int,
            default=10_000,
            nargs="*",
            help="Number of ids to consider in a batch update",
        )

    def handle(self, *args, **options):
        """
        For any item that has a citation count > 0, update the citation
        count based on the DB.
        """
        super().handle(*args, **options)

        clusters = OpinionCluster.objects.filter(citation_count__gt=0)
        if options.get("doc_id"):
            clusters = clusters.filter(pk__in=options["doc_id"])

            for cluster in clusters.iterator():
                count = 0
                for sub_opinion in cluster.sub_opinions.all():
                    count += sub_opinion.citing_opinions.all().count()

                cluster.citation_count = count
                cluster.save()
            return

        if not options.get("count_from_opinions_cited"):
            return

        if not (
            options.get("start_cluster_id") and options.get("end_cluster_id")
        ):
            raise ValueError(
                "Must pass values for start-cluster-id and end-cluster-id"
            )

        # In 2025, we have a little more than 10.1M clusters
        step_size = options["step_size"]
        for start_id in range(
            options.get("start_cluster_id"),
            options.get("end_cluster_id"),
            step_size,
        ):
            end_id = start_id + step_size

            logger.info(
                "Updating citation_count for clusters with ids between %s and %s",
                start_id,
                end_id,
            )
            self.update_cluster_citation_count_from_opinions_cited(
                options["start_cluster_id"], options["end_cluster_id"]
            )
            logger.info("Finished citation_count update")

            # Give some time for anything waiting for the clusters' locks
            time.sleep(10)

    def update_cluster_citation_count_from_opinions_cited(
        self, start_cluster_id: int, end_cluster_id: int
    ) -> None:
        # Group by OpinionCluster.id and count all the OpinionsCited rows for
        # all of its subopinions
        count_by_cluster_subquery = Subquery(
            OpinionsCited.objects.filter(
                # 'pk' refers to the OpinionCluster.id of the row being updated
                # OuterRef joins to a key from the query enveloping the Subquery,
                # in this case, the update statement below
                cited_opinion__cluster_id=OuterRef("pk"),
                cited_opinion__cluster_id__gte=start_cluster_id,
                cited_opinion__cluster_id__lt=end_cluster_id,
            )
            # Group by the cluster ID
            .values("cited_opinion__cluster_id")
            # Count the number of citation entries for this cluster
            .annotate(total_count=Count("id"))
            # bring back only the grouping id and the total_count
            .values("total_count")
            .order_by()
        )

        with transaction.atomic():
            OpinionCluster.objects.filter(
                id__gte=start_cluster_id, id__lt=end_cluster_id
            ).update(
                citation_count=Coalesce(
                    count_by_cluster_subquery,
                    Value(0),
                    output_field=IntegerField(),
                )
            )
