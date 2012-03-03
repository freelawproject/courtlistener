# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import sys

from alert.lib import sunburnt
from alert.lib.db_tools import queryset_iterator
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
import time

class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--update',
            action='store_true',
            dest='update_mode',
            default=False,
            help='Run the command in update mode. Use this to add or update documents.'),
        make_option('--delete',
            action='store_true',
            dest='delete_mode',
            default=False,
            help='Run the command in delete mode. Use this to remove documents from the index.'),
        make_option('--optimize',
            action='store_true',
            dest='optimize_mode',
            default=False,
            help=('Run the optimize command against the current index. Note '
                  'that the index is always optimized after updating everything.')),
        make_option('--everything',
            action='store_true',
            dest='everything',
            default=False,
            help='Take action on everything in the database'),
        make_option('--document',
            action='store_true',
            dest='document',
            default=False,
            help='Take action on a list of documents using a single Celery task'),
        make_option('--debug',
            action='store_true',
            dest='debug',
            default=False,
            help='Run the command, but take no action. Be verbose.'),
        )
    args = '(--update | --delete) (--everything | --document <doc_id> <doc_id>) [--debug]'
    help = 'Adds, updates or removes documents in the index.'

    @print_timing
    def delete(self, *documents):
        '''
        Given a document, creates a Celery task to delete it.
        '''
        self.stdout.write("Deleting document(s): %s\n" % list(documents))
        # Use Celery to delete the document asynrhronously
        delete_docs.delay(documents)

    def delete_all(self):
        '''
        Deletes all documents from the database.
        '''
        self.stdout.write("\n")
        yes_or_no = raw_input("WARNING: Are you **sure** you want to delete all documents? [y/N] ")
        self.stdout.write('\n')
        if not yes_or_no.lower().startswith('y'):
            self.stdout.write("No action taken.\n")
            sys.exit(0)

        if self.verbosity >= 1:
            self.stdout.write('Removing all documents from your index because you said so.\n')

        if self.verbosity >= 1:
            self.stdout.write('Marking all documents as deleted...\n')
        self.si.delete_all()
        if self.verbosity >= 1:
            self.stdout.write('Committing the deletion...\n')
        self.si.commit()
        self.stdout.write('\nDone. Your index has been emptied. Hope this is what you intended.\n')

    @print_timing
    def add_or_update(self, *documents):
        '''
        Given a document, adds it to the index, or updates it if it's already
        in the index.
        '''
        self.stdout.write("Adding or updating document(s): %s\n" % list(documents))
        # Use Celery to add or update the document asynrhronously
        add_or_update_docs.delay(documents)

    @print_timing
    def add_or_update_all(self):
        '''
        Iterates over the entire corpus, adding it to the index. Can be run on 
        an empty index or an existing one. If run on an existing index,
        existing documents will be updated.
        '''
        self.stdout.write("Adding or updating all documents...\n")
        everything = queryset_iterator(Document.objects.all())
        count = Document.objects.all().count()
        processed_count = 0
        not_in_use = 0
        subtasks = []
        for doc in everything:
            # Make a search doc, and add it to the index
            if self.verbosity >= 2:
                self.stdout.write('Indexing document %s' % doc.pk)
            if doc.court.in_use == True:
                subtasks.append(add_or_update_doc_object.subtask((doc,)))
                processed_count += 1
            else:
                # The document is in an unused court
                not_in_use += 1

            last_document = (count == processed_count + not_in_use)
            if (processed_count % 1000 == 0) or last_document:
                # Every 1000 documents, we send the subtasks off for processing
                job = TaskSet(tasks=subtasks)
                result = job.apply_async()
                while not result.ready():
                    time.sleep(5)

                # The jobs finished - clean things up for the next round
                subtasks = []

                # Do a commit every 1000 items, for good measure.
                self.si.commit()

            self.stdout.write("\rProcessed %d of %d.   Not in use: %d" %
                              (processed_count, count, not_in_use))
        self.stdout.write('\nCommitting last chunk and optimizing the index...\n')
        self.si.optimize()

    @print_timing
    def optimize(self):
        '''Runs the Solr optimize command. 
        
        Not much more than a wrapper of a wrapper (Sunburnt) of a wrapper 
        (Solr). Weird. Thankfully, Lucene isn't a wrapper of anything.
        '''
        self.stdout.write('Optimizing the index...')
        self.si.optimize()
        self.stdout.write('done.\n')

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.si = sunburnt.SolrInterface(settings.SOLR_URL, mode='w')

        if options.get('update_mode'):
            if self.verbosity >= 1:
                self.stdout.write('Running in update mode...\n')
            if options.get('everything'):
                self.add_or_update_all()
            elif options.get('document'):
                for doc in args:
                    try:
                        int(doc)
                    except ValueError:
                        self.stderr.write('Error: Document "%s" could not be converted to an ID.\n' % doc)
                        sys.exit(1)
                self.add_or_update(*args)
            else:
                self.stderr.write('Error: You must specify whether you wish to update everything or a single document.\n')
                sys.exit(1)

        elif options.get('delete_mode'):
            if self.verbosity >= 1:
                self.stdout.write('Running in deletion mode...\n')
            if options.get('everything'):
                self.delete_all()
            elif options.get('document'):
                for doc in args:
                    try:
                        int(doc)
                    except ValueError:
                        self.stderr.write('Error: Document "%s" could not be converted to an ID.\n' % doc)
                        sys.exit(1)
                self.delete(*args)
            else:
                self.stderr.write('Error: You must specify whether you wish to delete everything or a single document.\n')
                sys.exit(1)

        elif options.get('optimize_mode'):
            if self.verbosity >= 1:
                self.stdout.write('Running in optimize mode...\n')
            self.optimize()
            sys.exit(0)

        else:
            self.stderr.write('Error: You must specify whether you wish to update or delete documents.\n')
            sys.exit(1)



