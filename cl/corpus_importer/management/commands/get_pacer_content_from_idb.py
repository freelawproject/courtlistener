import argparse
import os
import random
import re

from celery.canvas import chain
from django.conf import settings
from django.db.models import Q
from juriscraper.pacer.http import PacerSession

from cl.corpus_importer.tasks import get_pacer_case_id_for_idb_row, \
    get_docket_by_pacer_case_id, get_pacer_doc_by_rd_and_description
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Docket, RECAPDocument
from cl.search.tasks import add_or_update_recap_docket
from cl.recap.constants import FAIR_LABOR_STANDARDS_ACT_CR, \
    FAIR_LABOR_STANDARDS_ACT_CV, BANKRUPTCY_APPEALS, BANKRUPTCY_WITHDRAWAL, \
    PRISONER_PETITIONS_VACATE_SENTENCE, PRISONER_PETITIONS_HABEAS_CORPUS, \
    PRISONER_PETITIONS_MANDAMUS_AND_OTHER, PRISONER_CIVIL_RIGHTS, \
    PRISONER_PRISON_CONDITION, IMMIGRATION_ACTIONS_OTHER, \
    FORFEITURE_AND_PENALTY_SUITS_OTHER, SOCIAL_SECURITY, TAX_SUITS
from cl.recap.models import FjcIntegratedDatabase

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

KOMPLY_TAG = 'QAV5K6HU93A67WS6'
GAVELYTICS_TAG = 'FFQBCCFSBJSULNBS'


def get_pacer_case_ids(options, row_pks):
    """Get the PACER case IDs for the given items."""
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    for i, row_pk in enumerate(row_pks):
        if i >= options['count'] > 0:
            break
        throttle.maybe_wait()
        if i % 10000 == 0:
            pacer_session = PacerSession(username=PACER_USERNAME,
                                         password=PACER_PASSWORD)
            pacer_session.login()
            logger.info("Sent %s tasks to celery so far." % i)
        get_pacer_case_id_for_idb_row.apply_async(
            args=(row_pk, pacer_session),
            queue=q,
        )


def get_pacer_dockets(options, row_pks, tag=None):
    """Get the pacer dockets identified by the FJC IDB rows"""
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    for i, row_pk in enumerate(row_pks):
        if i >= options['count'] > 0:
            break
        throttle.maybe_wait()
        if i % 1000 == 0:
            pacer_session = PacerSession(username=PACER_USERNAME,
                                         password=PACER_PASSWORD)
            pacer_session.login()
            logger.info("Sent %s tasks to celery so far." % i)
        row = FjcIntegratedDatabase.objects.get(pk=row_pk)
        chain(
            get_docket_by_pacer_case_id.s(
                row.pacer_case_id,
                row.district_id,
                pacer_session,
                **{'tag': tag, 'show_parties_and_counsel': True,
                   'show_terminated_parties': True,
                   'show_list_of_member_cases': True}
            ).set(queue=q),
            add_or_update_recap_docket.s().set(queue=q),
        ).apply_async()


