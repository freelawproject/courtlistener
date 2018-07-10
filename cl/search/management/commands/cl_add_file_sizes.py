from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.db_tools import queryset_generator
from cl.search.models import RECAPDocument


class Command(VerboseCommand):
    help = 'Save file sizes for all items in RECAP'

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        qs = RECAPDocument.objects.filter(is_available=True)
        for i, rd in enumerate(queryset_generator(qs)):
            rd.file_size = rd.filepath_local.size
            rd.save()
            if i % 1000 == 0:
                logger.info("Completed %s items", i)

