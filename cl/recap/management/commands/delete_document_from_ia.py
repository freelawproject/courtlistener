from urllib import parse

import requests
from django.conf import settings
from requests import Response

from cl.lib.command_utils import VerboseCommand


def delete_from_ia(url: str) -> Response:
    """Delete an item from Internet Archive by URL

    :param url: The URL of the item, for example,
    https://archive.org/download/gov.uscourts.nyed.299029/gov.uscourts.nyed.299029.30.0.pdf
    :return: The requests.Response of the request to IA.
    """
    # Get the path and drop the /download/ part of it to just get the bucket
    # and the path
    path = parse.urlparse(url).path
    bucket_path = path.split("/", 2)[2]
    storage_domain = "http://s3.us.archive.org"
    return requests.delete(
        f"{storage_domain}/{bucket_path}",
        headers={
            "Authorization": f"LOW {settings.IA_ACCESS_KEY}:{settings.IA_SECRET_KEY}",
            "x-archive-cascade-delete": "1",
        },
        timeout=60,
    )


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
