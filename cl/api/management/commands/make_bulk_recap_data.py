from django.utils.timezone import now

from cl.api.tasks import write_json_to_disk
from cl.lib.argparse_types import readable_dir
from cl.lib.command_utils import VerboseCommand
from cl.search.api_serializers import FullDocketSerializer
from cl.search.models import Court, Docket


class Command(VerboseCommand):
    help = 'Create the bulk files for all jurisdictions and for "all".'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-directory',
            type=readable_dir,
            required=True,
            help='A directory to place the generated data.',
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        courts = Court.objects.all()

        self.stdout.write('Starting bulk file creation.')
        t1 = now()
        write_json_to_disk(courts, obj_type_str='full-dockets',
                           obj_class=Docket, court_attr='court_id',
                           serializer=FullDocketSerializer,
                           bulk_dir=options['output_directory'])
        t2 = now()
        self.stdout.write("Completed in %s" % (t2 - t1))
