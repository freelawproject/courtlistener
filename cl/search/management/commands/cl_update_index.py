import ast
import sys
import time
from cl.audio.models import Audio
from cl.lib import sunburnt
from cl.lib.argparse_types import valid_date_time, valid_obj_type, valid_source
from cl.lib.db_tools import queryset_generator
from cl.lib.timer import print_timing
from cl.search.models import Opinion, Docket
from cl.search.tasks import (delete_items, add_or_update_audio_files,
                             add_or_update_opinions, add_or_update_items)
from celery.task.sets import TaskSet
from django.core.management.base import BaseCommand


def proceed_with_deletion(out, count, noinput):
    """
    Checks whether we want to proceed to delete (lots of) items
    """
    if noinput:
        return True

    proceed = True
    out.write("\n")
    yes_or_no = raw_input('WARNING: Are you **sure** you want to delete all '
                          '%s items? [y/N] ' % count)
    out.write('\n')
    if not yes_or_no.lower().startswith('y'):
        out.write("No action taken.\n")
        proceed = False

    if count > 10000 and proceed is True:
        # Double check...something might be off.
        yes_or_no = raw_input('Are you double-plus sure? There are an awful '
                              'lot of items here? [y/N] ')
        if not yes_or_no.lower().startswith('y'):
            out.write("No action taken.\n")
            proceed = False

    return proceed


