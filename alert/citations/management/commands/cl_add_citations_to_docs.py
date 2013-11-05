from datetime import datetime
import time
import sys

from alert.lib.db_tools import queryset_generator
from django.core.management import call_command
from alert.search.models import Document
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
            '--start_date',
            type=str,
            help="Start date in ISO-8601 format for a range of documents to update"
        ),
        make_option(
            '--all',
            default=False,
            action='store_true',
            help='parse citations for all items',
        ),
        make_option(
            '--index',
            default='all_at_end',
            type=str,
            help=("When/if to save changes to the Solr index. Options are all_at_end, concurrently or False. Saving "
                  "'concurrently' is least efficient, since each document is updated once for each citation to it, "
                  "however this setting will show changes in the index in realtime. Saving 'all_at_end' can be "
                  "considerably more efficient, but will not show changes until the process has finished and the index "
                  "has been completely regenerated from the database. Setting this to False disables changes to Solr, "
                  "if that is what's desired."),
        )
    )
    help = 'Parse citations out of documents.'

    def update_documents(self, documents, count, index):
        sys.stdout.write('Graph size is {0:d} nodes.\n'.format(count))
        sys.stdout.flush()
        processed_count = 0
        subtasks = []
        timings = []
        average_per_s = 0
        if index == 'concurrently':
            index_during_subtask = True
        else:
            index_during_subtask = False
        for doc in documents:
            processed_count += 1
            if processed_count % 10000 == 0:
                # Send the commit every 1000 times.
                commit = True
            else:
                commit = False
            subtasks.append(update_document.subtask((doc, index_during_subtask, commit)))
            if processed_count % 1000 == 1:
                t1 = time.time()
            if processed_count % 1000 == 0:
                t2 = time.time()
                timings.append(t2 - t1)
                average_per_s = 1000 / (sum(timings) / float(len(timings)))
            sys.stdout.write("\rProcessing items in Celery queue: {:.0%} ({}/{}, {:.1f}/s)".format(
                processed_count * 1.0 / count,
                processed_count,
                count,
                average_per_s
            ))
            sys.stdout.flush()
            last_document = (count == processed_count)
            if (processed_count % 500 == 0) or last_document:
                # Every 500 documents, we send the subtasks off for processing
                # Poll to see when they're done.
                job = TaskSet(tasks=subtasks)
                result = job.apply_async()
                while not result.ready():
                    time.sleep(0.5)

                # The jobs finished - clean things up for the next round
                subtasks = []

        if index == 'all_at_end':
            call_command('cl_update_index', update_mode=True, everything=True)
        elif index == 'false':
            sys.stdout.write("Solr index not updated after running citation finder. You may want to do so manually.")

    def handle(self, *args, **options):
        both_list_and_endpoints = (options.get('doc_id') is not None and
                                   (options.get('start_id') is not None or
                                    options.get('end_id') is not None or
                                    options.get('start_date') is not None))
        no_option = (not any([options.get('doc_id') is None,
                              options.get('start_id') is None,
                              options.get('end_id') is None,
                              options.get('start_date') is None,
                              options.get('all') is False]))
        if both_list_and_endpoints or no_option:
            raise CommandError('Please specify either a list of documents, a range of ids, a range of dates, or '
                               'everything.')

        if options.get('start_date'):
            start_date = datetime.strptime(options['start_date'], '%Y-%m-%d')

        index = options['index'].lower()

        # Use query chaining to build the query
        query = Document.objects.all()
        if options.get('doc_id'):
            query = query.filter(pk=options.get('doc_id'))
        if options.get('end_id'):
            query = query.filter(pk__lte=options.get('end_id'))
        if options.get('start_id'):
            query = query.filter(pk__gte=options.get('start_id'))
        if options.get('start_date'):
            query = query.filter(date_filed__gte=start_date)
        elif options.get('all'):
            query = Document.object.all()
        count = query.count()
        docs = queryset_generator(query.order_by('date_filed'), chunksize=10000)
        self.update_documents(docs, count, index)
