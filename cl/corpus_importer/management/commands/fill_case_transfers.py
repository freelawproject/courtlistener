from cl.lib.command_utils import VerboseCommand
from cl.search.models import CaseTransfer


class Command(VerboseCommand):
    help = "Update missing docket foreign keys in the CaseTransfer table."

    def handle(self, *args, **options):
        super().handle(*args, **options)
        CaseTransfer.fill_null_dockets()
