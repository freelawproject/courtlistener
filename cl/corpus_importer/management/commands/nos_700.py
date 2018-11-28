import os

from celery.canvas import chain
from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.task_canvases import get_district_attachment_pages
from cl.corpus_importer.tasks import get_pacer_case_id_and_title, \
    get_docket_by_pacer_case_id, make_fjc_idb_lookup_params, \
    filter_docket_by_tags
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.recap.constants import LABOR_MANAGEMENT_RELATIONS_ACT, \
    FAIR_LABOR_STANDARDS_ACT_CV, LABOR_MANAGEMENT_REPORT_DISCLOSURE, \
    RAILWAY_LABOR_ACT, FAMILY_AND_MEDICAL_LEAVE_ACT, LABOR_LITIGATION_OTHER, \
    EMPLOYEE_RETIREMENT_INCOME_SECURITY_ACT
from cl.recap.models import FjcIntegratedDatabase
from cl.search.models import RECAPDocument
from cl.search.tasks import add_or_update_recap_docket

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

TAG = 'pQuGjNMncnYealSvVjwL'
TAG_SAMPLE = 'KzulifmXjVaknYcKpFxz'


def get_docket_sample(options):
    sample_size = 1000
    get_dockets(options, sample_size)


def get_dockets(options, sample_size=0):
    """Download dockets from PACER matching the 7xx series of NOS codes.

    :param sample_size: The number of items to get. If 0, get them all. Else,
    get only this many and do it randomly.
    """
    nos_codes = [LABOR_LITIGATION_OTHER,
                 LABOR_MANAGEMENT_RELATIONS_ACT,
                 LABOR_MANAGEMENT_REPORT_DISCLOSURE,
                 FAIR_LABOR_STANDARDS_ACT_CV,
                 RAILWAY_LABOR_ACT,
                 FAMILY_AND_MEDICAL_LEAVE_ACT,
                 EMPLOYEE_RETIREMENT_INCOME_SECURITY_ACT]
    items = FjcIntegratedDatabase.objects.filter(
        nature_of_suit__in=nos_codes,
        date_terminated__gt='2009-01-01',
        date_filed__gt='2009-01-01'
    )
    if sample_size > 0:
        items = items.order_by('?')[:sample_size]
        tags = [TAG, TAG_SAMPLE]
    else:
        tags = [TAG]

    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()
    for i, row in enumerate(items):
        if i < options['offset']:
            continue
        if i >= options['limit'] > 0:
            break

        if i % 5000 == 0:
            # Re-authenticate just in case the auto-login mechanism isn't
            # working.
            session = PacerSession(username=PACER_USERNAME,
                                   password=PACER_PASSWORD)
            session.login()

        # All tests pass. Get the docket.
        logger.info("Doing row %s: %s", i, row)

        throttle.maybe_wait()
        params = make_fjc_idb_lookup_params(row)
        chain(
            get_pacer_case_id_and_title.s(
                docket_number=row.docket_number,
                court_id=row.district_id,
                cookies=session.cookies,
                **params
            ).set(queue=q),
            filter_docket_by_tags.s(tags, row.district_id).set(queue=q),
            get_docket_by_pacer_case_id.s(
                court_id=row.district_id,
                cookies=session.cookies,
                tag_names=tags,
                use_existing_entries=False,
                **{
                    'show_parties_and_counsel': True,
                    'show_terminated_parties': True,
                    'show_list_of_member_cases': True
                }
            ).set(queue=q),
            add_or_update_recap_docket.s().set(queue=q),
        ).apply_async()


def get_attachment_pages(options):
    rd_pks = RECAPDocument.objects.filter(
        tags__name=TAG,
        docket_entry__description__icontains='attachment',
    ).values_list('pk', flat=True)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()
    get_district_attachment_pages(options=options, rd_pks=rd_pks,
                                  tag_names=[TAG], session=session)


class Command(VerboseCommand):
    help = "Look up a sample of dockets from the " \
           "IDB to get an approximate cost"

    allowed_tasks = [
        'docket_sample',
        'docket_all',
        'district_attachments',
    ]

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
            '--limit',
            type=int,
            default=0,
            help="After doing this number, stop. This number is not additive "
                 "with the offset parameter. Default is to do all of them.",
        )
        parser.add_argument(
            '--task',
            type=str,
            required=True,
            help="What task are we doing at this point?",
        )

    def handle(self, *args, **options):
        logger.info("Using PACER username: %s" % PACER_USERNAME)
        if options['task'] == 'docket_sample':
            get_docket_sample(options)
        elif options['task'] == 'docket_all':
            get_dockets(options)
        elif options['task'] == 'district_attachments':
            get_attachment_pages(options)
