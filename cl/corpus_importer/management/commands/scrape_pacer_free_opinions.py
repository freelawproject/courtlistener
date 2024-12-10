import argparse
import datetime
import inspect
import math
import time
from typing import Callable, Dict, List, Optional, cast

from celery.canvas import chain
from django.db.models import F, Q, Window
from django.db.models.functions import RowNumber
from django.utils.timezone import now
from juriscraper.lib.date_utils import make_date_range_tuples
from juriscraper.lib.exceptions import PacerLoginException
from juriscraper.lib.string_utils import CaseNameTweaker
from requests import RequestException
from urllib3.exceptions import ReadTimeoutError

from cl.corpus_importer.tasks import (
    delete_pacer_row,
    get_and_process_free_pdf,
    get_and_save_free_document_report,
    mark_court_done_on_date,
    process_free_opinion_result,
    recap_document_into_opinions,
)
from cl.corpus_importer.utils import CycleChecker
from cl.lib.argparse_types import valid_date
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer import map_cl_to_pacer_id, map_pacer_to_cl_id
from cl.lib.types import OptionsType
from cl.scrapers.models import PACERFreeDocumentLog, PACERFreeDocumentRow
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import Court, RECAPDocument


def get_last_complete_date(
    court_id: str,
) -> Optional[datetime.date]:
    """Get the next start query date for a court.

    Check the DB for the last date for a court that was completed. Return the
    day after that date + span days into the future as the range to query for
    the requested court.

    If the court is still in progress, return (None, None).

    :param court_id: A PACER Court ID
    :return: last date queried for the specified court or None if it is in progress
    """
    court_id = map_pacer_to_cl_id(court_id)
    try:
        last_completion_log = (
            PACERFreeDocumentLog.objects.filter(court_id=court_id)
            .exclude(status=PACERFreeDocumentLog.SCRAPE_FAILED)
            .latest("date_queried")
        )
    except PACERFreeDocumentLog.DoesNotExist:
        logger.warning(f"FAILED ON: {court_id}")
        raise

    if last_completion_log.status == PACERFreeDocumentLog.SCRAPE_IN_PROGRESS:
        return None

    # Ensure that we go back five days from the last time we had success if
    # that success was in the last few days.
    last_complete_date = min(
        now().date() - datetime.timedelta(days=5),
        last_completion_log.date_queried,
    )
    return last_complete_date


def mark_court_in_progress(
    court_id: str, d: datetime.date
) -> PACERFreeDocumentLog:
    """Create row with data of queried court

    Stores the pacer's court id, scraping status, and the last date queried.

    :param court_id: Pacer court id
    :param d: Last date queried
    :return: new PACERFreeDocumentLog object
    """
    return PACERFreeDocumentLog.objects.create(
        status=PACERFreeDocumentLog.SCRAPE_IN_PROGRESS,
        date_queried=d,
        court_id=map_pacer_to_cl_id(court_id),
    )


def fetch_doc_report(
    pacer_court_id: str,
    start: datetime.date,
    end: datetime.date,
) -> bool:
    """Get free documents from pacer

    Get free documents from pacer and save each using PACERFreeDocumentRow model

    :param pacer_court_id: Pacer court id to fetch
    :param start: start date to query
    :param end: end date to query
    :return: true if an exception occurred else false
    """
    exception_raised = False
    status = PACERFreeDocumentLog.SCRAPE_FAILED
    rows_to_create = 0

    log = mark_court_in_progress(pacer_court_id, end)

    logger.info(
        "Attempting to get latest document references for "
        "%s between %s and %s",
        pacer_court_id,
        start,
        end,
    )
    try:
        status, rows_to_create = get_and_save_free_document_report(pacer_court_id, start, end, log.pk)  # type: ignore
    except (
        RequestException,
        ReadTimeoutError,
        IndexError,
        TypeError,
        PacerLoginException,
        ValueError,
    ) as exc:
        if isinstance(exc, (RequestException, ReadTimeoutError)):
            reason = "network error."
        elif isinstance(exc, IndexError):
            reason = "PACER 6.3 bug."
        elif isinstance(exc, (TypeError, ValueError)):
            reason = "failing PACER website."
        elif isinstance(exc, PacerLoginException):
            reason = "PACER login issue."
        else:
            reason = "unknown reason."
        logger.error(
            "Failed to get free document references for "
            f"{pacer_court_id} between {start} and "
            f"{end} due to {reason}.",
            exc_info=True,
        )
        exception_raised = True

        mark_court_done_on_date(
            log.pk,
            PACERFreeDocumentLog.SCRAPE_FAILED,
        )

    if not exception_raised:
        logger.info(
            "Got %s document references for " "%s between %s and %s",
            rows_to_create,
            pacer_court_id,
            start,
            end,
        )
        # Scrape successful
        mark_court_done_on_date(log.pk, status)

    return exception_raised


