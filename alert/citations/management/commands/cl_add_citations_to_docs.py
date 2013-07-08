import time

from alert.search.models import Document
from alert.lib.db_tools import queryset_generator
from celery.task.sets import TaskSet
from django.core.management import BaseCommand, CommandError
from optparse import make_option

# Celery requires imports like this. Disregard syntax error.
from citations.tasks import update_document


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--doc_id',
                    type=int,
                    help='id of a document to update'),
        make_option('--start_id',
                    type=int,
                    default=0,
                    help='start id for a range of documents to update'),
        make_option('--end_id',
                    type=int,
                    help='end id for a range of documents to update')
    )
    help = 'Parse citations out of documents.'

    def update_documents(self, documents, count):
        processed_count = 0
        subtasks = []
        for doc in documents:
            subtasks.append(update_document.subtask((doc,)))
            processed_count += 1

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
        both_list_and_endpoints = (options.get('doc_id') and (options.get('start_id') or options.get('end_id')))
        neither_list_nor_endpoints = (not any([options.get('doc_id'),
                                              options.get('start_id'),
                                              options.get('end_id')]))
        if both_list_and_endpoints or neither_list_nor_endpoints:
            raise CommandError('Please specify either a list of documents or a range of ids.')

        if options.get('doc_id'):
            query = Document.objects.filter(pk=options.get('doc_id'))
        elif options.get('end_id'):
            query = Document.objects.filter(pk__gte=options.get('start_id'),
                                            pk__lte=options.get('end_id'))
        elif options.get('start_id') and not options.get('end_id'):
            query = Document.objects.filter(pk__gte=options.get('start_id'))
        count = query.count()
        docs = queryset_generator(query)
        self.update_documents(docs, count)
