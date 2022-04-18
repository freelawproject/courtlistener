import sys

from django.conf import settings
from django.core.management import call_command

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
        parser.add_argument(
            "--index",
            type=str,
            default="all-at-end",
            choices=("all-at-end", "concurrently", "False"),
            help=(
                "When/if to save changes to the Solr index. Options are "
                "all-at-end, concurrently or False. Saving 'concurrently' "
                "is least efficient, since each document is updated once "
                "for each citation to it, however this setting will show "
                "changes in the index in realtime. Saving 'all-at-end' can "
                "be considerably more efficient, but will not show changes "
                "until the process has finished and the index has been "
                "completely regenerated from the database. Setting this to "
                "False disables changes to Solr, if that is what's desired. "
                "Finally, only 'concurrently' will avoid reindexing the "
                "entire collection. If you are only updating a subset of "
                "the opinions, it is thus generally wise to use "
                "'concurrently'."
            ),
        )

    @staticmethod
    def do_solr(options):
        """Update Solr if requested, or report if not."""
        if options["index"] == "all-at-end":
            # fmt: off
            call_command(
                'cl_update_index',
                '--type', 'search.Opinion',
                '--solr-url', settings.SOLR_OPINION_URL,
                '--noinput',
                '--update',
                '--everything',
                '--do-commit',
            )
            # fmt: on
        elif options["index"] == "False":
            sys.stdout.write(
                "Solr index not updated after running citation "
                "finder. You may want to do so manually."
            )

    def handle(self, *args, **options):
        """
        For any item that has a citation count > 0, update the citation
        count based on the DB.
        """
        super(Command, self).handle(*args, **options)
        index_during_processing = False
        if options["index"] == "concurrently":
            index_during_processing = True

        clusters = OpinionCluster.objects.filter(citation_count__gt=0)
        if options.get("doc_id"):
            clusters = clusters.filter(pk__in=options["doc_id"])

        for cluster in clusters.iterator():
            count = 0
            for sub_opinion in cluster.sub_opinions.all():
                count += sub_opinion.citing_opinions.all().count()

            cluster.citation_count = count
            cluster.save(index=index_during_processing)

        self.do_solr(options)
