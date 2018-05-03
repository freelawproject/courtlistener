import requests
from django.conf import settings
from six.moves.urllib import parse

from cl.lib.command_utils import VerboseCommand


class Command(VerboseCommand):
    help = 'Delete a file from Internet Archive due to it being sealed or ' \
           'otherwise private.'
    IA_STORAGE_URL = 'http://s3.us.archive.org'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ia-download-url',
            help="The download URL of the item on Internet Archive, for "
                 "example, https://archive.org/download/gov.uscourts.nyed.299029/gov.uscourts.nyed.299029.30.0.pdf",
            required=True,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        path = parse.urlparse(options['ia_download_url']).path
        # Drop the /download/ part of the url to just get the bucket and the
        # path
        bucket_path = path.split('/', 2)[2]
        r = requests.delete(
            '%s/%s' % (self.IA_STORAGE_URL, bucket_path),
            headers={
                'Authorization': 'LOW %s:%s' % (
                    settings.IA_ACCESS_KEY,
                    settings.IA_SECRET_KEY,
                ),
                'x-archive-cascade-delete': '1',
            }
        )
        if r.ok:
            print("Item deleted successfully")
        else:
            print("No luck with deletion: %s: %s" % (r.status_code, r.content))
