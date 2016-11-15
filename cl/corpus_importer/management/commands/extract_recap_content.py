import logging

from django.core.management import BaseCommand

from cl.scrapers.utils import extract_recap_documents
from cl.search.models import RECAPDocument

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = ('Iterate over all of the RECAPDocuments and extract their '
            'content. This should later be modified to only do certain docs, '
            'since doing all of them should be rare.')

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
        parser.add_argument(
            '--queue-length',
            type=int,
            default=100,
            help="How many items should be enqueued at a time? (default: 100)",
        )

    def handle(self, *args, **options):
        docs = RECAPDocument.objects.all()
        extract_recap_documents(docs, options['skip_ocr'], options.get('order'),
                                options['queue'], options['queue_length'])

