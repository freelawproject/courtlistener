import logging

from celery.task import TaskSet
from django.core.management import BaseCommand

from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import RECAPDocument


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = ('Iterate over all of the RECAPDocuments and extract their '
            'content.')

    def handle(self, *args, **options):
        docs = RECAPDocument.objects.filter(
            ocr_status=None
        ).exclude(
            filepath_local='',
        )
        count = docs.count()
        print("There are %s documents to process." % count)

        subtasks = []
        completed = 0
        for pk in docs.values_list('pk', flat=True):
            # Try to extract the contents the easy way, but if that fails,
            # use OCR.
            last_item = (count == completed)
            subtasks.append(extract_recap_pdf.subtask((pk,)))

            # Every n items, send the subtasks to Celery. The larger this
            # number, the less frequently you must wait while Celery processes a
            # massive PDF. But beware: OCR can clog the queue blocking other
            # tasks.
            enqueue_length = 100
            if (len(subtasks) >= enqueue_length) or last_item:
                msg = ("Sent %s subtasks to celery. We have sent %s "
                       "items so far." % (len(subtasks), completed + 1))
                logger.info(msg)
                print(msg)
                job = TaskSet(tasks=subtasks)
                job.apply_async().join()
                subtasks = []

            completed += 1
