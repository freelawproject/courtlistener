import ast
import datetime
import sys
import time
from alert.audio.models import Audio
from alert.lib import sunburnt
from alert.lib.db_tools import queryset_generator
from alert.lib.timer import print_timing
from alert.search.models import Document
# Celery requires imports like this. Disregard syntax error.
from search.tasks import (delete_items, add_or_update_audio_files,
                          add_or_update_docs, add_or_update_items)
from celery.task.sets import TaskSet
from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware, utc
from optparse import make_option


def proceed_with_deletion(out, count):
    """
    Checks whether we want to proceed to delete (lots of) items
    """
    proceed = True
    out.write("\n")
    yes_or_no = raw_input('WARNING: Are you **sure** you want to delete all '
                          '%s items? [y/N] ' % count)
    out.write('\n')
    if not yes_or_no.lower().startswith('y'):
        out.write("No action taken.\n")
        proceed = False

    if count > 10000:
        # Double check...something might be off.
        yes_or_no = raw_input('Are you double-plus sure? There is an awful '
                              'lot of items here? [y/N] ')
        if not yes_or_no.lower().startswith('y'):
            out.write("No action taken.\n")
            proceed = False

    return proceed


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--type',
                    dest='type',
                    default=None,
                    help=('Because the Solr indexes are loosely bound to the '
                          'database, commands require that the correct'
                          'model is provided in this argument. Current '
                          'choices are "audio" or "opinions".')),
        make_option('--update',
                    action='store_true',
                    dest='update_mode',
                    default=False,
                    help='Run the command in update mode. Use this to add or '
                         'update items.'),
        make_option('--delete',
                    action='store_true',
                    dest='delete_mode',
                    default=False,
                    help='Run the command in delete mode. Use this to remove '
                         'items from the index. Note that this will not '
                         'delete items from the index that do not continue to '
                         'exist in the database.'),
        make_option('--optimize',
                    action='store_true',
                    dest='optimize_mode',
                    default=False,
                    help=(
                        'Run the optimize command against the current index '
                        'after any updates or deletions are completed.')),
        make_option('--everything',
                    action='store_true',
                    dest='everything',
                    default=False,
                    help='Take action on everything in the database'),
        make_option('--query',
                    dest='query',
                    help='Take action on items fulfilling a query. '
                         'Queries should be formatted as Python dicts such '
                         'as: "{\'court_id\':\'haw\'}"'),
        make_option('--solr-url',
                    dest='solr_url',
                    default=None,
                    help=('When swapping cores, it can be valuable to use a '
                          'temporary Solr URL, overriding the default value '
                          'that\'s in the settings, e.g., http://127.0.0.1:8983/solr/swap_core')),
        make_option('--datetime',
                    action='store_true',
                    dest='datetime',
                    default=False,
                    help=('Take action on items newer than a date '
                          '(YYYY-MM-DD) or a date and time '
                          '(YYYY-MM-DD HH:MM:SS)')),
        make_option('--item',
                    action='store_true',
                    dest='item',
                    default=False,
                    help='Take action on a list of items using a single '
                         'Celery task'),
    )
    args = (
        "--solr-url http://127.0.0.1:8983/your/core/location (--update | "
        "--delete) (--everything | --datetime 'YYYY-MM-DD [HH:MM:SS]' | "
        "--query Q | --item <item_id> <item_id> ...) [--optimize]")
    help = 'Adds, updates or removes items in an index.'

    def _chunk_queryset_into_tasks(self, items, count, chunksize=5000,
                                   bundle_size=250):
        """Chunks the queryset passed in, and dispatches it to Celery for
        adding to the index.

        Potential performance improvements:
         - Postgres is quiescent when Solr is popping tasks from Celery,
           instead, it should be fetching the next 1,000
         - The wait loop (while not result.ready()) polls for the results, at
           a 1s interval. Could this be reduced or somehow eliminated while
           keeping Celery's tasks list from running away?
        """
        processed_count = 0
        subtasks = []
        item_bundle = []
        for item in items:
            last_item = (count == processed_count + 1)
            if self.verbosity >= 2:
                self.stdout.write('Indexing item %s' % item.pk)

            item_bundle.append(item)
            if (processed_count % bundle_size == 0) or last_item:
                # Every bundle_size documents we create a subtask
                subtasks.append(add_or_update_items.subtask(
                    (item_bundle, self.solr_url)))
                item_bundle = []
            processed_count += 1

            if (processed_count % chunksize == 0) or last_item:
                # Every chunksize items, we send the subtasks for processing
                job = TaskSet(tasks=subtasks)
                result = job.apply_async()
                while not result.ready():
                    time.sleep(1)
                subtasks = []

            if (processed_count % 50000 == 0) or last_item:
                # Do a commit every 50000 items, for good measure.
                self.stdout.write("...running commit command...")
                self.si.commit()

            sys.stdout.write("\rProcessed {}/{} ({:.0%})".format(
                processed_count,
                count,
                processed_count * 1.0 / count,
            ))
            self.stdout.flush()
        self.stdout.write('\n')

    @print_timing
    def delete(self, *items):
        """
        Given an item, creates a Celery task to delete it.
        """
        self.stdout.write("Deleting items(s): %s\n" % list(items))
        # Use Celery to delete the item asynchronously
        delete_items.delay(items)

    def delete_all(self):
        """
        Deletes all items from the database.
        """
        count = self.si.raw_query(
            **{'q': '*:*', 'caller': 'cl_update_index', }).count()

        if proceed_with_deletion(self.stdout, count):
            self.stdout.write('Removing all items from your index because '
                              'you said so.\n')
            self.stdout.write('Marking all items as deleted...\n')
            self.si.delete_all()
            self.stdout.write('Committing the deletion...\n')
            self.si.commit()
            self.stdout.write('\nDone. Your index has been emptied. Hope this '
                              'is what you intended.\n')

    @print_timing
    def delete_by_datetime(self, dt):
        """
        Given a datetime, deletes all items in the index newer than that time.

        Relies on the items still being in the database.
        """
        qs = self.type.objects.filter(time_retrieved__gt=dt)
        count = qs.count()
        if proceed_with_deletion(self.stdout, count):
            self.stdout.write("Deleting all item(s) newer than %s\n" % dt)
            items = queryset_generator(qs)
            for item in items:
                self.si.delete(item)
            self.si.commit()

    @print_timing
    def delete_by_query(self, query):
        """
        Given a query, deletes all the items that match that query.
        """
        query_dict = ast.literal_eval(query)
        count = self.si.query(self.si.Q(**query_dict)).count()
        if proceed_with_deletion(self.stdout, count):
            self.stdout.write("Deleting all item(s) that match the query: "
                              "%s\n" % query)
            self.si.delete(queries=self.si.Q(**query_dict))
            self.si.commit()

    @print_timing
    def add_or_update(self, *items):
        """
        Given an item, adds it to the index, or updates it if it's already
        in the index.
        """
        self.stdout.write("Adding or updating item(s): %s\n" % list(items))
        # Use Celery to add or update the item asynchronously
        if self.type == Document:
            add_or_update_docs.delay(items)
        elif self.type == Audio:
            add_or_update_audio_files.delay(items)

    @print_timing
    def add_or_update_by_datetime(self, dt):
        """
        Given a datetime, adds or updates all items newer than that time.
        """
        self.stdout.write(
            "Adding or updating items(s) newer than %s\n" % dt)
        qs = self.type.objects.filter(time_retrieved__gt=dt)
        items = queryset_generator(qs)
        count = qs.count()
        self._chunk_queryset_into_tasks(items, count)

    @print_timing
    def add_or_update_all(self):
        """
        Iterates over the entire corpus, adding it to the index. Can be run on
        an empty index or an existing one.

        If run on an existing index, existing items will be updated.
        """
        self.stdout.write("Adding or updating all items...\n")
        q = self.type.objects.all()
        items = queryset_generator(q, chunksize=5000)
        count = q.count()
        self._chunk_queryset_into_tasks(items, count)

    @print_timing
    def optimize(self):
        """Runs the Solr optimize command.

        This wraps Sunburnt, which wraps Solr, which wraps Lucene!
        """
        self.stdout.write('Optimizing the index...')
        self.si.optimize()
        self.stdout.write('done.\n')

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        if options.get('solr_url'):
            self.solr_url = options.get('solr_url')
            self.si = sunburnt.SolrInterface(options.get('solr_url'),
                                             mode='rw')
        else:
            self.stderr.write("solr-url is a required parameter.\n")
            exit(1)

        t = options.get('type')
        if t is not None and t.lower() == 'opinions':
            self.type = Document
        elif t is not None and t == 'audio':
            self.type = Audio
        else:
            self.stderr.write('Unable to parse --type argument. See help for '
                              'details.')
            exit(1)


        if options.get('datetime'):
            try:
                # Parse the date string into a datetime object
                dt = make_aware(datetime.datetime(
                    *time.strptime(args[0], '%Y-%m-%d %H:%M:%S')[0:6]), utc)
            except ValueError:
                try:
                    dt = make_aware(datetime.datetime(
                        *time.strptime(args[0], '%Y-%m-%d')[0:5]), utc)
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
            elif options.get('query'):
                self.stderr.write("Updating by query not yet implemented.")
                sys.exit(1)
            elif options.get('item'):
                for item in args:
                    try:
                        int(item)
                    except ValueError:
                        self.stderr.write('Error: Item "%s" could not be '
                                          'converted to an ID.\n' % item)
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
            elif options.get('item'):
                for item in args:
                    try:
                        int(item)
                    except ValueError:
                        self.stderr.write('Error: Item "%s" could not be '
                                          'converted to an ID.\n' % item)
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
