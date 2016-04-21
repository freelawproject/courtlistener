import os
import shutil
from os.path import join

from django.conf import settings
from django.core.management import BaseCommand

from cl.api.tasks import make_bulk_data_and_swap_it_in
from cl.audio.api_serializers import AudioSerializer
from cl.audio.models import Audio
from cl.lib.utils import mkdir_p
from cl.people_db.api_serializers import PersonSerializer, PositionSerializer, \
    RetentionEventSerializer, EducationSerializer, SchoolSerializer, \
    PoliticalAffiliationSerializer
from cl.people_db.models import Person, Position, RetentionEvent, Education, \
    School, PoliticalAffiliation
from cl.search.api_serializers import OpinionClusterSerializer, \
    OpinionSerializer, DocketSerializer, CourtSerializer
from cl.search.models import Court, Docket, OpinionCluster, Opinion


class Command(BaseCommand):
    help = 'Create the bulk files for all jurisdictions and for "all".'

    def handle(self, *args, **options):
        courts = Court.objects.all()

        # Make the main bulk files
        kwargs_list = [
            {
                'obj_type_str': 'clusters',
                'obj_type': OpinionCluster,
                'court_attr': 'docket.court_id',
                'serializer': OpinionClusterSerializer,
            },
            {
                'obj_type_str': 'opinions',
                'obj_type': Opinion,
                'court_attr': 'cluster.docket.court_id',
                'serializer': OpinionSerializer,
            },
            {
                'obj_type_str': 'dockets',
                'obj_type': Docket,
                'court_attr': 'court_id',
                'serializer': DocketSerializer,
            },
            {
                'obj_type_str': 'courts',
                'obj_type': Court,
                'court_attr': None,
                'serializer': CourtSerializer,
            },
            {
                'obj_type_str': 'audio',
                'obj_type': Audio,
                'court_attr': 'docket.court_id',
                'serializer': AudioSerializer,
            },
            {
                'obj_type_str': 'people',
                'obj_type': Person,
                'court_attr': None,
                'serializer': PersonSerializer,
            },
            {
                'obj_type_str': 'schools',
                'obj_type': School,
                'court_attr': None,
                'serializer': SchoolSerializer,
            },
            {
                'obj_type_str': 'positions',
                'obj_type': Position,
                'court_attr': None,
                'serializer': PositionSerializer,
            },
            {
                'obj_type_str': 'retention-events',
                'obj_type': RetentionEvent,
                'court_attr': None,
                'serializer': RetentionEventSerializer,
            },
            {
                'obj_type_str': 'educations',
                'obj_type': Education,
                'court_attr': None,
                'serializer': EducationSerializer,
            },
            {
                'obj_type_str': 'politicial-affiliations',
                'obj_type': PoliticalAffiliation,
                'court_attr': None,
                'serializer': PoliticalAffiliationSerializer,
            },
        ]

        print 'Starting bulk file creation with %s celery tasks...' % \
              len(kwargs_list)
        for kwargs in kwargs_list:
            make_bulk_data_and_swap_it_in.delay(courts, kwargs)

        # Make the citation bulk data
        obj_type_str = 'citations'
        print ' - Creating bulk data CSV for citations...'
        tmp_destination = join(settings.BULK_DATA_DIR, 'tmp', obj_type_str)
        final_destination = join(settings.BULK_DATA_DIR, obj_type_str)
        self.make_citation_data(tmp_destination, obj_type_str)
        print "   - Swapping in the new citation archives..."

        mkdir_p(join(settings.BULK_DATA_DIR, obj_type_str))
        shutil.move(
            join(tmp_destination, 'all.csv.gz'),
            join(final_destination, 'all.csv.gz'),
        )

        print 'Done.\n'

    @staticmethod
    def make_citation_data(tmp_destination, obj_type_str):
        """Because citations are paginated and because as of this moment there
        are 11M citations in the database, we cannot provide users with a bulk
        data file containing the complete objects for every citation.

        Instead of doing that, we dump our citation table with a shell command,
        which provides people with compact and reasonable data they can import.
        """
        mkdir_p(tmp_destination)

        print '   - Copying the citations table to disk...'

        # This command calls the psql COPY command and requests that it dump
        # the citation table to disk as a compressed CSV.
        os.system(
            '''PGPASSWORD="{password}" psql -c "COPY \\"search_opinionscited\\" (citing_opinion_id, cited_opinion_id) to stdout DELIMITER ',' CSV HEADER" -d {database} --username {username} | gzip > {destination}'''.format(
                password=settings.DATABASES['default']['PASSWORD'],
                database=settings.DATABASES['default']['NAME'],
                username=settings.DATABASES['default']['USER'],
                destination=join(tmp_destination, 'all.csv.gz'),
            )
        )
        print '   - Table created successfully.'
