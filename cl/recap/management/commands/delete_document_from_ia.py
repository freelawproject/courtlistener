"""Delete a file from the Internet Archive."""

from cl.lib.command_utils import VerboseCommand
from cl.search.deletion_utils import delete_from_ia


class Command(VerboseCommand):
    """Delete a file from the Internet Archive by its download URL."""

    help = (
        "Delete a file from Internet Archive due to it being sealed or "
        "otherwise private."
    )

    def add_arguments(self, parser):
        """Add the required Internet Archive download URL option."""
        parser.add_argument(
            "--ia-download-url",
            help="The download URL of the item on Internet Archive, for "
            "example, https://archive.org/download/gov.uscourts.nyed.299029/gov.uscourts.nyed.299029.30.0.pdf",
            required=True,
        )

    def handle(self, *args, **options):
        """Delete the file and print whether it worked."""
        super().handle(*args, **options)
        r = delete_from_ia(options["ia_download_url"])
        if r.ok:
            print("Item deleted successfully")
        else:
            print(f"No luck with deletion: {r.status_code}: {r.text}")
