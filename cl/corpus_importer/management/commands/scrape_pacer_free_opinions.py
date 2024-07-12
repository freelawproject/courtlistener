import argparse
import calendar
import datetime
import os
from typing import Callable, Dict, List, Optional, Tuple, cast

from celery.canvas import chain
from django.conf import settings
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
)
from cl.lib.argparse_types import valid_date
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer import map_cl_to_pacer_id, map_pacer_to_cl_id
from cl.lib.types import OptionsType
from cl.scrapers.models import PACERFreeDocumentLog, PACERFreeDocumentRow
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import Court, RECAPDocument
from cl.search.tasks import add_docket_to_solr_by_rds, add_items_to_solr

PACER_USERNAME = os.environ.get("PACER_USERNAME", settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", settings.PACER_PASSWORD)


def get_next_date_range(
    court_id: str,
    span: int = 7,
) -> Tuple[Optional[datetime.date], Optional[datetime.date]]:
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
        last_completion_log = (
            PACERFreeDocumentLog.objects.filter(court_id=court_id)
            .exclude(status=PACERFreeDocumentLog.SCRAPE_FAILED)
            .latest("date_queried")
        )
    except PACERFreeDocumentLog.DoesNotExist:
        logger.warning(f"FAILED ON: {court_id}")
        raise

    if last_completion_log.status == PACERFreeDocumentLog.SCRAPE_IN_PROGRESS:
        return None, None

    # Ensure that we go back five days from the last time we had success if
    # that success was in the last few days.
    last_complete_date = min(
        now().date() - datetime.timedelta(days=5),
        last_completion_log.date_queried,
    )
    next_end_date = min(
        now().date(), last_complete_date + datetime.timedelta(days=span)
    )
    return last_complete_date, next_end_date


def mark_court_in_progress(
    court_id: str, d: datetime.date
) -> PACERFreeDocumentLog:
    log = PACERFreeDocumentLog.objects.create(
        status=PACERFreeDocumentLog.SCRAPE_IN_PROGRESS,
        date_queried=d,
        court_id=map_pacer_to_cl_id(court_id),
    )
    return log


def fetch_doc_report(
    pacer_court_id: int,
    start: Optional[datetime.date],
    end: Optional[datetime.date],
    log_id: int = 0,
):
    exception_raised = False
    status = PACERFreeDocumentLog.SCRAPE_FAILED
    rows_to_create = 0

    logger.info(
        "Attempting to get latest document references for "
        "%s between %s and %s",
        pacer_court_id,
        start,
        end,
    )
    try:
        status, rows_to_create = get_and_save_free_document_report(pacer_court_id, start, end, log_id)  # type: ignore
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

    logger.info(
        "Got %s document references for " "%s between %s and %s",
        rows_to_create,
        pacer_court_id,
        start,
        end,
    )

    return exception_raised, status


def get_and_save_free_document_reports(options: OptionsType) -> None:
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
    three_hrs_ago = now() - datetime.timedelta(hours=3)
    PACERFreeDocumentLog.objects.filter(
        date_started__lt=three_hrs_ago,
        status=PACERFreeDocumentLog.SCRAPE_IN_PROGRESS,
    ).update(status=PACERFreeDocumentLog.SCRAPE_FAILED)

    excluded_court_ids = ["casb", "gub", "ilnb", "innb", "miwb", "ohsb", "prb"]

    if options["courts"] != ["all"]:
        cl_court_ids = (
            Court.federal_courts.district_or_bankruptcy_pacer_courts()
            .filter(
                in_use=True,
                end_date=None,
                pk__in=options["courts"],
            )
            .exclude(pk__in=excluded_court_ids)
            .values_list("pk", flat=True)
        )
    else:
        cl_court_ids = (
            Court.federal_courts.district_or_bankruptcy_pacer_courts()
            .filter(
                in_use=True,
                end_date=None,
            )
            .exclude(pk__in=excluded_court_ids)
            .values_list("pk", flat=True)
        )

    pacer_court_ids = [map_cl_to_pacer_id(v) for v in cl_court_ids]

    if options["date_start"] and options["date_end"]:
        for pacer_court_id in pacer_court_ids:
            # Here we do not save the log since if an incorrect range is entered
            # the next time the daily cron is executed the command could skip days
            exc, status = fetch_doc_report(
                pacer_court_id, options["date_start"], options["date_end"]  # type: ignore
            )
            if exc:
                break
    else:
        today = now()
        for pacer_court_id in pacer_court_ids:
            while True:
                next_start_d, next_end_d = get_next_date_range(pacer_court_id)
                if next_end_d is None:
                    logger.warning(
                        f"Free opinion scraper for {pacer_court_id} still "
                        "in progress."
                    )
                    break

                log = mark_court_in_progress(pacer_court_id, next_end_d)

                exc, status = fetch_doc_report(
                    pacer_court_id, next_start_d, next_end_d, log.pk
                )
                if exc:
                    # Something failed
                    mark_court_done_on_date(
                        log.pk,
                        PACERFreeDocumentLog.SCRAPE_FAILED,
                    )
                    break

                # Scrape successful
                mark_court_done_on_date(log.pk, status)

                if status == PACERFreeDocumentLog.SCRAPE_SUCCESSFUL:
                    if next_end_d >= today.date():
                        logger.info(
                            "Got all document references for '%s'.",
                            pacer_court_id,
                        )
                        # Break from while loop, onwards to next court
                        break
                    else:
                        # More dates to do; let it continue
                        continue

                elif status == PACERFreeDocumentLog.SCRAPE_FAILED:
                    logger.error(
                        "Encountered critical error on %s "
                        "(network error?). Marking as failed and "
                        "pressing on." % pacer_court_id,
                        exc_info=True,
                    )
                    # Break from while loop, onwards to next court
                    break


def get_pdfs(options: OptionsType) -> None:
    """Get PDFs for the results of the Free Document Report queries.

    At this stage, we have rows in the PACERFreeDocumentRow table, each of
    which represents a PDF we need to download and merge into our normal
    tables: Docket, DocketEntry, and RECAPDocument.

    In this function, we iterate over the entire table of results, merge it
    into our normal tables, and then download and extract the PDF.

    :return: None
    """
    q = cast(str, options["queue"])
    index = options["index"]
    cnt = CaseNameTweaker()
    rows = PACERFreeDocumentRow.objects.filter(error_msg="")

    if options["courts"] != ["all"]:
        rows = rows.filter(court_id__in=options["courts"])

    if options["date_start"] and options["date_end"]:
        rows = rows.filter(
            date_filed__gte=options["date_start"],
            date_filed__lte=options["date_end"],
        )

    rows = rows.only("pk")
    count = rows.count()
    task_name = "downloading"
    if index:
        task_name += " and indexing"
    logger.info(f"{task_name} {count} items from PACER.")
    throttle = CeleryThrottle(queue_name=q)
    completed = 0
    for row in rows.iterator():
        throttle.maybe_wait()
        c = chain(
            process_free_opinion_result.si(
                row.pk,
                row.court_id,
                cnt,
            ).set(queue=q),
            get_and_process_free_pdf.s(row.pk, row.court_id).set(queue=q),
            delete_pacer_row.s(row.pk).set(queue=q),
        )
        if index:
            c = c | add_items_to_solr.s("search.RECAPDocument").set(queue=q)
        c.apply_async()
        completed += 1
        if completed % 1000 == 0:
            logger.info(
                f"Sent {completed}/{count} tasks to celery for {task_name} so far."
            )


def ocr_available(options: OptionsType) -> None:
    """Do the OCR for any items that need it, then save to the solr index."""
    q = cast(str, options["queue"])
    rds = (
        RECAPDocument.objects.filter(ocr_status=RECAPDocument.OCR_NEEDED)
        .values_list("pk", flat=True)
        .order_by()
    )
    count = rds.count()
    throttle = CeleryThrottle(queue_name=q)
    for i, pk in enumerate(rds):
        throttle.maybe_wait()
        if options["index"]:
            extract_recap_pdf.si(pk, ocr_available=True).set(
                queue=q
            ).apply_async()
        else:
            chain(
                extract_recap_pdf.si(pk, ocr_available=True).set(queue=q),
                add_docket_to_solr_by_rds.s().set(queue=q),
            ).apply_async()
        if i % 1000 == 0:
            logger.info(f"Sent {i + 1}/{count} tasks to celery so far.")


def do_quarterly(options: OptionsType):
    """Collect last quarter documents

    Run it every three months (0 0 1 */3 *)

    :return: None
    """
    first_day_current_month = datetime.datetime.now().replace(day=1)

    # Calculate the first day of the month three months ago
    if first_day_current_month.month <= 3:
        start_year = first_day_current_month.year - 1
        start_month = first_day_current_month.month + 9
    else:
        start_year = first_day_current_month.year
        start_month = first_day_current_month.month - 3
    start_date = datetime.date(start_year, start_month, 1)

    # Calculate the last day of the month prior to today
    last_month = first_day_current_month - datetime.timedelta(days=1)
    end_day = calendar.monthrange(last_month.year, last_month.month)[1]
    end_date = datetime.date(last_month.year, last_month.month, end_day)

    dates = make_date_range_tuples(start_date, end_date, gap=7)

    for _start, _end in dates:
        # We run this in 7-day date ranges to ingest all the information on a weekly
        # basis and not wait for all the responses from three months ago to now from
        # each court. This also allows us to scrape each court every 7 day range to
        # avoid possible blockages.
        options["date_start"] = _start  # type: ignore
        options["date_end"] = _end  # type: ignore
        do_everything(options)


def do_monthly(options: OptionsType):
    """Collect last month's documents

    Run it on the 3rd of each month to let them update the last days of the month
    (15 2 3 * *)

    :return: None
    """
    today = datetime.date.today()
    prev_month, current_year = (
        (today.month - 1, today.year)
        if today.month != 1
        else (12, today.year - 1)
    )
    month_last_day = calendar.monthrange(current_year, prev_month)[1]
    start = datetime.date(current_year, prev_month, 1)
    end = datetime.date(current_year, prev_month, month_last_day)

    # Update options with start and end date of previous month
    options["date_start"] = start  # type: ignore
    options["date_end"] = end  # type: ignore

    do_everything(options)


def do_weekly(options: OptionsType):
    """Collect last week's documents

    Run it every wednesday (* * * * 3)

    :return: None
    """

    today = datetime.date.today()
    weekday = today.weekday()
    start_of_this_week = today - datetime.timedelta(days=weekday)
    start_of_previous_week = start_of_this_week - datetime.timedelta(weeks=1)
    end_of_previous_week = start_of_previous_week + datetime.timedelta(days=6)

    # Update options with start and end date of previous week
    options["date_start"] = start_of_previous_week  # type: ignore
    options["date_end"] = end_of_previous_week  # type: ignore

    do_everything(options)


def do_all(options: OptionsType):
    """Collect all documents since the beginning of time

    It was established on this date based on the PacerFreeDocumentLog table. The first
    date queried is 1950-05-12 from ca9.

    The command will be executed until the day on which it is executed.

    To collect all documents, weekly, monthly and quarterly sweeps will be used to make
    sure we don't miss anything.

    Take note that documents could be missing if they were marked as free after these
    periods.

    :return: None
    """
    start = datetime.date(1950, 5, 1)
    end = datetime.date.today()

    dates = make_date_range_tuples(start, end, gap=7)

    for _start, _end in dates:
        # We run this in 7-day date ranges to ingest all the information on a weekly
        # basis and not wait for all the responses from 1950 to now from each court (
        # ~3900 weeks/requests until today). This also allows us to scrape each court
        # every 7 day range to avoid possible blockages.
        options["date_start"] = _start  # type: ignore
        options["date_end"] = _end  # type: ignore
        do_everything(options)


def do_everything(options: OptionsType):
    logger.info("Running and compiling free document reports.")
    get_and_save_free_document_reports(options)
    logger.info("Getting PDFs from free document reports")
    get_pdfs(options)
    logger.info("Doing OCR and saving items to Solr.")
    ocr_available(options)


class Command(VerboseCommand):
    help = "Get all the free content from PACER."

    def valid_actions(self, s: str) -> Callable:
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s"
                % (", ".join(self.VALID_ACTIONS.keys()))
            )

        return self.VALID_ACTIONS[s]

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
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--index",
            action="store_true",
            default=False,
            help="Do we index as we go, or leave that to be done later?",
        )
        parser.add_argument(
            "--courts",
            type=str,
            default=["all"],
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

        if options["date_start"] and options["date_end"]:
            if options["date_start"] > options["date_end"]:  # type: ignore
                print(
                    "Error: date-end must be greater or equal than date-start option."
                )
                return
        action = cast(Callable, options["action"])
        action(options)

    VALID_ACTIONS: Dict[str, Callable] = {
        "do-everything": do_everything,
        "get-report-results": get_and_save_free_document_reports,
        "get-pdfs": get_pdfs,
        "ocr-available": ocr_available,
        "do-quarterly": do_quarterly,
        "do-monthly": do_monthly,
        "do-weekly": do_weekly,
        "do-all": do_all,
    }
