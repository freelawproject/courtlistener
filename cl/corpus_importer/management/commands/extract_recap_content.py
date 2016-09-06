import logging

from celery.task import TaskSet
from django.core.management import BaseCommand

from cl.scrapers.tasks import extract_recap_pdf
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
            type=bool,
            store_true=True,
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
        docs = RECAPDocument.objects.exclude(filepath_local='')

        if options['skip_ocr']:
            # Focus on the items that we don't know if they need OCR.
            docs.filter(ocr_status=None)
        else:
            # We're doing OCR. Only work with those items that require it.
            docs.filter(ocr_status=RECAPDocument.OCR_NEEDED)

        count = docs.count()
        print("There are %s documents to process." % count)

        if options.get('order') is not None:
            if options['order'] == 'small-first':
                docs.order_by('page_count')
            elif options['order'] == 'big-first':
                docs.order_by('-page_count')

        subtasks = []
        completed = 0
        for pk in docs.values_list('pk', flat=True):
            # Send the items off for processing.
            last_item = (count == completed)
            subtasks.append(extract_recap_pdf.subtask(
                (pk, options['skip_ocr']),
                priority=5,
                queue=options['queue']
            ))

            # Every enqueue_length items, send the subtasks to Celery.
            if (len(subtasks) >= options['enqueue_length']) or last_item:
                msg = ("Sent %s subtasks to celery. We have sent %s "
                       "items so far." % (len(subtasks), completed + 1))
                logger.info(msg)
                print(msg)
                job = TaskSet(tasks=subtasks)
                job.apply_async().join()
                subtasks = []

            completed += 1
