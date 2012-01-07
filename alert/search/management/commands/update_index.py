

import sys

from alert.lib import sunburnt
from alert.lib.db_tools import queryset_iterator
from alert.search.models import Document
from alert.search.search_indexes import InvalidDocumentError
from alert.search.search_indexes import SearchDocument
# Celery requires imports like this. Disregard syntax error.
from search.tasks import delete_docs
from search.tasks import add_or_update_docs

from django.conf import settings
from django.core.management.base import BaseCommand
from optparse import make_option

class Command(BaseCommand):
    '''
    Builds the index from scratch. First deletes all values. Use with caution.
    '''
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
        sys.exit(0)

    def add_or_update(self, *documents):
        '''
        Given a document, adds it to the index, or updates it if it's already
        in the index.
        '''
        self.stdout.write("Adding or updating document(s): %s\n" % list(documents))
        # Use Celery to add or update the document asynrhronously
        add_or_update_docs.delay(documents)

    def add_or_update_all(self):
        '''
        Iterates over the entire corpus, adding it to the index. Can be run on 
        an empty index or an existing one. If run on an existing index,
        existing documents will be updated.
        '''
        self.stdout.write("Adding or updating all documents.\n")
        everything = queryset_iterator(Document.objects.filter(court__in_use=True))
        for doc in everything:
            # Make a search doc, and add it to the index
            if self.verbosity >= 2:
                self.stdout.write('Indexing document %s' % doc.pk)
            try:
                search_doc = SearchDocument(doc)
                self.si.add(search_doc)
            except InvalidDocumentError:
                if self.verbosity >= 1:
                    self.stderr.write('InvalidDocumentError: Unable to index document %s\n' % doc.pk)
                pass
        self.stderr.write('Committing all documents to the index...\n')
        self.si.commit()


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

        else:
            self.stderr.write('Error: You must specify whether you wish to update or delete documents.\n')
            sys.exit(1)



