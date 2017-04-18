import argparse
import logging
import os
from datetime import timedelta

from celery.canvas import chain
from django.conf import settings
from django.core.management import BaseCommand
from django.utils.timezone import now
from juriscraper.lib.string_utils import CaseNameTweaker
from juriscraper.pacer.http import login

from cl.search.models import Court
from cl.corpus_importer.tasks import (
    mark_court_done_on_date,
    get_and_save_free_document_report,
    process_free_opinion_result, get_and_process_pdf, delete_pacer_row)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.db_tools import queryset_generator
from cl.lib.pacer import map_cl_to_pacer_id, map_pacer_to_cl_id
from cl.scrapers.models import PACERFreeDocumentLog, PACERFreeDocumentRow

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

logger = logging.getLogger(__name__)


def get_next_date_range(court_id, span=7):
    """Get the next start and end query dates for a court.

    Check the DB for the last date for a court that was completed. Return the
    day after that date + span days into the future as the range to query for
    the requested court.

    If the court is still in progress, return (None, None).

    :param court_id: A PACER Court ID
    :param span: The number of days to go forward from the last completed date
    """
    court_id = map_pacer_to_cl_id(court_id)
    try:
        last_completion_log = PACERFreeDocumentLog.objects.filter(
            court_id=court_id,
        ).latest('date_queried')
    except PACERFreeDocumentLog.DoesNotExist:
        print "FAILED ON: %s" % court_id
        raise

    if last_completion_log.status == PACERFreeDocumentLog.SCRAPE_IN_PROGRESS:
        return None, None

    last_complete_date = last_completion_log.date_queried
    next_start_date = last_complete_date + timedelta(days=1)
    next_end_date = last_complete_date + timedelta(days=span)
    return next_start_date, next_end_date


def mark_court_in_progress(court_id, d):
    PACERFreeDocumentLog.objects.create(
        status=PACERFreeDocumentLog.SCRAPE_IN_PROGRESS,
        date_queried=d,
        court_id=map_pacer_to_cl_id(court_id),
    )


def get_and_save_free_document_reports(options):
    pacer_court_ids = {
        map_cl_to_pacer_id(v): {'until': now(), 'count': 1} for v in
            Court.objects.filter(
                jurisdiction__in=['FD', 'FB'],
                in_use=True,
                end_date=None,
            ).exclude(
                pk__in=['casb', 'ganb', 'gub', 'innb', 'mieb', 'miwb', 'nmib',
                        'nvb', 'ohsb', 'prb', 'tnwb', 'vib']
            ).values_list(
                'pk', flat=True
            )
    }
    pacer_session = login('cand', PACER_USERNAME, PACER_PASSWORD)

    # Iterate over every court, X days at a time. As courts are completed,
    # remove them from the list of courts to process until none are left
    tomorrow = now() + timedelta(days=1)
    while len(pacer_court_ids) > 0:
        court_ids_copy = pacer_court_ids.copy()  # Make a copy of the list.
        for pacer_court_id, delay in court_ids_copy.items():
            if now() < delay['until']:
                # Do other courts until the delay is up. Do not print/log
                # anything since at the end there will only be one court left.
                continue

            next_start_date, next_end_date = get_next_date_range(pacer_court_id)
            if next_start_date is None:
                next_delay = min(delay['count'] * 5, 30)  # backoff w/cap
                logger.info("Court %s still in progress. Delaying at least "
                            "%ss." % (pacer_court_id, next_delay))
                pacer_court_ids[pacer_court_id]['until'] = now() + timedelta(
                    seconds=next_delay)
                pacer_court_ids[pacer_court_id]['count'] += 1
                continue
            elif next_start_date >= tomorrow.date():
                logger.info("Finished '%s'. Marking it complete." %
                            pacer_court_id)
                pacer_court_ids.pop(pacer_court_id, None)
                continue

            try:
                court = Court.objects.get(pk=map_pacer_to_cl_id(pacer_court_id))
            except Court.DoesNotExist:
                logger.error("Could not find court with pk: %s" % pacer_court_id)
                continue

            mark_court_in_progress(pacer_court_id, next_end_date)
            pacer_court_ids[pacer_court_id]['count'] = 1  # Reset
            chain(
                get_and_save_free_document_report.si(
                    pacer_court_id,
                    next_start_date,
                    next_end_date,
                    pacer_session
                ),
                mark_court_done_on_date.si(pacer_court_id, next_end_date),
            )()


def get_pdfs(options):
    """Get PDFs for the results of the Free Document Report queries.

    At this stage, we have rows in the PACERFreeDocumentRow table, each of 
    which represents a PDF we need to download and merge into our normal 
    tables: Docket, DocketEntry, and RECAPDocument.

    In this function, we iterate over the entire table of results, merge it 
    into our normal tables, and then download and extract the PDF.

    :return: None
    """
    q = options['queue']
    cnt = CaseNameTweaker()
    pacer_session = login('cand', PACER_USERNAME, PACER_PASSWORD)
    rows = PACERFreeDocumentRow.objects.only('pk')
    throttle = CeleryThrottle(queue_name=q)
    for row in queryset_generator(rows):
        throttle.maybe_wait()
        chain(
            process_free_opinion_result.si(row.pk, cnt).set(queue=q),
            get_and_process_pdf.s(pacer_session).set(queue=q),
            delete_pacer_row.si(row.pk).set(queue=q),
        ).apply_async()


class Command(BaseCommand):
    help = "Get all the free content from PACER. There are three modes."

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
            '--action',
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s" % (
                ', '.join(self.VALID_ACTIONS.keys())
            )
        )
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )

    def handle(self, *args, **options):
        options['action'](options)

    VALID_ACTIONS = {
        'get-report-results': get_and_save_free_document_reports,
        'get-pdfs': get_pdfs,
    }

