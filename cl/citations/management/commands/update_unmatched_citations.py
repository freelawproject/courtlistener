from cl.citations.management.commands import find_citations
from cl.citations.models import UnmatchedCitation
from cl.lib.command_utils import VerboseCommand


class Command(find_citations.Command):
    """Re-run find_citations_and_parentheticals_for_opinion_by_pks for
    opinions where unmatched citations have been found
    """

    help = "Try to resolve unmatched citations"
    # variables to use find_citations.Command.update_documents
    count = 0
    average_per_s = 0.0
    timings: list[float] = []

    def add_arguments(self, parser):
        VerboseCommand.add_arguments(self, parser)
        parser.add_argument(
            "--resolve-failures",
            action="store_true",
            default=False,
            help="Include citations with FAILED and FAILED_AMBIGUOUS status",
        )
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )

    def handle(self, *args, **options):
        """Re-uses find_citations.Command enqueuer and logging"""
        VerboseCommand.handle(self, *args, **options)
        status = [UnmatchedCitation.FOUND]
        if options["resolve_failures"]:
            status.extend(
                [UnmatchedCitation.FAILED, UnmatchedCitation.FAILED_AMBIGUOUS]
            )

        # distinct() on Django only works when the same field is on .order_by()
        opinion_ids = (
            UnmatchedCitation.objects.filter(status__in=status)
            .order_by("citing_opinion_id")
            .distinct("citing_opinion_id")
        )
        self.count = opinion_ids.count()
        opinion_pks = opinion_ids.values_list("citing_opinion_id", flat=True)
        find_citations.Command.update_documents(
            self, opinion_pks, options["queue"]
        )
