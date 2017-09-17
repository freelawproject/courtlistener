import os
from django.conf import settings
from django.db.models import Q
from juriscraper.pacer.http import PacerSession

from cl.corpus_importer.tasks import get_pacer_case_id_for_idb_row
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.recap.constants import FAIR_LABOR_STANDARDS_ACT_CR,\
    FAIR_LABOR_STANDARDS_ACT_CV
from cl.recap.models import FjcIntegratedDatabase

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)


def get_pacer_case_ids(options, row_pks):
    """Get the PACER case IDs for the given items."""
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    for i, row_pk in enumerate(row_pks):
        throttle.maybe_wait()
        if i % 10000 == 0:
            pacer_session = PacerSession(username=PACER_USERNAME,
                                         password=PACER_PASSWORD)
            pacer_session.login()
        get_pacer_case_id_for_idb_row.apply_async(args=(row_pk, pacer_session),
                                                  queue=q)
        if i % 1000 == 0:
            logger.info("Sent %s tasks to celery so far." % (i + 1))


class Command(VerboseCommand):
    help = "Get all the free content from PACER. There are three modes."

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        row_pks = self.get_komply_ids()
        get_pacer_case_ids(options, row_pks)

    def get_komply_ids(self):
        return FjcIntegratedDatabase.objects.filter(
            Q(nature_of_suit=FAIR_LABOR_STANDARDS_ACT_CV) |
            Q(nature_of_offense=FAIR_LABOR_STANDARDS_ACT_CR),
            pacer_case_id='',
            # date_filed__gt="2017-01-01",
        ).values_list('pk', flat=True)
