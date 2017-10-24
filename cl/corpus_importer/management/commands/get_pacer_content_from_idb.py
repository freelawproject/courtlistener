import argparse
import os
import re

from django.conf import settings
from django.db.models import Q
from juriscraper.pacer.http import PacerSession

from cl.corpus_importer.tasks import get_pacer_case_id_for_idb_row, \
    get_docket_by_pacer_case_id, get_pacer_doc_by_rd_and_description
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Docket, RECAPDocument
from cl.recap.constants import FAIR_LABOR_STANDARDS_ACT_CR,\
    FAIR_LABOR_STANDARDS_ACT_CV
from cl.recap.models import FjcIntegratedDatabase

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

KOMPLY_TAG = 'QAV5K6HU93A67WS6'


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
            logger.info("Sent %s tasks to celery so far." % i)
        get_pacer_case_id_for_idb_row.apply_async(args=(row_pk, pacer_session),
                                                  queue=q)


def get_pacer_dockets(options, row_pks, tag=None):
    """Get the pacer dockets identified by the FJC IDB rows"""
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    for i, row_pk in enumerate(row_pks):
        throttle.maybe_wait()
        if i % 1000 == 0:
            pacer_session = PacerSession(username=PACER_USERNAME,
                                         password=PACER_PASSWORD)
            pacer_session.login()
            logger.info("Sent %s tasks to celery so far." % i)
        row = FjcIntegratedDatabase.objects.get(pk=row_pk)
        get_docket_by_pacer_case_id.apply_async(
            args=(
                row.pacer_case_id,
                row.district_id,
                pacer_session,
            ),
            kwargs={
                'tag': tag,
                'show_parties_and_counsel': True,
                'show_terminated_parties': True,
                'show_list_of_member_cases': True,
            },
            queue=q,
        )


def get_cover_sheets_for_docket(options, docket_pks, tag=None):
    """Get civil cover sheets for dockets in our system."""
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    cover_sheet_re = re.compile(r'cover\s*sheet', re.IGNORECASE)
    for i, docket_pk in enumerate(docket_pks):
        throttle.maybe_wait()
        if i % 1000 == 0:
            pacer_session = PacerSession(username=PACER_USERNAME,
                                         password=PACER_PASSWORD)
            pacer_session.login()
            logger.info("Sent %s tasks to celery so far." % i)
        try:
            rd_pk = RECAPDocument.objects.get(
                document_number=1,
                docket_entry__docket_id=docket_pk,
            ).pk
        except (RECAPDocument.MultipleObjectsReturned,
                RECAPDocument.DoesNotExist):
            logger.warn("Unable to get document 1 for docket_pk: %s" %
                        docket_pk)
        else:
            get_pacer_doc_by_rd_and_description.apply_async(
                args=(
                    rd_pk,
                    cover_sheet_re,
                    pacer_session,
                ),
                kwargs={
                    'tag': tag,
                },
                queue=q,
            )


class Command(VerboseCommand):
    help = "Get all the free content from PACER."

    def valid_actions(self, s):
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s" % (
                    ', '.join(self.VALID_ACTIONS.keys())
                )
            )

        return self.VALID_ACTIONS[s]

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            '--action',
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s" % (
                ', '.join(self.VALID_ACTIONS.keys())
            )
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.options = options
        self.options['action'](self)

    def get_komply_ids(self):
        """Get pacer_case_id values for every item relevant to Komply's work."""
        row_pks = FjcIntegratedDatabase.objects.filter(
            Q(nature_of_suit=FAIR_LABOR_STANDARDS_ACT_CV) |
            Q(nature_of_offense=FAIR_LABOR_STANDARDS_ACT_CR),
        ).values_list('pk', flat=True)
        get_pacer_case_ids(self.options, row_pks)

    def get_komply_dockets(self):
        row_pks = FjcIntegratedDatabase.objects.exclude(
            Q(pacer_case_id='') | Q(pacer_case_id='Error')
        ).filter(
            Q(nature_of_suit=FAIR_LABOR_STANDARDS_ACT_CV) |
            Q(nature_of_offense=FAIR_LABOR_STANDARDS_ACT_CR),
            date_filed__gte="2017-01-01",
        ).distinct(
            # Avoid duplicates.
            'pacer_case_id',
            'district_id',
        ).values_list('pk', flat=True)
        get_pacer_dockets(self.options, row_pks, tag=KOMPLY_TAG)

    def get_komply_cover_sheets(self):
        """Once we have all the dockets, our next step is to get the cover
        sheets from each of those cases.
        """
        docket_pks = Docket.objects.filter(
            tags__name=KOMPLY_TAG,
        ).values_list('pk', flat=True)
        get_cover_sheets_for_docket(self.options, docket_pks, tag=KOMPLY_TAG)

    VALID_ACTIONS = {
        'get-komply-pacer-ids': get_komply_ids,
        'get-komply-dockets': get_komply_dockets,
        'get-komply-cover-sheets': get_komply_cover_sheets,
    }
