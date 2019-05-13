import argparse
import csv
import os

from celery.canvas import chain
from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.tasks import get_pacer_case_id_and_title, \
    get_docket_by_pacer_case_id, get_pacer_doc_by_rd
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import RECAPDocument
from cl.search.tasks import add_or_update_recap_docket, add_items_to_solr

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

TAG = 'ILNB-KESSLER'
TAG_PETITIONS = 'ILNB-KESSLER-PETITIONS'


def make_docket_number(year, docket_number):
    """The docket number field kind of sucks for lookup. Combine it with the
    year to make a better version.

    :param year: The four digit year field from the "filecy" field.
    :param docket_number: The 5-6 digit docket number from the "docket" field.
    :return a string like 20-bk-39238
    """
    docket_serial = docket_number[-5:]
    two_digit_year = year[-2:]
    return '%s-bk-%s' % (two_digit_year, docket_serial)


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
        logger.info("Doing row %s", i)
        throttle.maybe_wait()
        chain(
            get_pacer_case_id_and_title.s(
                pass_through=None,
                docket_number=make_docket_number(row['filecy'], row['docket']),
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


def get_petitions(options):
    """Just get document number one for every docket that's tagged in this
    collection.
    """
    rds = RECAPDocument.objects.filter(
        tags__name=TAG,
        document_number='1',
        document_type=RECAPDocument.PACER_DOCUMENT,
    ).values_list('pk', flat=True).iterator()
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    pacer_session = PacerSession(username=PACER_USERNAME,
                                 password=PACER_PASSWORD)
    pacer_session.login()
    for i, rd_pk in enumerate(rds):
        if i < options['offset']:
            i += 1
            continue
        if i >= options['limit'] > 0:
            break

        if i % 1000 == 0:
            pacer_session = PacerSession(username=PACER_USERNAME,
                                         password=PACER_PASSWORD)
            pacer_session.login()
            logger.info("Sent %s tasks to celery so far." % i)
        logger.info("Doing row %s", i)
        throttle.maybe_wait()

        chain(
            get_pacer_doc_by_rd.s(
                rd_pk, pacer_session.cookies, tag=TAG_PETITIONS).set(queue=q),
            extract_recap_pdf.si(rd_pk).set(queue=q),
            add_items_to_solr.si([rd_pk], 'search.RECAPDocument').set(queue=q),
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
        parser.add_argument(
            '--task',
            type=str,
            required=True,
            help="What task are we doing at this point?",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        logger.info("Using PACER username: %s" % PACER_USERNAME)
        if options['task'] == 'all_dockets':
            get_dockets(options)
        elif options['task'] == 'all_petitions':
            get_petitions(options)

