import logging
import os
from datetime import timedelta, datetime

from celery.canvas import chain
from django.core.management import BaseCommand
from juriscraper.lib.string_utils import CaseNameTweaker
from juriscraper.pacer.http import login

from cl.search.models import Court
from cl.corpus_importer.tasks import get_free_document_report, \
    process_free_opinion_result, get_and_process_pdf, upload_free_opinion_to_ia
from cl.lib.celery_utils import blocking_queue
from cl.lib.pacer import map_cl_to_pacer_id, map_pacer_to_cl_id
from cl.lib.tasks import dmap
from cl.scrapers.models import PACERFreeDocumentLog

PACER_USERNAME = os.environ.get('PACER_USERNAME', None)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', None)

logger = logging.getLogger(__name__)

cnt = CaseNameTweaker()


def get_next_date_range(court_id, span=7):
    """Get the next start and end query dates for a court.

    Check the DB for the last date for a court that was completed. Return the
    day after that date + span days into the future as the range to query for
    the requested court.

    :param court_id: A PACER Court ID
    :param span: The number of days to go forward from the last completed date
    """
    court_id = map_pacer_to_cl_id(court_id)
    try:
        last_complete_date = PACERFreeDocumentLog.objects.filter(
            status=PACERFreeDocumentLog.SCRAPE_SUCCESSFUL,
            court_id=court_id,
        ).latest('date_queried').date_queried
    except PACERFreeDocumentLog.DoesNotExist:
        print "FAILED ON: %s" % court_id
        raise
    next_start_date = last_complete_date + timedelta(days=1)
    next_end_date = last_complete_date + timedelta(days=span)
    return next_start_date, next_end_date


def mark_court_done_on_date(court_id, d):
    court_id = map_pacer_to_cl_id(court_id)
    doc_log = PACERFreeDocumentLog.objects.filter(
        status=PACERFreeDocumentLog.SCRAPE_SUCCESSFUL,
        court_id=court_id,
    ).latest('date_queried')
    doc_log.date_queried = d
    doc_log.save()


def go():
    pacer_court_ids = [
        map_cl_to_pacer_id(v) for v in Court.objects.filter(
            jurisdiction__in=['FD', 'FB'],
            in_use=True,
            end_date=None,
        ).exclude(
            pk__in=['casb', 'ganb', 'gub', 'innb', 'mieb', 'miwb', 'nmib',
                    'nvb', 'ohsb', 'prb', 'tnwb', 'vib']
        ).values_list(
            'pk', flat=True
        )
    ]
    pacer_session = login('cand', PACER_USERNAME, PACER_PASSWORD)

    # Iterate over every court, X days at a time. As courts are completed,
    # remove them from the list of courts to process until none are left
    tomorrow = datetime.today() + timedelta(days=1)
    while len(pacer_court_ids) > 0:
        temp_list = list(pacer_court_ids)  # Make a copy of the list.
        for pacer_court_id in temp_list:
            next_start_date, next_end_date = get_next_date_range(pacer_court_id)

            if next_start_date >= tomorrow.date():
                logger.info("Finished '%s'. Marking it complete." % pacer_court_id)
                pacer_court_ids.remove(pacer_court_id)
                continue

            # TODO: Figure out an elegant way to keep the status field in the
            # DB updated during the process below.
            try:
                court = Court.objects.get(pk=map_pacer_to_cl_id(pacer_court_id))
            except Court.DoesNotExist:
                logger.error("Could not find court with pk: %s" % pacer_court_id)
                continue

            chain(
                get_free_document_report.s(pacer_court_id, next_start_date,
                                           next_end_date, pacer_session),
                dmap.s(
                    process_free_opinion_result.s(court, cnt) |
                    get_and_process_pdf.s(pacer_court_id, pacer_session) |
                    upload_free_opinion_to_ia.s()
                ),
            )()
            mark_court_done_on_date(pacer_court_id, next_end_date)


class Command(BaseCommand):
    help = "Get all the free content from PACER."

    def handle(self, *args, **options):
        go()
