import calendar
import logging
import os

from datetime import timedelta

import requests
from celery.canvas import chain, chord
from django.conf import settings
from django.core.management import BaseCommand
from django.utils.timezone import now

from cl.corpus_importer.tasks import download_recap_item, parse_recap_docket
from cl.lib.recap_utils import get_docketxml_url, get_docket_filename, \
    get_document_filename, get_pdf_url
from cl.lib.utils import previous_and_next
from cl.scrapers.models import RECAPLog
from cl.scrapers.tasks import extract_recap_pdf, get_recap_page_count
from cl.search.models import RECAPDocument
from cl.search.tasks import add_or_update_recap_document

RECAP_MOD_URL = "http://recapextension.org/recap/get_updated_cases/"
logger = logging.getLogger(__name__)


def update_log_status(log, status):
    log.status = status
    log.save()


def get_new_content_from_recap():
    """Query the RECAP server and get a list of all the new content."""
    # Get the moment that the last process started, and use that as our start
    # time.
    last_success = RECAPLog.objects.filter(
        status=RECAPLog.SCRAPE_SUCCESSFUL,
    ).latest('date_completed')

    # Create a new log entry to track this run.
    new_log = RECAPLog.objects.create(status=RECAPLog.GETTING_CHANGELIST)

    r = requests.post(RECAP_MOD_URL, {
        'tpq': calendar.timegm(last_success.date_started.timetuple()),
    })
    items = []
    keys = ['court_id', 'case_number', 'document_number', 'attachment_number',
            'is_available']
    for row in r.content.split():
        items.append(dict(zip(keys, row.split(','))))
    update_log_status(new_log, RECAPLog.CHANGELIST_RECEIVED)
    return items, new_log


def get_and_merge_items(items, log):
    """Get the items returned from the RECAP server and merge them into CL.

    Items is a list of dicts like so, sorted by court, case number, document
    number and attachment number:

    [{'attachment_number': '0',
      'document_number': '1',
      'case_number': '186759',
      'court_id': 'almb',
      'is_available': '0'},
      ...
    ]

    Note that all values are strings. The idea is to iterate over all of these
    dicts, grabbing the docket, and adding any items that have is_available = 1.
    """
    update_log_status(log, RECAPLog.GETTING_AND_MERGING_ITEMS)
    tasks = []
    for prev, item, nxt in previous_and_next(items):
        if prev is None or item['case_number'] != prev['case_number']:
            # New case. Get the next docket before getting any PDFs.
            url = get_docketxml_url(item['court_id'], item['case_number'])
            logger.info("New docket found at: %s" % url)
            filename = get_docket_filename(item['court_id'], item['case_number'])
            tasks.append(download_recap_item.si(url, filename, clobber=True))

        # Get the document
        filename = get_document_filename(item['court_id'], item['case_number'],
                                         item['document_number'],
                                         item['attachment_number'])
        location = os.path.join(settings.MEDIA_ROOT, 'recap', filename)
        if not os.path.isfile(location) and int(item['is_available']):
            # We don't have it yet, and it's available to get. Get it!
            url = get_pdf_url(item['court_id'], item['case_number'], filename)
            tasks.append(download_recap_item.si(url, filename))

        if nxt is None or item['case_number'] != nxt['case_number']:
            # Last item in the case. Send for processing.
            if len(tasks) > 0:
                logger.info("Sending %s tasks for processing." % len(tasks))
                filename = get_docket_filename(item['court_id'],
                                               item['case_number'])
                chord(tasks)(chain(
                    parse_recap_docket.si(filename, debug=False),
                    extract_recap_pdf.s().set(priority=5),
                    add_or_update_recap_document.s(coalesce_docket=True),
                ))
                tasks = []
    logger.info("Finished queueing new cases.")


def sweep_missing_downloads():
    """
    Get any documents that somehow are missing.
    
    This function attempts to address issue #671 by checking for any missing
    documents, downloading and parsing them. Hopefully this is a temporary 
    hack that we can soon remove when we deprecate the old RECAP server.
    
    :return: None 
    """
    rds = RECAPDocument.objects.filter(
        is_available=True,
        page_count=None,
        date_created__gt=now() - timedelta(hours=2),
    ).order_by()
    for rd in rds:
        # Download the item to the correct location if it doesn't exist
        if not os.path.isfile(rd.filepath_local.path):
            filename = rd.filepath_local.name.rsplit('/', 1)[-1]
            chain(
                download_recap_item.si(rd.filepath_ia, filename),
                get_recap_page_count.si(rd.pk),
                extract_recap_pdf.s(check_if_needed=False).set(priority=5),
                add_or_update_recap_document.s(coalesce_docket=True),
            ).apply_async()


class Command(BaseCommand):
    help = ("Get all the latest content from the RECAP Server. In theory, this "
            "is only temporary until the recap server can be decommissioned.")

    def handle(self, *args, **options):
        items, log = get_new_content_from_recap()
        get_and_merge_items(items, log)
        log.status = RECAPLog.SCRAPE_SUCCESSFUL
        log.date_completed = now()
        log.save()

        sweep_missing_downloads()
