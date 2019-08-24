import argparse
import csv
import os

from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.task_canvases import get_docket_and_claims
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Court

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

TAG = 'RllVuRYPZETjSCTkDp-TCIL'
TAG_IDB_SAMPLE = 'xJwsPIosbuXPGeFblc-TCIL'


def get_data(options, field_map, row_transform, tags):
    """Download dockets from their list, then download claims register data
    from those dockets.
    """
    f = options['file']
    reader = csv.DictReader(f)
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()
    for i, row in enumerate(reader):
        if i < options['offset']:
            continue
        if i >= options['limit'] > 0:
            break

        # All tests pass. Get the docket.
        logger.info("Doing row %s: %s", i, row)
        row = row_transform(row)
        throttle.maybe_wait()
        get_docket_and_claims(
            row[field_map['docket_number']].strip(),
            row[field_map['court']].strip(),
            row.get(field_map['case_name'], '').strip(),
            session.cookies,
            tags,
            q,
        )


def idb_row_transform(row):
    """A small helper function to tune up the row.

    :param row: A dict of the row from the CSV
    :return row: A transformed version of the row
    """
    # Convert the court field from theirs to something bearable
    row['court'] = Court.objects.get(
        fjc_court_id=row['DISTRICT'],
        jurisdiction=Court.FEDERAL_BANKRUPTCY
    ).pk

    # Set the case name to None. Alas, we don't get it, but we probably don't
    # need it either.
    row['case_name'] = None

    # Make a docket number. Combination of the two digit year and a five digit
    # 0-padded serial number.
    row['docket_number'] = '%s-%s' % (row['FILECY'][2:4],
                                      row['DOCKET'].rjust(5, '0'))
    return row


class Command(VerboseCommand):
    help = "Look up dockets from a spreadsheet for a client and download them."

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            '--offset',
            type=int,
            default=0,
            help="The number of items to skip before beginning. Default is to "
                 "skip none.",
        )
        parser.add_argument(
            '--task',
            type=str,
            help="The task to perform. Either fdd_export, or idb_sample",
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help="After doing this number, stop. This number is not additive "
                 "with the offset parameter. Default is to do all of them.",
        )
        parser.add_argument(
            '--file',
            type=argparse.FileType('r'),
            help="Where is the CSV that has the information about what to "
                 "download?",
            required=True,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        logger.info("Using PACER username: %s" % PACER_USERNAME)
        if options['task'] == 'fdd_export':
            get_data(
                options,
                {'docket_number': 'Docket #', 'court': 'Court',
                 'case_name': 'Case name'},
                None,
                [TAG],
            )
        elif options['task'] == 'idb_sample':
            get_data(
                options,
                {'docket_number': 'docket_number', 'court': 'court',
                 'case_name': 'case_name'},
                idb_row_transform,
                [TAG_IDB_SAMPLE]
            )
        else:
            NotImplementedError("Unknown task: %s" % options['task'])

