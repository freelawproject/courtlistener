import argparse
import csv
import os

from celery.canvas import chain
from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.tasks import get_pacer_case_id_and_title, \
    get_docket_by_pacer_case_id
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.tasks import add_or_update_recap_docket

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

TAG = 'ILNB-KESSLER'


def get_dockets(options):
    """Download the dockets described in the CSV
    """
    f = options['file']
    reader = csv.DictReader(f)
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    pacer_session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    pacer_session.login()
    for i, row in enumerate(reader):
        if i < options['offset']:
            continue
        if i >= options['limit'] > 0:
            break

        if i % 1000 == 0:
            pacer_session = PacerSession(username=PACER_USERNAME,
                                         password=PACER_PASSWORD)
            pacer_session.login()
            logger.info("Sent %s tasks to celery so far." % i)
        logger.info("Doing row %s: %s", i)
        throttle.maybe_wait()
        chain(
            get_pacer_case_id_and_title.s(
                pass_through=None,
                # Makes a value like 2000-257, which works fine.
                docket_number='%s-%s' % (row['filecy'], row['docket']),
                court_id='ilnb',
                cookies=pacer_session.cookies,
                office_number=row['office'],
                docket_number_letters='bk',
            ).set(queue=q),
            get_docket_by_pacer_case_id.s(
                court_id='ilnb',
                cookies=pacer_session.cookies,
                tag_names=[TAG],
                **{
                    'show_parties_and_counsel': True,
                    'show_terminated_parties': True,
                    'show_list_of_member_cases': True
                }
            ).set(queue=q),
            add_or_update_recap_docket.s().set(queue=q),
        ).apply_async()


class Command(VerboseCommand):
    help = "Look up dockets from a spreadsheet for a client and download them."

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            default='io_bound',
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
        get_dockets(options)

