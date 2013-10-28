import time
import sys

from alert.search.models import Document
from alert.lib.db_tools import queryset_generator
from celery.task.sets import TaskSet
from citations.tasks import update_document
from django.core.management import BaseCommand, CommandError
from optparse import make_option


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option(
            '--doc_id',
            type=int,
            help='id of a document to update'
        ),
        make_option(
            '--start_id',
            type=int,
            default=0,
            help='start id for a range of documents to update'
        ),
        make_option(
            '--end_id',
            type=int,
            help='end id for a range of documents to update'
        ),
        make_option(
            '--all',
            default=False,
            action='store_true',
            help='parse citations for all items',
        ),
    )
    help = 'Parse citations out of documents.'

    def update_documents(self, documents, count):
        sys.stdout.write('Graph size is {0:d} nodes.\n'.format(count))
        sys.stdout.flush()
        processed_count = 0
        subtasks = []
        for doc in documents:
            subtasks.append(update_document.subtask((doc,)))
            processed_count += 1
            sys.stdout.write("\rProcessing items in Celery queue: {0:d}/{1:d}...".format(processed_count, count))
            sys.stdout.flush()
            last_document = (count == processed_count)
            if (processed_count % 50 == 0) or last_document:
                # Every 50 documents, we send the subtasks off for processing
                # Poll to see when they're done.
                job = TaskSet(tasks=subtasks)
                result = job.apply_async()
                while not result.ready():
                    time.sleep(0.5)

                # The jobs finished - clean things up for the next round
                subtasks = []

    def handle(self, *args, **options):
        both_list_and_endpoints = (options.get('doc_id') is not None and
                                   (options.get('start_id') is not None or options.get('end_id') is not None))
        no_option = (not any([options.get('doc_id') is None,
                              options.get('start_id') is None,
                              options.get('end_id') is None,
                              options.get('all') is False]))
        if both_list_and_endpoints or no_option:
            raise CommandError('Please specify either a list of documents, a range of ids or everything.')

        if options.get('doc_id') is not None:
            query = Document.objects.filter(pk=options.get('doc_id'))
        elif options.get('end_id'):
            query = Document.objects.filter(pk__gte=options.get('start_id'),
                                            pk__lte=options.get('end_id'))
        elif options.get('start_id') is not None and not options.get('end_id'):
            query = Document.objects.filter(pk__gte=options.get('start_id'))
        elif options.get('all'):
            query = Document.object.all()
        count = query.count()
        docs = queryset_generator(query.order_by('date_filed'), chunksize=10000)
        self.update_documents(docs, count)
