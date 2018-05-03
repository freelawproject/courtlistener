from django.utils.timezone import now

from cl.api.tasks import write_json_to_disk
from cl.lib.argparse_types import readable_dir
from cl.lib.command_utils import VerboseCommand
from cl.people_db.api_serializers import PartySerializer, AttorneySerializer
from cl.people_db.models import Party, Attorney
from cl.search.api_serializers import FullDocketSerializer
from cl.search.models import Court, Docket


class Command(VerboseCommand):
    help = 'Create the bulk files for all jurisdictions and for "all".'

    data_types = {
        1: {
            'obj_type_str': 'full-dockets',
            'obj_class': Docket,
            'court_attr': 'court_id',
            'serializer': FullDocketSerializer,
        },
        2: {
            'obj_type_str': 'parties',
            'obj_class': Party,
            'court_attr': None,
            'serializer': PartySerializer,
        },
        3: {
            'obj_type_str': 'attorneys',
            'obj_class': Attorney,
            'court_attr': None,
            'serializer': AttorneySerializer,
        },
    }

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-directory',
            type=readable_dir,
            required=True,
            help='A directory to place the generated data.',
        )
        parser.add_argument(
            '--data-types',
            type=int,
            default=[1, 2, 3],
            nargs='*',
            help="The types of data to generate. Possibilities are:\n%s" %
                 self.data_types,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        courts = Court.objects.all()

        for data_type in options['data_types']:
            kwargs = self.data_types[data_type]
            self.stdout.write("Starting bulk file creation of '%s'" %
                              kwargs['obj_type_str'])
            t1 = now()

            write_json_to_disk(courts, bulk_dir=options['output_directory'],
                               **kwargs)
            t2 = now()
            self.stdout.write("Completed in %s" % (t2 - t1))
