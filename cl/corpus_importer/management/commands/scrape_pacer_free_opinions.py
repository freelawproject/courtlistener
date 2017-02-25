import os
from datetime import timedelta, datetime

from celery.canvas import chain
from django.core.management import BaseCommand
from juriscraper.pacer.http import login

from cl.search.models import Court
from cl.lib.pacer import cl_to_pacer_ids, pacer_to_cl_ids
from cl.scrapers.models import PACERFreeDocumentLog

PACER_USERNAME = os.environ.get('PACER_USERNAME', None)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', None)


def get_next_date(court_id):
    """Get the next incomplete date for a court.

    Check the DB for the next date for a court that has not been completed.

    court_id: A PACER Court ID (not a CL court ID)
    """
    court_id = pacer_to_cl_ids[court_id]
    last_complete_date = PACERFreeDocumentLog.objects.filter(
        status=PACERFreeDocumentLog.SCRAPE_SUCCESSFUL,
        court_id=court_id,
    ).latest('date_queried').date_queried
    next_date = last_complete_date + timedelta(days=1)
    return next_date


def go():
    court_ids = [
        cl_to_pacer_ids[v] for v in Court.objects.filter(
            jurisdiction__in=['FD', 'FB']
        ).values_list('pk', flat=True)
    ]
    session = login('cand', PACER_USERNAME, PACER_PASSWORD)

    # There's maybe a better way to do this, but this iterates over every court,
    # one day at a time. As courts are completed, they're removed from the list
    # of courts to process until none are left and we exit the outer while loop.
    tomorrow = datetime.today() + timedelta(days=1)
    while len(court_ids) > 0:
        temp_list = list(court_ids)
        for court_id in temp_list:
            next_date = get_next_date(court_id)

            if next_date == tomorrow:
                # We finished the court! Remove it from original list and continue
                court_ids.remove(court_id)
                continue

            # Make a chain to run the report, get the PDFs and save it all to
            # CL and to Internet Archive.
            # TODO: Figure out how to keep the status field in the DB updated
            #       during the process below.
            chain(
                get_free_document_report_response(court_id, next_date)
                download_pdfs(),
                save_to_db_question_mark(),
                upload_to_ia(),
            ).delay()


class Command(BaseCommand):
    help = "Get all the free content from PACER."

    def handle(self, *args, **options):
        go()