def get_and_save_free_document_reports(
    courts: list[Optional[str]],
    date_start: Optional[datetime.date],
    date_end: Optional[datetime.date],
) -> None:
    """Query the Free Doc Reports on PACER and get a list of all the free
    documents. Do not download those items, as that step is done later. For now
    just get the list.

    Note that this uses synchronous celery chains. A previous version was more
    complex and did not use synchronous chains. Unfortunately in Celery 4.2.0,
    or more accurately in redis-py 3.x.x, doing it that way failed nearly every
    time.

    This is a simpler version, though a slower one, but it should get the job
    done.

    :param courts: optionally a list of courts to scrape
    :param date_start: optionally a start date to query all the specified courts or all
    courts
    :param date_end: optionally an end date to query all the specified courts or all
    courts
    """
    # Kill any *old* logs that report they're in progress. (They've failed.)
    three_hrs_ago = now() - datetime.timedelta(hours=3)
    PACERFreeDocumentLog.objects.filter(
        date_started__lt=three_hrs_ago,
        status=PACERFreeDocumentLog.SCRAPE_IN_PROGRESS,
    ).update(status=PACERFreeDocumentLog.SCRAPE_FAILED)

    excluded_court_ids = ["casb", "gub", "ilnb", "innb", "miwb", "ohsb", "prb"]

    base_filter = Q(in_use=True, end_date=None) & ~Q(pk__in=excluded_court_ids)
    if courts:
        base_filter &= Q(pk__in=courts)

    cl_court_ids = (
        Court.federal_courts.district_or_bankruptcy_pacer_courts()
        .filter(base_filter)
        .values_list("pk", flat=True)
    )

    pacer_court_ids = [map_cl_to_pacer_id(v) for v in cl_court_ids]

    dates = None
    if date_start and date_end:
        # If we pass the dates in the command then we generate the range on those dates
        # The first date queried is 1950-05-12 from ca9, that should be the starting
        # point for the sweep
        dates = make_date_range_tuples(date_start, date_end, gap=7)

    for pacer_court_id in pacer_court_ids:
        court_failed = False
        if not dates:
            # We don't pass the dates in the command, so we generate the range based
            # on each court
            date_end = datetime.date.today()
            date_start = get_last_complete_date(pacer_court_id)
            if not date_start:
                logger.warning(
                    f"Free opinion scraper for {pacer_court_id} still "
                    "in progress."
                )
                continue
            dates = make_date_range_tuples(date_start, date_end, gap=7)

        # Iterate through the gap in dates either short or long
        for _start, _end in dates:
            exc = fetch_doc_report(
                pacer_court_id, _start, _end  # type: ignore
            )
            if exc:
                # Something happened with the queried date range, abort process for
                # that court
                court_failed = True
                break

            # Wait 1s between queries to try to avoid a possible throttling/blocking
            # from the court
            time.sleep(1)

        if court_failed:
            continue


def get_pdfs(
    courts: list[Optional[str]],
    date_start: datetime.date,
    date_end: datetime.date,
    queue: str,
) -> None:
    """Get PDFs for the results of the Free Document Report queries.

    At this stage, we have rows in the PACERFreeDocumentRow table, each of
    which represents a PDF we need to download and merge into our normal
    tables: Docket, DocketEntry, and RECAPDocument.

    In this function, we iterate over the entire table of results, merge it
    into our normal tables, and then download and extract the PDF.

    :param courts: optionally a list of courts to scrape
    :param date_start: optionally a start date to query all the specified courts or all
    courts
    :param date_end: optionally an end date to query all the specified courts or all
    courts
    :param queue: the queue name
    :return: None
    """
    q = cast(str, queue)
    cnt = CaseNameTweaker()
    base_filter = Q(error_msg="")

    if courts:
        # Download PDFs only from specified court ids
        base_filter &= Q(court_id__in=courts)

    if date_start and date_end:
        # Download documents only from the date range passed from the command args (
        # sweep)
        base_filter &= Q(date_filed__gte=date_start, date_filed__lte=date_end)

    # Filter rows based on the base_filter, then annotate each row with a row_number
    # within each partition defined by 'court_id', ordering the rows by 'pk' in
    # ascending order. Finally, order the results by 'row_number' and 'court_id' to
    # download one item for each court until it finishes
    rows = (
        PACERFreeDocumentRow.objects.filter(base_filter)
        .annotate(
            row_number=Window(
                expression=RowNumber(),
                partition_by=[F("court_id")],
                order_by=F("pk").asc(),
            )
        )
        .order_by("row_number", "court_id")
        .only("pk", "court_id")
    )
    count = rows.count()
    task_name = "downloading"
    logger.info(
        f"{task_name} {count} items from PACER from {date_start} to {date_end}."
    )
    throttle = CeleryThrottle(queue_name=q)
    completed = 0
    cycle_checker = CycleChecker()
    for row in rows.iterator():
        # Wait until the queue is short enough
        throttle.maybe_wait()

        if cycle_checker.check_if_cycled(row.court_id):
            # How many courts we cycled in the previous cycle
            cycled_items_count = cycle_checker.count_prev_iteration_courts

            # Update the queue size where the max number is close to the number
            # of courts we did on the previous cycle, that way we can try to avoid
            # having more than one item of each court of in the queue until it shortens
            min_items = math.ceil(cycled_items_count / 2)
            if min_items < 50:
                # we set the limit to 50 to keep this number less than the defaults
                # from the class to avoid having a lot of items
                throttle.update_min_items(min_items)

            logger.info(
                f"Court cycle completed for: {row.court_id}. Current iteration: {cycle_checker.current_iteration}. Sleep 1 second "
                f"before starting the next cycle."
            )
            time.sleep(1)
        logger.info(f"Processing row id: {row.id} from {row.court_id}")
        c = chain(
            process_free_opinion_result.si(
                row.pk,
                row.court_id,
                cnt,
            ).set(queue=q),
            get_and_process_free_pdf.s(row.pk, row.court_id).set(queue=q),
            # `recap_document_into_opinions` uses a different doctor extraction
            # endpoint, so it doesn't depend on the document's content
            # being extracted on `get_and_process_free_pdf`, where it's
            # only extracted if it doesn't require OCR
            recap_document_into_opinions.s().set(queue=q),
            delete_pacer_row.s(row.pk).set(queue=q),
        )

        c.apply_async()
        completed += 1
        if completed % 1000 == 0:
            logger.info(
                f"Sent {completed}/{count} tasks to celery for {task_name} so far."
            )


