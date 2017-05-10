import logging

from django.core.management import BaseCommand

from cl.scrapers.utils import extract_recap_documents
from cl.search.models import RECAPDocument

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = ('Iterate over all of the RECAPDocuments and extract their '
            'content.')

    def add_arguments(self, parser):
        # Global args.
        parser.add_argument(
            '--order',
            type=str,
            help="The order that you wish to enqueue items, either "
                 "'small-first' or 'big-first'"
        )
        parser.add_argument(
            '--skip-ocr',
            default=False,
            action='store_true',
            help="Should we run OCR, or just label items that need it?",
        )
        parser.add_argument(
            '--queue',
            type=str,
            default='celery',
            help="Which queue should the items be sent to? (default: 'celery')",
        )

    def handle(self, *args, **options):
        docs = RECAPDocument.objects.all().order_by()
        extract_recap_documents(docs, options['skip_ocr'], options.get('order'),
                                options['queue'])

