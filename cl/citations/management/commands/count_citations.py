from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from cl.lib.command_utils import VerboseCommand
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
            help="Flag to compute the citation_count for all clusters from the OpinionsCited table",
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

        # Group by OpinionCluster.id and count all the OpinionsCited rows for
        # all of its subopinions
        count_by_cluster_subquery = Subquery(
            OpinionsCited.objects.filter(
                # 'pk' refers to the OpinionCluster.id of the row being updated
                # OuterRef joins to a key from the query enveloping the Subquery,
                # in this case, the update statement below
                cited_opinion__cluster_id=OuterRef("pk")
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
            OpinionCluster.objects.update(
                citation_count=Coalesce(
                    count_by_cluster_subquery,
                    Value(0),
                    output_field=IntegerField(),
                )
            )
