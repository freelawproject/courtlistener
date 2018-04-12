
import sys

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.db_tools import queryset_generator
from cl.search.models import Docket


class Command(VerboseCommand):
    help = 'Reprocess all dockets in the RECAP Archive.'

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
            logger.info("Reprocessing %s: %s" % (d.pk, d.case_name))
            d.reprocess_recap_content(do_original_xml=True)
