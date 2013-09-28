import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from datetime import datetime

from alert.search.models import Document
from alert.lib.dump_lib import make_dump_file
from alert.lib.db_tools import queryset_generator_by_date
from alert.settings import DUMP_DIR
from django.utils.timezone import now, utc


def main():
    """
    A simple function that dumps all cases to a single dump file. Rotates out
    the old file before deleting it.
    """
    start_date = datetime(1754, 9, 1, tzinfo=utc)  # First American case
    end_date = now()
    # Get the documents from the database.
    qs = Document.objects.all()
    docs_to_dump = queryset_generator_by_date(
        qs,
        'date_filed',
        start_date,
        end_date
    )

    path_from_root = DUMP_DIR
    filename = 'all.xml'
    make_dump_file(docs_to_dump, path_from_root, filename)

    exit(0)

if __name__ == '__main__':
    main()