def ocr_available(queue: str) -> None:
    """Do the OCR for any items that need it, then save to the ES index.

    :param queue: the queue name
    """
    q = cast(str, queue)
    rds = (
        RECAPDocument.objects.filter(ocr_status=RECAPDocument.OCR_NEEDED)
        .values_list("pk", flat=True)
        .order_by()
    )
    count = rds.count()
    logger.info(f"Total documents requiring OCR: {count}")
    throttle = CeleryThrottle(queue_name=q)
    for i, pk in enumerate(rds):
        throttle.maybe_wait()
        extract_recap_pdf.si(pk, ocr_available=True).set(queue=q).apply_async()
        if i % 1000 == 0:
            logger.info(f"Sent {i + 1}/{count} tasks to celery so far.")


def do_everything(courts, date_start, date_end, queue):
    """Execute the entire process of obtaining the metadata of the free documents,
    downloading them and ingesting them into the system

    :param courts: optionally a list of courts to scrape
    :param date_start: optionally a start date to query all the specified courts or all
    courts
    :param date_end: optionally an end date to query all the specified courts or all
    courts
    :param queue: the queue name
    """
    logger.info("Running and compiling free document reports.")
    get_and_save_free_document_reports(courts, date_start, date_end)
    logger.info("Getting PDFs from free document reports")
    get_pdfs(courts, date_start, date_end, queue)
    logger.info("Doing OCR and saving items.")
    ocr_available(queue)


class Command(VerboseCommand):
    help = "Get all the free content from PACER."

    def valid_actions(self, s: str) -> Callable:
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s"
                % (", ".join(self.VALID_ACTIONS.keys()))
            )

        return self.VALID_ACTIONS[s]

    def validate_date_args(self, opts):
        """Validate dates arguments if any

        :param opts: dictionary with arguments from the command
        :return: true if the date validations are satisfied else false
        """
        if not opts.get("date_start") and not opts.get("date_end"):
            return True
        elif not opts.get("date_start") or not opts.get("date_end"):
            logger.error(
                "Both --date-start and --date-end must be specified together."
            )
            return False
        elif opts.get("date_start") > opts.get("date_end"):
            logger.error(
                "--date-end must be greater than or equal to --date-start."
            )
            return False
        return True

    def filter_kwargs(self, func, kwargs):
        """Keep only the params required to call the function

        :param func: function to be called by the command
        :param kwargs: dictionary with arguments from the command
        :return: dictionary with params required for the function
        """
        valid_params = inspect.signature(func).parameters.keys()
        return {
            key: value for key, value in kwargs.items() if key in valid_params
        }

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--action",
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s"
            % (", ".join(self.VALID_ACTIONS.keys())),
        )
        parser.add_argument(
            "--queue",
            type=str,
            default="pacerdoc1",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--courts",
            type=str,
            default="",
            nargs="*",
            help="The courts that you wish to parse. Use cl ids.",
        )
        parser.add_argument(
            "--date-start",
            dest="date_start",
            required=False,
            type=valid_date,
            help="Date when the query should start.",
        )
        parser.add_argument(
            "--date-end",
            dest="date_end",
            required=False,
            type=valid_date,
            help="Date when the query should end.",
        )

    def handle(self, *args: List[str], **options: OptionsType) -> None:
        super().handle(*args, **options)

        if not self.validate_date_args(options):
            return

        action = cast(Callable, options["action"])
        filtered_kwargs = self.filter_kwargs(action, options)
        action(**filtered_kwargs)

    VALID_ACTIONS: Dict[str, Callable] = {
        "do-everything": do_everything,
        "get-report-results": get_and_save_free_document_reports,
        "get-pdfs": get_pdfs,
        "ocr-available": ocr_available,
    }
