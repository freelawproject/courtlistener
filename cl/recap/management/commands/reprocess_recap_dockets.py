
import sys

from django.db import IntegrityError

from cl.lib.command_utils import VerboseCommand
from cl.lib.db_tools import queryset_generator
from cl.search.models import Docket


class Command(VerboseCommand):
    help = 'Reprocess all dockets in the RECAP Archive.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-pk',
            type=int,
            default=0,
            help="Skip any primary keys lower than this value. (Useful for "
                 "restarts.)",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        ds = Docket.objects.filter(
            source__in=Docket.RECAP_SOURCES
        ).only(
            'pk',
            'case_name',
        )
        count = ds.count()
        for i, d in enumerate(queryset_generator(ds, chunksize=50000)):
            sys.stdout.write('\rDoing docket: %s of %s, with pk: %s' %
                             (i, count, d.pk))
            sys.stdout.flush()
            if d.pk < options['start_pk'] > 0:
                continue

            try:
                d.reprocess_recap_content(do_original_xml=True)
            except IntegrityError:
                # Happens when there's wonkiness in the source data. Move on.
                continue
