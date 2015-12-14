import os

from django.core.management import BaseCommand

from cl.api.tasks import make_bulk_data_and_swap_it_in, swap_archives
from cl.audio.models import Audio
from cl.search.models import Court, Docket, Opinion, OpinionCluster
from cl.lib.utils import mkdir_p


class Command(BaseCommand):
    help = 'Create the bulk files for all jurisdictions and for "all".'

    def handle(self, *args, **options):
        courts = Court.objects.all()

        from cl.search import api3

        # Make the main bulk files
        arg_tuples = (
            ('document', OpinionCluster, 'docket.court_id', api3.DocumentResource),
            ('audio', Audio, 'docket.court_id', api3.AudioResource),
            ('docket', Docket, 'court_id', api3.DocketResource),
            ('jurisdiction', Court, 'pk', api3.JurisdictionResource),
        )

        print 'Starting bulk file creation with %s celery tasks...' % \
              len(arg_tuples)
        for arg_tuple in arg_tuples:
            make_bulk_data_and_swap_it_in.delay(arg_tuple, courts)

        # Make the citation bulk data
        print ' - Creating bulk data CSV for citations...'
        self.make_citation_data()
        print "   - Swapping in the new citation archives..."
        swap_archives('citation')

        print 'Done.\n'

    @staticmethod
    def make_citation_data():
        """Because citations are paginated and because as of this moment there
        are 11M citations in the database, we cannot provide users with a bulk
        data file containing the complete objects for every citation.

        Instead of doing that, we dump our citation table with a shell command,
        which provides people with compact and reasonable data they can import.
        """
        mkdir_p('/tmp/bulk/citation')

        print '   - Copying the Document_opinions_cited table to disk...'

        # This command calls the psql COPY command and requests that it dump
        # the document_id and citation_id columns from the
        # Document_opinions_cited table to disk as a compressed CSV.
        os.system(
            '''psql -c "COPY \\"search_opinionscited\\" (from_document, to_document) to stdout DELIMITER ',' CSV HEADER" -d courtlistener --username django | gzip > /tmp/bulk/citation/all.csv.gz'''
        )
        print '   - Table created successfully.'
