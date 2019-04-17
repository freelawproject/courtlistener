from django.core.exceptions import ValidationError

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.db_tools import queryset_generator
from cl.search.models import RECAPDocument


class Command(VerboseCommand):
    help = 'Save file sizes for all items in RECAP'

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        qs = RECAPDocument.objects.filter(is_available=True, file_size=None)
        for i, rd in enumerate(queryset_generator(qs)):
            try:
                rd.file_size = rd.filepath_local.size
            except OSError as e:
                if e.errno != 2:
                    # Problem other than No such file or directory.
                    raise
                continue
            except ValueError:
                #  The 'filepath_local' attribute has no file
                # associated with it.
                continue
            try:
                rd.save()
            except ValidationError:
                # [u'Duplicate values violate save constraint. An object with
                # this document_number and docket_entry already exists:
                # (8, 16188376)']
                continue
            if i % 1000 == 0:
                logger.info("Completed %s items", i)

