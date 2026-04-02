from cl.lib.command_utils import VerboseCommand
from cl.search.utils import delete_from_ia


class Command(VerboseCommand):
    help = (
        "Delete a file from Internet Archive due to it being sealed or "
        "otherwise private."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--ia-download-url",
            help="The download URL of the item on Internet Archive, for "
            "example, https://archive.org/download/gov.uscourts.nyed.299029/gov.uscourts.nyed.299029.30.0.pdf",
            required=True,
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        r = delete_from_ia(options["ia_download_url"])
        if r.ok:
            print("Item deleted successfully")
        else:
            print(f"No luck with deletion: {r.status_code}: {r.text}")