class Command(BaseCommand):
    help = ('Adds, updates, deletes items in an index, committing changes and '
            'optimizing it, if requested.')

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.solr_url = None
        self.si = None
        self.verbosity = None
        self.options = []
        self.type = None
        self.noinput = None

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=valid_obj_type,
            required=True,
            help='Because the Solr indexes are loosely bound to the database, '
                 'commands require that the correct model is provided in this '
                 'argument. Current choices are "audio", "opinions" and "dockets".'
        )
        parser.add_argument(
            '--solr-url',
            required=True,
            type=str,
            help='When swapping cores, it can be valuable to use a temporary '
                 'Solr URL, overriding the default value that\'s in the '
                 'settings, e.g., http://127.0.0.1:8983/solr/swap_core'
        )
        parser.add_argument(
            '--noinput',
            action='store_true',
            help="Do NOT prompt the user for input of any kind. Useful in "
                 "tests, but can disable important warnings."
        )

        actions_group = parser.add_mutually_exclusive_group()
        actions_group.add_argument(
            '--update',
            action='store_true',
            default=False,
            help='Run the command in update mode. Use this to add or update '
                 'items.'
        )
        actions_group.add_argument(
            '--delete',
            action='store_true',
            default=False,
            help='Run the command in delete mode. Use this to remove  items '
                 'from the index. Note that this will not delete items from '
                 'the index that do not continue to exist in the database.'
        )

        parser.add_argument(
            '--optimize',
            action='store_true',
            default=False,
            help='Run the optimize command against the current index after '
                 'any updates or deletions are completed.'
        )
        parser.add_argument(
            '--do-commit',
            action='store_true',
            default=False,
            help='Performs a simple commit and nothing more.'
        )
        parser.add_argument(
            '--source',
            type=valid_source,
            help='Take action on only the Dockets from RECAP stored in the local database.'
        )

        act_upon_group = parser.add_mutually_exclusive_group()
        act_upon_group.add_argument(
            '--everything',
            action='store_true',
            default=False,
            help='Take action on everything in the database',
        )
        act_upon_group.add_argument(
            '--query',
            help='Take action on items fulfilling a query. Queries should be '
                 'formatted as Python dicts such as: "{\'court_id\':\'haw\'}"'
        )
        act_upon_group.add_argument(
            '--items',
            type=int,
            nargs='*',
            help='Take action on a list of items using a single '
                 'Celery task'
        )
        act_upon_group.add_argument(
            '--datetime',
            type=valid_date_time,
            help='Take action on items newer than a date (YYYY-MM-DD) or a '
                 'date and time (YYYY-MM-DD HH:MM:SS)'
        )

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.solr_url = options['solr_url']
        self.si = sunburnt.SolrInterface(self.solr_url, mode='rw')
        self.options = options
        self.type = options['type']
        self.noinput = options['noinput']

        if options['update']:
            if self.verbosity >= 1:
                self.stdout.write('Running in update mode...\n')
            if options.get('everything'):
                source_val = None
                if options.get('source'):
                    source_val = options['source']
                self.add_or_update_all(source_val)
            elif options.get('datetime'):
                self.add_or_update_by_datetime(options['datetime'])
            elif options.get('query'):
                self.stderr.write("Updating by query not implemented.")
                sys.exit(1)
            elif options.get('items'):
                self.add_or_update(*options['items'])

        elif options.get('delete'):
            if self.verbosity >= 1:
                self.stdout.write('Running in deletion mode...\n')
            if options.get('everything'):
                self.delete_all()
            elif options.get('datetime'):
                self.delete_by_datetime(options['datetime'])
            elif options.get('query'):
                self.delete_by_query(options['query'])
            elif options.get('items'):
                self.delete(*options['items'])
            #elif options.get('recap'):
                #self.delete_all_recap_dockets()

        elif options.get('do_commit'):
            self.commit()

        elif options.get('optimize'):
            self.optimize()

        else:
            self.stderr.write('Error: You must specify whether you wish to '
                              'update, delete, commit, or optimize your '
                              'index.\n')
            sys.exit(1)

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
    def delete(self, items):
        """
        Given an item, creates a Celery task to delete it.
        """
        self.stdout.write("Deleting items(s): %s\n" % items)
        delete_items.delay(items, self.solr_url)

    def delete_all(self):
        """
        Deletes all items from the database.
        """
        count = self.si.raw_query(
            **{'q': '*:*', 'caller': 'cl_update_index:delete_all', }).count()

        if proceed_with_deletion(self.stdout, count, self.noinput):
            self.stdout.write('Removing all items from your index because '
                              'you said so.\n')
            self.stdout.write('  Marking all items as deleted...\n')
            self.si.delete_all()
            self.stdout.write('  Committing the deletion...\n')
            self.si.commit()
            self.stdout.write('\nDone. The index located at: %s\n'
                              'is now empty.\n' % self.solr_url)

    @print_timing
    def delete_by_datetime(self, dt):
        """
        Given a datetime, deletes all items in the index newer than that time.

        Relies on the items still being in the database.
        """
        qs = self.type.objects.filter(
            date_created__gt=dt
        ).values_list(
            'pk',
            flat=True,
        )
        count = qs.count()
        if proceed_with_deletion(self.stdout, count, self.noinput):
            self.stdout.write("Deleting all item(s) newer than %s\n" % dt)
            self.si.delete(list(qs))
            self.si.commit()

    @print_timing
    def delete_by_query(self, query):
        """
        Given a query, deletes all the items that match that query.
        """
        query_dict = ast.literal_eval(query)
        count = self.si.query(self.si.Q(**query_dict)).count()
        if proceed_with_deletion(self.stdout, count, self.noinput):
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
        if self.type == Opinion:
            add_or_update_opinions.delay(items)
        elif self.type == Audio:
            add_or_update_audio_files.delay(items)

    @print_timing
    def add_or_update_by_datetime(self, dt):
        """
        Given a datetime, adds or updates all items newer than that time.
        """
        self.stdout.write("Adding or updating items(s) newer than %s\n" % dt)
        qs = self.type.objects.filter(date_created__gte=dt)
        items = queryset_generator(qs, chunksize=5000)
        count = qs.count()
        self._chunk_queryset_into_tasks(items, count)

    @print_timing
    def add_or_update_all(self, source=None):
        """
        Iterates over the entire corpus, adding it to the index. Can be run on
        an empty index or an existing one.

        If run on an existing index, existing items will be updated.

        :param source : The source of the items (Optional). One of the constants mentioned in the Docket Model choices.
        """
        self.stdout.write("Adding or updating all items...\n")
        if source:
            q = self.type.objects.filter(source=source)
        else:
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

    def commit(self):
        """Runs a simple commit command.
        """
        self.si.commit()