def get_doc_by_re_and_de_nums_for_dockets(options, docket_pks, regex, de_nums,
                                          fallback=False, tag=None):
    """Get civil cover sheets for dockets in our system.

    :param options: The options sent on the command line as a dict.
    :param docket_pks: A list of docket pks to iterate over.
    :param regex: A regex to match on the document description on the attachment
    page. For example, to get initial complaints, set this to
    r'initial\s*complaints'.
    :param de_nums: The docket entry numbers to use when looking for items, as a
    list.
    :param fallback: After loading the attachment page, if we don't find
    something that matches `regex`, should we just grab the main document?
    :param tag: A tag to add to any modified content.
    """
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    for i, docket_pk in enumerate(docket_pks):
        if i >= options['count'] > 0:
            break
        throttle.maybe_wait()
        if i % 1000 == 0:
            pacer_session = PacerSession(username=PACER_USERNAME,
                                         password=PACER_PASSWORD)
            pacer_session.login()
            logger.info("Sent %s tasks to celery so far." % i)
        try:
            rds = RECAPDocument.objects.filter(
                document_number__in=de_nums,
                document_type=RECAPDocument.PACER_DOCUMENT,
                docket_entry__docket_id=docket_pk,
            )
        except (RECAPDocument.MultipleObjectsReturned,
                RECAPDocument.DoesNotExist):
            logger.warn("Unable to get document 1 for docket_pk: %s" %
                        docket_pk)
        else:
            for rd in rds:
                get_pacer_doc_by_rd_and_description.apply_async(
                    args=(
                        rd.pk,
                        regex,
                        pacer_session,
                    ),
                    kwargs={
                        'fallback_to_main_doc': fallback,
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
        parser.add_argument(
            '--count',
            type=int,
            default=0,
            help="The number of items to do. Default is to do all of them.",
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
            pacer_case_id='',
        ).values_list('pk', flat=True)
        get_pacer_case_ids(self.options, row_pks)

    def get_gavelytics_ids(self):
        """Get the pacer_case_id values for every item relevant to Gavelytics"""
        row_pks = FjcIntegratedDatabase.objects.exclude(
            nature_of_suit__in=[
                BANKRUPTCY_APPEALS,
                BANKRUPTCY_WITHDRAWAL,
                PRISONER_PETITIONS_VACATE_SENTENCE,
                PRISONER_PETITIONS_HABEAS_CORPUS,
                PRISONER_PETITIONS_MANDAMUS_AND_OTHER,
                PRISONER_CIVIL_RIGHTS,
                PRISONER_PRISON_CONDITION,
                IMMIGRATION_ACTIONS_OTHER,
                FORFEITURE_AND_PENALTY_SUITS_OTHER,
                SOCIAL_SECURITY,
                TAX_SUITS,
            ],
        ).filter(
            district_id__in=['cand', 'casd', 'cacd', 'caed'],
            date_filed__gte='2012-01-01',
            pacer_case_id='',
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

    def get_gavelytics_docket_sample(self):
        self.get_gavelytics_dockets(sample=True)

    def get_gavelytics_dockets(self, sample=False):
        row_pks = FjcIntegratedDatabase.objects.exclude(
            Q(pacer_case_id='') | Q(pacer_case_id='Error'),
            nature_of_suit__in=[
                BANKRUPTCY_APPEALS,
                BANKRUPTCY_WITHDRAWAL,
                PRISONER_PETITIONS_VACATE_SENTENCE,
                PRISONER_PETITIONS_HABEAS_CORPUS,
                PRISONER_PETITIONS_MANDAMUS_AND_OTHER,
                PRISONER_CIVIL_RIGHTS,
                PRISONER_PRISON_CONDITION,
                IMMIGRATION_ACTIONS_OTHER,
                FORFEITURE_AND_PENALTY_SUITS_OTHER,
                SOCIAL_SECURITY,
                TAX_SUITS,
            ],
        ).filter(
            district_id__in=['cand', 'casd', 'cacd', 'caed'],
            date_filed__gte='2012-01-01',
        ).distinct(
            # Avoid duplicates.
            'pacer_case_id',
            'district_id',
        ).values_list('pk', flat=True)
        if sample is True:
            random.shuffle(list(row_pks))
            row_pks = row_pks[0:100]
        get_pacer_dockets(self.options, row_pks, tag=GAVELYTICS_TAG)

    def get_komply_cover_sheets(self):
        """Once we have all the dockets, our next step is to get the cover
        sheets from each of those cases.
        """
        docket_pks = Docket.objects.filter(
            tags__name=KOMPLY_TAG,
        ).values_list('pk', flat=True)
        cover_sheet_re = re.compile(r'cover\s*sheet', re.IGNORECASE)
        get_doc_by_re_and_de_nums_for_dockets(
            self.options, docket_pks, cover_sheet_re, [1, 2], tag=KOMPLY_TAG)

    def get_komply_initial_complaints(self):
        docket_pks = Docket.objects.filter(
            tags__name=KOMPLY_TAG,
        ).values_list('pk', flat=True)
        initial_complaint_re = re.compile(r'initial\s+complaint', re.IGNORECASE)
        get_doc_by_re_and_de_nums_for_dockets(
            self.options,
            docket_pks,
            initial_complaint_re,
            [1],  # Only want to look for initial complaints on DE #1.
            fallback=True,  # If we don't find it, grab the main doc.
            tag=KOMPLY_TAG,
        )

    VALID_ACTIONS = {
        # Komply
        'get-komply-pacer-ids': get_komply_ids,
        'get-komply-dockets': get_komply_dockets,
        'get-komply-cover-sheets': get_komply_cover_sheets,
        'get-komply-initial-complaints': get_komply_initial_complaints,
        # Gavelytics
        'get-gavelytics-pacer-ids': get_gavelytics_ids,
        'get-gavelytics-docket-sample': get_gavelytics_docket_sample,
        'get-gavelytics-dockets': get_gavelytics_dockets,
    }
