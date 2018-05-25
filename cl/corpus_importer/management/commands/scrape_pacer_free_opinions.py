import argparse
import os
from datetime import timedelta

from celery.canvas import chain
from django.conf import settings
from django.db.models import Q
from django.utils.timezone import now
from juriscraper.lib.string_utils import CaseNameTweaker
from juriscraper.pacer.http import PacerSession

from cl.corpus_importer.tasks import (
    mark_court_done_on_date,
    get_and_save_free_document_report,
    process_free_opinion_result, get_and_process_pdf, delete_pacer_row,
    upload_pdf_to_ia,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.db_tools import queryset_generator
from cl.lib.pacer import map_cl_to_pacer_id, map_pacer_to_cl_id
from cl.scrapers.models import PACERFreeDocumentLog, PACERFreeDocumentRow
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import Court, RECAPDocument
from cl.search.tasks import add_or_update_recap_document

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)


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
        ).exclude(
            status=PACERFreeDocumentLog.SCRAPE_FAILED,
        ).latest('date_queried')
    except PACERFreeDocumentLog.DoesNotExist:
        logger.warn("FAILED ON: %s" % court_id)
        raise

    if last_completion_log.status == PACERFreeDocumentLog.SCRAPE_IN_PROGRESS:
        return None, None

    # Ensure that we go back five days from the last time we had success if that
    # success was in the last few days.
    last_complete_date = min(now().date() - timedelta(days=5),
                             last_completion_log.date_queried)
    next_end_date = min(now().date(),
                        last_complete_date + timedelta(days=span))
    return last_complete_date, next_end_date


def mark_court_in_progress(court_id, d):
    PACERFreeDocumentLog.objects.create(
        status=PACERFreeDocumentLog.SCRAPE_IN_PROGRESS,
        date_queried=d,
        court_id=map_pacer_to_cl_id(court_id),
    )


def get_and_save_free_document_reports(options):
    """Query the Free Doc Reports on PACER and get a list of all the free
    documents. Do not download those items, as that step is done later.
    """
    # Kill any *old* logs that report they're in progress. (They've failed.)
    twelve_hrs_ago = now() - timedelta(hours=12)
    PACERFreeDocumentLog.objects.filter(
        date_started__lt=twelve_hrs_ago,
        status=PACERFreeDocumentLog.SCRAPE_IN_PROGRESS,
    ).update(
        status=PACERFreeDocumentLog.SCRAPE_FAILED,
    )

    cl_court_ids = Court.objects.filter(
        jurisdiction__in=[Court.FEDERAL_DISTRICT,
                          Court.FEDERAL_BANKRUPTCY],
        in_use=True,
        end_date=None,
    ).exclude(
        pk__in=['casb', 'ganb', 'gub', 'innb', 'mieb', 'miwb', 'nmib', 'nvb',
                'ohsb', 'prb', 'tnwb', 'vib'],
    ).values_list(
        'pk',
        flat=True,
    )
    pacer_court_ids = {
        map_cl_to_pacer_id(v): {'until': now(), 'count': 1, 'result': None} for
        v in cl_court_ids
    }
    pacer_session = PacerSession(username=PACER_USERNAME,
                                 password=PACER_PASSWORD)
    pacer_session.login()

    # Iterate over every court, X days at a time. As courts are completed,
    # remove them from the list of courts to process until none are left
    today = now()
    max_delay_count = 20
    while len(pacer_court_ids) > 0:
        court_ids_copy = pacer_court_ids.copy()  # Make a copy of the list.
        for pacer_court_id, delay in court_ids_copy.items():
            if now() < delay['until']:
                # Do other courts until the delay is up. Do not print/log
                # anything since at the end there will only be one court left.
                continue

            next_start_date, next_end_date = get_next_date_range(pacer_court_id)
            if delay['result'] is not None:
                if delay['result'].ready():
                    result = delay['result'].get()
                    if result == PACERFreeDocumentLog.SCRAPE_SUCCESSFUL:
                        if next_end_date >= today.date():
                            logger.info("Finished '%s'. Marking it complete." %
                                        pacer_court_id)
                            pacer_court_ids.pop(pacer_court_id, None)
                            continue

                    elif result == PACERFreeDocumentLog.SCRAPE_FAILED:
                        logger.error("Encountered critical error on %s "
                                     "(network error?). Marking as failed and "
                                     "pressing on." % pacer_court_id)
                        pacer_court_ids.pop(pacer_court_id, None)
                        continue
                else:
                    if delay['count'] > max_delay_count:
                        logger.error("Something went wrong and we weren't "
                                     "able to finish %s. We ran out of time." %
                                     pacer_court_id)
                        pacer_court_ids.pop(pacer_court_id, None)
                        continue
                    next_delay = min(delay['count'] * 5, 30)  # backoff w/cap
                    logger.info("Court %s still in progress. Delaying at least "
                                "%ss." % (pacer_court_id, next_delay))
                    pacer_court_ids[pacer_court_id]['until'] = now() + timedelta(
                        seconds=next_delay)
                    pacer_court_ids[pacer_court_id]['count'] += 1
                    continue

            mark_court_in_progress(pacer_court_id, next_end_date)
            pacer_court_ids[pacer_court_id]['count'] = 1  # Reset
            delay['result'] = chain(
                get_and_save_free_document_report.si(
                    pacer_court_id,
                    next_start_date,
                    next_end_date,
                    pacer_session
                ),
                mark_court_done_on_date.s(pacer_court_id, next_end_date),
            ).apply_async()


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
    index = options['index']
    cnt = CaseNameTweaker()
    rows = PACERFreeDocumentRow.objects.filter(error_msg="").only('pk')
    count = rows.count()
    task_name = "downloading"
    if index:
        task_name += " and indexing"
    logger.info("%s %s items from PACER." % (task_name, count))
    throttle = CeleryThrottle(queue_name=q)
    completed = 0
    for row in queryset_generator(rows):
        throttle.maybe_wait()
        if completed % 30000 == 0:
            pacer_session = PacerSession(username=PACER_USERNAME,
                                         password=PACER_PASSWORD)
            pacer_session.login()
        chain(
            process_free_opinion_result.si(row.pk, cnt).set(queue=q),
            get_and_process_pdf.s(pacer_session, row.pk, index=index).set(queue=q),
            delete_pacer_row.si(row.pk).set(queue=q),
        ).apply_async()
        completed += 1
        if completed % 1000 == 0:
            logger.info("Sent %s/%s tasks to celery for %s so "
                        "far." % (completed, count, task_name))


