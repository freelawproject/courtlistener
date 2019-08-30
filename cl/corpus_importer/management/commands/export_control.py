import argparse
import csv
import os

from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.task_canvases import get_docket_and_claims
from cl.corpus_importer.tasks import save_ia_docket_to_disk
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Court, Docket

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

TAG = 'RllVuRYPZETjSCTkDp-TCIL'
TAG_IDB_SAMPLE = 'xJwsPIosbuXPGeFblc-TCIL'

BULK_OUTPUT_DIRECTORY = '/tmp/fdd-export/'

def do_bulk_export(options):
    """The final step of this project is to bulk export an outrageous
    amount of bankruptcy data from our system.

    Limit/offset work differently than in many other functions. Limit is a
    true hard limit to the number that should get done. A limit of 10 means
    ten items will be done. Offset corresponds to the docket PK below which you
    do not want to process. (It does *not* correspond to the number of
    completed items.)
    """
    q = options['queue']
    offset = options['offset']
    throttle = CeleryThrottle(queue_name=q)
    if offset > 0:
        logger.info("Skipping to dockets with PK greater than %s", offset)
    d_pks = Docket.objects.filter(
        court__jurisdiction=Court.FEDERAL_BANKRUPTCY,
        pk__gt=offset,
    ).order_by('pk').values_list('pk', flat=True)
    for i, d_pk in enumerate(d_pks):
        if i >= options['limit'] > 0:
            break
        logger.info("Doing item %s with pk %s", i, d_pk)
        throttle.maybe_wait()
        save_ia_docket_to_disk.apply_async(args=(d_pk, BULK_OUTPUT_DIRECTORY),
                                           queue=q)



def get_data(options, row_transform, tags):
    """Download dockets from a csv, then download claims register data
    from those dockets.

    :param options: The options provided at the command line.
    :param row_transform: A function that takes the row as an argument and
    returns a cleaned up version of the row that has the needed attributes.
    This parameter allows this function to be able to work with almost any
    CSV.
    :param tags: Tags you wish to apply to the gathered data.
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
        row = row_transform(row)
        logger.info("Doing row %s: %s", i, row)
        throttle.maybe_wait()
        get_docket_and_claims(
            row['docket_number'],
            row['court'],
            row['case_name'],
            session.cookies,
            tags,
            q,
        )


def tcil_row_transform(row):
    """A small helper to tune up the row from the tcil spreadsheet"""
    row['docket_number'] = row['Docket #'].strip()
    row['court'] = row['Court'].strip()
    row['case_name'] = row['Case name'].strip()
    return row


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
    row['docket_number'] = '%s-%s' % (row['DOCKET'][0:2],
                                      row['DOCKET'][2:])
    return row


class Command(VerboseCommand):
    help = "Look up dockets from a spreadsheet for a client and download them."
    tasks = ('fdd_export', 'idb_sample', 'bulk_export')

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
            help="The task to perform. One of %s" % ', '.join(self.tasks),
            required=True,
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
            required=False,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        logger.info("Using PACER username: %s" % PACER_USERNAME)
        if options['task'] == 'fdd_export':
            get_data(
                options,
                tcil_row_transform,
                [TAG],
            )
        elif options['task'] == 'idb_sample':
            get_data(
                options,
                idb_row_transform,
                [TAG_IDB_SAMPLE]
            )
        elif options['task'] == 'bulk_export':
            do_bulk_export(options)
        else:
            raise NotImplementedError(
                "Unknown task: %s. Valid tasks are: %s" % (
                    options['task'], ', '.join(self.tasks)))

