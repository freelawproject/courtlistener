import os

from celery.canvas import chain
from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.tasks import get_pacer_case_id_and_title, \
    get_docket_by_pacer_case_id
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.recap.constants import LABOR_MANAGEMENT_RELATIONS_ACT, \
    FAIR_LABOR_STANDARDS_ACT_CV, LABOR_MANAGEMENT_REPORT_DISCLOSURE, \
    RAILWAY_LABOR_ACT, FAMILY_AND_MEDICAL_LEAVE_ACT, LABOR_LITIGATION_OTHER, \
    EMPLOYEE_RETIREMENT_INCOME_SECURITY_ACT
from cl.recap.models import FjcIntegratedDatabase
from cl.search.tasks import add_or_update_recap_docket

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

TAG = 'pQuGjNMncnYealSvVjwL'


def get_dockets(options):
    """Download a sample of dockets from PACER matching the 7xx series of NOS
    codes.
    """
    nos_codes = [LABOR_LITIGATION_OTHER,
                 LABOR_MANAGEMENT_RELATIONS_ACT,
                 LABOR_MANAGEMENT_REPORT_DISCLOSURE,
                 FAIR_LABOR_STANDARDS_ACT_CV,
                 RAILWAY_LABOR_ACT,
                 FAMILY_AND_MEDICAL_LEAVE_ACT,
                 EMPLOYEE_RETIREMENT_INCOME_SECURITY_ACT]
    sample_size = 300
    items = FjcIntegratedDatabase.objects.filter(
        nature_of_suit__in=nos_codes,
        date_terminated__gt='2009-01-01',
        date_terminated__lt='2018-10-15',
        date_filed__gt='2009-01-01'
    ).order_by('?')[:sample_size]

    q = options['queue']
    task = options['task']
    throttle = CeleryThrottle(queue_name=q)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()
    for i, row in items:
        if i < options['offset']:
            continue
        if i >= options['limit'] > 0:
            break

        # All tests pass. Get the docket.
        logger.info("Doing row %s: %s", i, row)
        logger.info("This case is from year: %s", row.date_filed.year)

        throttle.maybe_wait()
        case_name = '%s v. %s' % (row.plaintiff, row.defendant)
        chain(
            get_pacer_case_id_and_title.s(
                docket_number=row.docket_number,
                court_id=row.district_id,
                cookies=session.cookies,
                case_name=case_name,
            ).set(queue=q),
            get_docket_by_pacer_case_id.s(
                court_id=row.district_id,
                cookies=session.cookies,
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
    help = "Look up a sample of dockets from the " \
           "IDB to get an approximate cost"

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

    def handle(self, *args, **options):
        logger.info("Using PACER username: %s" % PACER_USERNAME)

