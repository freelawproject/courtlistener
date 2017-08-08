# coding=utf-8
import time
import sys

from cl.citations.tasks import update_document
from cl.lib import sunburnt
from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.db_tools import queryset_generator
from cl.search.models import Opinion
from django.conf import settings
from django.core.management import call_command
from django.core.management import CommandError


class Command(VerboseCommand):
    help = 'Parse citations out of documents.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--doc_id',
            type=int,
            nargs='*',
            help='ids of citing opinions',
        )
        parser.add_argument(
            '--start_id',
            type=int,
            help='start id for a range of documents to update (inclusive)',
        )
        parser.add_argument(
            '--end_id',
            type=int,
            help='end id for a range of documents to update (inclusive)',
        )
        parser.add_argument(
            # Note that there's a temptation to add a field here for
            # date_modified, to get any recently modified files. The danger of
            # doing this is that you modify files as you process them,
            # creating an endless loop. You'll start the program reporting X
            # files to modify, but after those items finish, you'll discover
            # that the program continues onto the newly edited files,
            # including those files that have new citations to them.
            # ♪♪♪ Smoke in the server, fire in the wires. ♪♪♪
            '--filed_after',
            type=valid_date_time,
            help="Start date in ISO-8601 format for a range of documents to "
                 "update. Dates will be converted to ",
        )
        parser.add_argument(
            '--all',
            action='store_true',
            default=False,
            help='Parse citations for all items',
        )
        parser.add_argument(
            '--index',
            type=str,
            default='all_at_end',
            choices=('all_at_end', 'concurrently', 'False'),
            help=("When/if to save changes to the Solr index. Options are "
                  "all_at_end, concurrently or False. Saving 'concurrently' "
                  "is least efficient, since each document is updated once "
                  "for each citation to it, however this setting will show "
                  "changes in the index in realtime. Saving 'all_at_end' can "
                  "be considerably more efficient, but will not show changes "
                  "until the process has finished and the index has been "
                  "completely regenerated from the database. Setting this to "
                  "False disables changes to Solr, if that is what's desired. "
                  "Finally, only 'concurrently' will avoid reindexing the "
                  "entire collection. If you are only updating a subset of "
                  "the opinions, it is thus generally wise to use "
                  "'concurrently'."),
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        both_list_and_endpoints = (options.get('doc_id') is not None and
                                   (options.get('start_id') is not None or
                                    options.get('end_id') is not None or
                                    options.get('filed_after') is not None))
        no_option = (not any([options.get('doc_id') is None,
                              options.get('start_id') is None,
                              options.get('end_id') is None,
                              options.get('filed_after') is None,
                              options.get('all') is False]))
        if both_list_and_endpoints or no_option:
            raise CommandError('Please specify either a list of documents, a '
                               'range of ids, a range of dates, or '
                               'everything.')

        self.index = options['index']
        self.si = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='rw')

        # Use query chaining to build the query
        query = Opinion.objects.all()
        if options.get('doc_id'):
            query = query.filter(pk__in=options.get('doc_id'))
        if options.get('end_id'):
            query = query.filter(pk__lte=options.get('end_id'))
        if options.get('start_id'):
            query = query.filter(pk__gte=options.get('start_id'))
        if options.get('filed_after'):
            query = query.filter(
                cluster__date_filed__gte=options['filed_after'])
        if options.get('all'):
            query = Opinion.objects.all()
        self.count = query.count()
        self.average_per_s = 0
        self.timings = []
        docs = queryset_generator(query, chunksize=10000)
        self.update_documents(docs)

    def log_progress(self, processed_count, last_pk):
        if processed_count % 1000 == 1:
            self.t1 = time.time()
        if processed_count % 1000 == 0:
            self.t2 = time.time()
            self.timings.append(self.t2 - self.t1)
            self.average_per_s = 1000 / (sum(self.timings) / float(len(self.timings)))
        template = ("\rProcessing items in Celery queue: {:.0%} ({}/{}, "
                    "{:.1f}/s, Last id: {})")
        sys.stdout.write(template.format(
            float(processed_count) / self.count,  # Percent
            processed_count,
            self.count,
            self.average_per_s,
            last_pk,
        ))
        sys.stdout.flush()

    def update_documents(self, documents):
        sys.stdout.write('Graph size is {0:d} nodes.\n'.format(self.count))
        sys.stdout.flush()
        processed_count = 0
        if self.index == 'concurrently':
            index_during_subtask = True
        else:
            index_during_subtask = False
        throttle = CeleryThrottle(min_items=500)
        for doc in documents:
            throttle.maybe_wait()
            update_document.delay(doc, index_during_subtask)
            processed_count += 1
            self.log_progress(processed_count, doc.pk)

        if self.index == 'all_at_end':
            call_command(
                'cl_update_index',
                '--type', 'opinions',
                '--solr-url', settings.SOLR_OPINION_URL,
                '--noinput',
                '--update',
                '--everything',
                '--do-commit',
            )
        elif self.index == 'False':
            sys.stdout.write("Solr index not updated after running citation "
                             "finder. You may want to do so manually.")
