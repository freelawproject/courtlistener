import argparse
import os
from datetime import timedelta

from celery.canvas import chain
from celery.exceptions import TimeoutError
from django.conf import settings
from django.utils.timezone import now
from juriscraper.lib.string_utils import CaseNameTweaker
from juriscraper.pacer.http import PacerSession

from cl.corpus_importer.tasks import (
    mark_court_done_on_date,
    get_and_save_free_document_report,
    process_free_opinion_result, get_and_process_pdf, delete_pacer_row,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.db_tools import queryset_generator
from cl.lib.pacer import map_cl_to_pacer_id, map_pacer_to_cl_id
from cl.scrapers.models import PACERFreeDocumentLog, PACERFreeDocumentRow
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import Court, RECAPDocument
from cl.search.tasks import add_items_to_solr, add_docket_to_solr_by_rds

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

    # Ensure that we go back five days from the last time we had success if
    # that success was in the last few days.
    last_complete_date = min(now().date() - timedelta(days=5),
                             last_completion_log.date_queried)
    next_end_date = min(now().date(),
                        last_complete_date + timedelta(days=span))
    return last_complete_date, next_end_date


def mark_court_in_progress(court_id, d):
    log = PACERFreeDocumentLog.objects.create(
        status=PACERFreeDocumentLog.SCRAPE_IN_PROGRESS,
        date_queried=d,
        court_id=map_pacer_to_cl_id(court_id),
    )
    return log


def get_and_save_free_document_reports(options):
    """Query the Free Doc Reports on PACER and get a list of all the free
    documents. Do not download those items, as that step is done later. For now
    just get the list.

    Note that this uses synchronous celery chains. A previous version was more
    complex and did not use synchronous chains. Unfortunately in Celery 4.2.0,
    or more accurately in redis-py 3.x.x, doing it that way failed nearly every
    time.

    This is a simpler version, though a slower one, but it should get the job
    done.
    """
    # Kill any *old* logs that report they're in progress. (They've failed.)
    three_hrs_ago = now() - timedelta(hours=3)
    PACERFreeDocumentLog.objects.filter(
        date_started__lt=three_hrs_ago,
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
        pk__in=['casb', 'gub', 'innb', 'miwb', 'ohsb', 'prb'],
    ).values_list(
        'pk',
        flat=True,
    )
    pacer_court_ids = [map_cl_to_pacer_id(v) for v in cl_court_ids]

    pacer_session = PacerSession(username=PACER_USERNAME,
                                 password=PACER_PASSWORD)
    pacer_session.login()

    today = now()
    max_delay = 60
    for pacer_court_id in pacer_court_ids:
        while True:
            next_start_d, next_end_d = get_next_date_range(pacer_court_id)
            logger.info("Attempting to get latest document references at for "
                        "%s between %s and %s", pacer_court_id, next_start_d,
                        next_end_d)
            pacer_log = mark_court_in_progress(pacer_court_id, next_end_d)
            result = chain(
                get_and_save_free_document_report.si(
                    pacer_court_id,
                    next_start_d,
                    next_end_d,
                    pacer_session.cookies,
                ),
                mark_court_done_on_date.s(pacer_court_id, next_end_d),
            )()
            try:
                result.get(timeout=max_delay)
            except TimeoutError:
                logger.info("Court %s failed to complete in %ss. Marking as "
                            "failed and pressing on. Tried to do: %s to %s",
                            pacer_court_id, max_delay, next_start_d,
                            next_end_d)
                pacer_log.status = PACERFreeDocumentLog.SCRAPE_FAILED
                pacer_log.save()
                break

            if result == PACERFreeDocumentLog.SCRAPE_SUCCESSFUL:
                if next_end_d >= today.date():
                    logger.info("Got all document references for '%s'.",
                                pacer_court_id)
                    # Break from while loop, onwards to next court
                    break
                else:
                    # More dates to do; let it continue
                    continue

            elif result == PACERFreeDocumentLog.SCRAPE_FAILED:
                logger.error("Encountered critical error on %s "
                             "(network error?). Marking as failed and "
                             "pressing on." % pacer_court_id)
                # Break from while loop, onwards to next court
                break


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
        c = chain(
            process_free_opinion_result.si(row.pk, cnt).set(queue=q),
            get_and_process_pdf.s(pacer_session.cookies, row.pk).set(queue=q),
            delete_pacer_row.s(row.pk).set(queue=q),
        )
        if index:
            c |= add_items_to_solr.s('search.RECAPDocument').set(queue=q)
        c.apply_async()
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
                add_docket_to_solr_by_rds.s().set(queue=q),
            ).apply_async()
        if i % 1000 == 0:
            logger.info("Sent %s/%s tasks to celery so far." % (i + 1, count))


def do_everything(options):
    logger.info("Running and compiling free document reports.")
    get_and_save_free_document_reports(options)
    logger.info("Getting PDFs from free document reports")
    get_pdfs(options)
    logger.info("Doing OCR and saving items to Solr.")
    do_ocr(options)


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
        'do-everything': do_everything,
        'get-report-results': get_and_save_free_document_reports,
        'get-pdfs': get_pdfs,
        'do-ocr': do_ocr,
    }
