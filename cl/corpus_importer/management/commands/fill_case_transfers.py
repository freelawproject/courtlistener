from cl.corpus_importer.tasks import fill_case_transfer_missing_dockets
from cl.lib.command_utils import VerboseCommand


class Command(VerboseCommand):
    help = "Update missing docket foreign keys in the CaseTransfer table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue",
            type=str,
            help="The queue to run the update task in.",
            default="celery",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        queue = options["queue"]
        fill_case_transfer_missing_dockets.delay(queue)
