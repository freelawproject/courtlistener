import ast
import sys

from alert.lib import sunburnt
from alert.lib.db_tools import queryset_generator
from alert.lib.timer import print_timing
from alert.search.models import Document
# Celery requires imports like this. Disregard syntax error.
from search.tasks import delete_docs
from search.tasks import add_or_update_docs
from search.tasks import add_or_update_doc_object

from celery.task.sets import TaskSet
from django.conf import settings
from django.core.management.base import BaseCommand
from optparse import make_option
import datetime
import time


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--update',
                    action='store_true',
                    dest='update_mode',
                    default=False,
                    help=('Run the command in update mode. Use this to add or update '
                          'documents.')),
        make_option('--delete',
                    action='store_true',
                    dest='delete_mode',
                    default=False,
                    help=('Run the command in delete mode. Use this to remove documents '
                          'from the index.')),
        make_option('--optimize',
                    action='store_true',
                    dest='optimize_mode',
                    default=False,
                    help=('Run the optimize command against the current index after any '
                          'updates or deletions are completed.')),
        make_option('--everything',
                    action='store_true',
                    dest='everything',
                    default=False,
                    help='Take action on everything in the database'),
        make_option('--query',
                    action='store_true',
                    dest='query',
                    default=False,
                    help=('Take action on documents fulfilling a query. Queries should be'
                          ' formatted as Python dicts such as: "{\'court_id\':\'haw\'}"')),
        make_option('--datetime',
                    action='store_true',
                    dest='datetime',
                    default=False,
                    help=('Take action on documents newer than a date (YYYY-MM-DD) or a '
                          'date and time (YYYY-MM-DD HH:MM:SS)')),
        make_option('--document',
                    action='store_true',
                    dest='document',
                    default=False,
                    help='Take action on a list of documents using a single Celery task'),
    )
    args = ("(--update | --delete) (--everything | --datetime 'YYYY-MM-DD [HH:MM:SS]' | "
            "--query Q | --document <doc_id> <doc_id>) [--optimize]")
    help = 'Adds, updates or removes documents in the index.'

    def _proceed_with_deletion(self, count):
        """
        Checks whether we want to proceed to delete (lots of) documents
        """
        proceed = True
        self.stdout.write("\n")
        yes_or_no = raw_input('WARNING: Are you **sure** you want to delete all '
                              '%s documents? [y/N] ' % count)
        self.stdout.write('\n')
        if not yes_or_no.lower().startswith('y'):
            self.stdout.write("No action taken.\n")
            proceed = False

        if count > 10000:
            # Double check...something might be off.
            yes_or_no = raw_input('Are you double-plus sure? There is an awful '
                                  'lot of documents here? [y/N] ')
            if not yes_or_no.lower().startswith('y'):
                self.stdout.write("No action taken.\n")
                proceed = False

        return proceed

    def _chunk_queryset_into_tasks(self, docs, count, chunksize=1000):
        """Chunks the queryset passed in, and dispatches it to Celery for
        adding to the index.

        Potential performance improvements:
         - Postgres is quiescent when Solr is popping tasks from Celery, instead, it should be fetching the next 1,000
         - The wait loop (while not result.ready()) polls for the results, at a 1s interval. Could this be reduced or
           somehow eliminated while keeping Celery's tasks list from running away?
        """
        processed_count = 0
        not_in_use = 0
        subtasks = []
        for doc in docs:
            # Make a search doc, and add it to the index
            if self.verbosity >= 2:
                self.stdout.write('Indexing document %s' % doc.pk)
            if doc.court.in_use:
                subtasks.append(add_or_update_doc_object.subtask((doc,)))
                processed_count += 1
            else:
                # The document is in an unused court
                not_in_use += 1

            last_document = (count == processed_count + not_in_use)
            if (processed_count % chunksize == 0) or last_document:
                # Every chunksize documents, we send the subtasks off for processing
                job = TaskSet(tasks=subtasks)
                result = job.apply_async()
                while not result.ready():
                    time.sleep(1)

                # The jobs finished - clean things up for the next round
                subtasks = []

                if (processed_count % 50000 == 0) or last_document:
                    # Do a commit every 50000 items, for good measure.
                    self.si.commit()

            self.stdout.write("\rProcessed %d of %d.   Not in use: %d" %
                              (processed_count, count, not_in_use))
        self.stdout.write('\n')

    @print_timing
    def delete(self, *documents):
        """
        Given a document, creates a Celery task to delete it.
        """
        self.stdout.write("Deleting document(s): %s\n" % list(documents))
        # Use Celery to delete the document asynchronously
        delete_docs.delay(documents)

    def delete_all(self):
        """
        Deletes all documents from the database.
        """
        count = self.si.raw_query({'q': '*:*'}).count()

        if self._proceed_with_deletion(count):
            self.stdout.write('Removing all documents from your index because '
                              'you said so.\n')
            self.stdout.write('Marking all documents as deleted...\n')
            self.si.delete_all()
            self.stdout.write('Committing the deletion...\n')
            self.si.commit()
            self.stdout.write('\nDone. Your index has been emptied. Hope this is '
                              'what you intended.\n')

    @print_timing
    def delete_by_datetime(self, dt):
        """
        Given a datetime, deletes all documents in the index newer than that time.
        """
        qs = Document.objects.filter(time_retrieved__gt=dt)
        count = qs.count()
        if self._proceed_with_deletion(count):
            self.stdout.write("Deleting all document(s) newer than %s\n" % dt)
            docs = queryset_generator(qs)
            for doc in docs:
                self.si.delete(doc)
            self.si.commit()

    @print_timing
    def delete_by_query(self, query):
        """
        Given a query, deletes all the documents that match that query.
        """
        query_dict = ast.literal_eval(query)
        count = self.si.query(self.si.Q(**query_dict)).count()
        if self._proceed_with_deletion(count):
            self.stdout.write("Deleting all document(s) that match the query: %s\n" % query)
            self.si.delete(queries=self.si.Q(**query_dict))
            self.si.commit()

    @print_timing
    def add_or_update(self, *documents):
        """
        Given a document, adds it to the index, or updates it if it's already
        in the index.
        """
        self.stdout.write("Adding or updating document(s): %s\n" % list(documents))
        # Use Celery to add or update the document asynchronously
        add_or_update_docs.delay(documents)

    @print_timing
    def add_or_update_by_datetime(self, dt):
        """
        Given a datetime, adds or updates all documents newer than that time.
        """
        self.stdout.write("Adding or updating document(s) newer than %s\n" % dt)
        qs = Document.objects.filter(time_retrieved__gt=dt)
        docs = queryset_generator(qs)
        count = qs.count()
        self._chunk_queryset_into_tasks(docs, count, chunksize=1000)

    @print_timing
    def add_or_update_all(self):
        """
        Iterates over the entire corpus, adding it to the index. Can be run on
        an empty index or an existing one. If run on an existing index,
        existing documents will be updated.
        """
        self.stdout.write("Adding or updating all documents...\n")
        docs = queryset_generator(Document.objects.all())
        count = Document.objects.all().count()
        self._chunk_queryset_into_tasks(docs, count, chunksize=1000)

    @print_timing
    def optimize(self):
        """Runs the Solr optimize command.

        Not much more than a wrapper of a wrapper (Sunburnt) of a wrapper
        (Solr). Weird. Thankfully, Lucene isn't a wrapper of anything.
        """
        self.stdout.write('Optimizing the index...')
        self.si.optimize()
        self.stdout.write('done.\n')

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.si = sunburnt.SolrInterface(settings.SOLR_URL, mode='rw')

        if options.get('datetime'):
            try:
                # Parse the date string into a datetime object
                dt = datetime.datetime(*time.strptime(args[0],
                                                      '%Y-%m-%d %H:%M:%S')[0:6])
            except ValueError:
                try:
                    dt = datetime.datetime(*time.strptime(args[0],
                                                          '%Y-%m-%d')[0:5])
                except ValueError:
                    self.stderr.write('Unable to parse time. Please use '
                                      'format: YYYY-MM-DD HH:MM:SS or '
                                      'YYYY-MM-DD.\n')
                    sys.exit(1)

        if options.get('update_mode'):
            if self.verbosity >= 1:
                self.stdout.write('Running in update mode...\n')
            if options.get('everything'):
                self.add_or_update_all()
            elif options.get('datetime'):
                self.add_or_update_by_datetime(dt)
            elif option.get('query'):
                self.stderr.write("Updating by query not yet implemented.")
                sys.exit(1)
            elif options.get('document'):
                for doc in args:
                    try:
                        int(doc)
                    except ValueError:
                        self.stderr.write('Error: Document "%s" could not be '
                                          'converted to an ID.\n' % doc)
                        sys.exit(1)
                self.add_or_update(*args)
            else:
                self.stderr.write('Error: You must specify what you wish to '
                                  'update.\n')
                sys.exit(1)

        elif options.get('delete_mode'):
            if self.verbosity >= 1:
                self.stdout.write('Running in deletion mode...\n')
            if options.get('everything'):
                self.delete_all()
            elif options.get('datetime'):
                self.delete_by_datetime(dt)
            elif options.get('query'):
                self.delete_by_query(args[0])
            elif options.get('document'):
                for doc in args:
                    try:
                        int(doc)
                    except ValueError:
                        self.stderr.write('Error: Document "%s" could not be '
                                          'converted to an ID.\n' % doc)
                        sys.exit(1)
                self.delete(*args)
            else:
                self.stderr.write('Error: You must specify what you wish to '
                                  'delete.\n')
                sys.exit(1)

        elif not any([options.get('update_mode'),
                      options.get('delete_mode'),
                      options.get('optimize_mode')]):
            self.stderr.write('Error: You must specify whether you wish to '
                              'update, delete, or optimize your index.\n')
            sys.exit(1)

        if options.get('optimize_mode'):
            self.optimize()
            sys.exit(0)