def do_ocr(options):
    """Do the OCR for any items that need it, then save to the solr index."""
    q = options['queue']
    rds = RECAPDocument.objects.filter(
        ocr_status=RECAPDocument.OCR_NEEDED,
    ).values_list('pk', flat=True).order_by()
    count = rds.count()
    throttle = CeleryThrottle(queue_name=q)
    for i, pk in enumerate(rds):
        throttle.maybe_wait()
        if options['index']:
            extract_recap_pdf.si(pk, skip_ocr=False).set(queue=q).apply_async()
        else:
            chain(
                extract_recap_pdf.si(pk, skip_ocr=False).set(queue=q),
                add_or_update_recap_document.s(coalesce_docket=True).set(queue=q),
            ).apply_async()
        if i % 1000 == 0:
            logger.info("Sent %s/%s tasks to celery so far." % (i + 1, count))


def upload_non_free_pdfs_to_internet_archive(options):
    upload_to_internet_archive(options, do_non_free=True)


def upload_to_internet_archive(options, do_non_free=False):
    """Upload items to the Internet Archive."""
    q = options['queue']
    rds = RECAPDocument.objects.filter(
        Q(ia_upload_failure_count__lt=3) | Q(ia_upload_failure_count=None),
        is_available=True,
        filepath_ia='',
    ).exclude(
        filepath_local='',
    ).values_list(
        'pk',
        flat=True,
    ).order_by()
    if do_non_free:
        rds = rds.filter(Q(is_free_on_pacer=False) | Q(is_free_on_pacer=None))
    else:
        rds = rds.filter(is_free_on_pacer=True)

    count = rds.count()
    logger.info("Sending %s items to Internet Archive." % count)
    throttle = CeleryThrottle(queue_name=q)
    for i, rd in enumerate(rds):
        throttle.maybe_wait()
        if i > 0 and i % 1000 == 0:
            logger.info("Sent %s/%s tasks to celery so far." % (i, count))
        upload_pdf_to_ia.si(rd).set(queue=q).apply_async()


def do_everything(options):
    logger.info("Running and compiling free document reports.")
    get_and_save_free_document_reports(options)
    logger.info("Getting PDFs from free document reports")
    get_pdfs(options)
    logger.info("Doing OCR and saving items to Solr.")
    do_ocr(options)
    logger.info("Uploading free opinions to Internet Archive.")
    upload_to_internet_archive(options)
    logger.info("Uploading non-free PDFs to Internet Archive.")
    upload_non_free_pdfs_to_internet_archive(options)


class Command(VerboseCommand):
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
        parser.add_argument(
            '--index',
            action='store_true',
            default=False,
            help='Do we index as we go, or leave that to be done later?'
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options['action'](options)

    VALID_ACTIONS = {
        'get-report-results': get_and_save_free_document_reports,
        'get-pdfs': get_pdfs,
        'do-ocr': do_ocr,
        'do-everything': do_everything,
        'upload-to-ia': upload_to_internet_archive,
        'upload-non-free-pdfs-to-ia': upload_non_free_pdfs_to_internet_archive,
    }

