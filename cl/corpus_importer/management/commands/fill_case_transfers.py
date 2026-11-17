"""Fill in the missing dockets of case transfers."""

from cl.lib.command_utils import VerboseCommand
from cl.search.models import CaseTransfer


class Command(VerboseCommand):
    """Fill in the missing docket foreign keys of case transfers."""

    help = "Update missing docket foreign keys in the CaseTransfer table."

    def handle(self, *args, **options):
        """Fill in the null dockets of case transfers."""
        super().handle(*args, **options)
        CaseTransfer.fill_null_dockets()
