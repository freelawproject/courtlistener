from cl.lib.command_utils import VerboseCommand
from cl.search.models import OpinionCluster


class Command(VerboseCommand):
    help = "Update the citation counts of all items, if they are wrong."

    def add_arguments(self, parser):
        parser.add_argument(
            "--doc-id",
            type=int,
            nargs="*",
            help="ids to process one by one, if desired",
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
