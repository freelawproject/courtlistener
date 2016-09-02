import argparse
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
            required=True,
            help="The order that you wish to enqueue items, either "
                 "'small-first' or 'big-first'"
            )

    def handle(self, *args, **options):
        docs = RECAPDocument.objects.filter(
            ocr_status=None
        ).exclude(
            filepath_local='',
        )
        count = docs.count()
        print("There are %s documents to process." % count)

        if options['order'] == 'small-first':
            docs.order_by('page_count')
            enqueue_length = 100
            queue = 'celery'  # default queue
        elif options['order'] == 'big-first':
            docs.order_by('-page_count')
            enqueue_length = 1000
            queue = 'big-ocr'
        else:
            raise argparse.ArgumentTypeError("Invalid argument for 'order'")

        subtasks = []
        completed = 0
        for pk in docs.values_list('pk', flat=True):
            # Try to extract the contents the easy way, but if that fails,
            # use OCR.
            last_item = (count == completed)
            subtasks.append(extract_recap_pdf.subtask((pk,), priority=5,
                                                      queue=queue))

            # Every n items, send the subtasks to Celery.
            if (len(subtasks) >= enqueue_length) or last_item:
                msg = ("Sent %s subtasks to celery. We have sent %s "
                       "items so far." % (len(subtasks), completed + 1))
                logger.info(msg)
                print(msg)
                job = TaskSet(tasks=subtasks)
                job.apply_async().join()
                subtasks = []

            completed += 1
