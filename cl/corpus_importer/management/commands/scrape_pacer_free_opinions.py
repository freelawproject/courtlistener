import argparse
import datetime
import inspect
import math
import random
import time
from collections.abc import Callable
from typing import cast

from celery.canvas import chain
from django.db.models import F, Max, Q, Window
from django.db.models.functions import RowNumber
from django.utils.timezone import now
from juriscraper.lib.date_utils import make_date_range_tuples
from juriscraper.lib.exceptions import PacerLoginException
from juriscraper.lib.string_utils import CaseNameTweaker
from juriscraper.pacer.free_documents import FreeOpinionReport
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
from cl.scrapers.tasks import extract_pdf_document
from cl.search.models import Court, RECAPDocument

# How far back to re-attempt days that previously failed and never succeeded.
# Wide enough to drain a multi-month backlog, but bounded so a date PACER can
# never render isn't retried forever (each retry can cost a full proxy
# timeout). Days older than this need manual attention.
OUTSTANDING_FAILED_LOOKBACK_DAYS = 365

# The most recent days are always re-queried (to catch late-posted opinions),
# so a failed day this recent is still being actively retried and shouldn't be
# reported as a gap yet.
RECENT_REQUERY_DAYS = 5

# A court is considered stalled if its newest successful scrape is older than
# this many days. Used by the report-stalls action.
DEFAULT_STALE_DAYS = 14

# Courts we skip when scraping/reporting on the free Written Opinions Report.
# The set has two sources, kept separate on purpose:
#
# 1. Juriscraper's ``FreeOpinionReport.EXCLUDED_COURT_IDS`` — courts whose
#    report can't be fetched or parsed. They don't have the report enabled
# 2. ``CL_OPERATIONAL_EXCLUSIONS`` — courts CL deliberately skips for its own
#    operational reasons (e.g. a court that has IP-blocked us), independent of
#    whether the report is technically fetchable.

CL_OPERATIONAL_EXCLUSIONS: list[str] = []

EXCLUDED_COURT_IDS = sorted(
    set(FreeOpinionReport.EXCLUDED_COURT_IDS) | set(CL_OPERATIONAL_EXCLUSIONS)
)


def get_last_complete_date(
    court_id: str,
) -> datetime.date | None:
    """Get the date a court's next forward scrape should start from.

    Look up the court's most recent non-failed log row. Return its
    ``date_queried``, but never more recent than ``RECENT_REQUERY_DAYS`` ago,
    so the last few days are always re-queried to catch late-posted opinions.

    If the most recent row is still in progress, return ``None``.

    :param court_id: A PACER Court ID
    :return: the date to resume querying from, or None if the court's latest
    scrape is still in progress
    :rtype: datetime.date | None
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

    # Ensure that we go back a few days from the last time we had success if
    # that success was in the last few days.
    last_complete_date = min(
        now().date() - datetime.timedelta(days=RECENT_REQUERY_DAYS),
        last_completion_log.date_queried,
    )
    return last_complete_date


def get_outstanding_failed_dates(
    court_id: str,
    before: datetime.date | None = None,
    floor: datetime.date | None = None,
) -> list[datetime.date]:
    """Return dates that failed and never succeeded.

    A date is "outstanding" when the court has a ``SCRAPE_FAILED`` log for it
    and no ``SCRAPE_SUCCESSFUL`` log for the same date.

    The scraper uses ``before`` (the forward-range start) and ``floor`` (a
    look-back bound) so it only retries days behind the cursor and not older
    than the bound. The report-stalls action calls it with a ``before`` cutoff
    only, to enumerate every still-failing day for visibility.

    :param court_id: A PACER Court ID
    :param before: if given, only dates earlier than this are considered
    :param floor: if given, only dates on or after this are considered
    :returns: sorted list of dates still needing a successful scrape
    :rtype: list[datetime.date]
    """
    cl_court_id = map_pacer_to_cl_id(court_id)
    logs = PACERFreeDocumentLog.objects.filter(court_id=cl_court_id)
    if floor is not None:
        logs = logs.filter(date_queried__gte=floor)
    if before is not None:
        logs = logs.filter(date_queried__lt=before)

    # Resolve the "failed but never succeeded" set in the database (anti-join)
    # so only the gap dates are returned, not the court's whole history.
    succeeded = (
        logs.filter(status=PACERFreeDocumentLog.SCRAPE_SUCCESSFUL)
        .values("date_queried")
        .order_by()
    )
    return list(
        logs.filter(status=PACERFreeDocumentLog.SCRAPE_FAILED)
        .exclude(date_queried__in=succeeded)
        .values_list("date_queried", flat=True)
        .distinct()
        .order_by("date_queried")
    )


def collapse_date_ranges(
    dates: list[datetime.date],
) -> list[tuple[datetime.date, datetime.date]]:
    """Collapse a sorted list of dates into consecutive-day ranges.

    Consecutive calendar days are merged into a single (start, end) tuple so
    they can be scraped in one --date-start/--date-end call.

    :param dates: a sorted list of dates
    :returns: list of inclusive (start, end) ranges
    :rtype: list[tuple[datetime.date, datetime.date]]
    """
    ranges: list[tuple[datetime.date, datetime.date]] = []
    one_day = datetime.timedelta(days=1)
    for day in dates:
        if ranges and day == ranges[-1][1] + one_day:
            ranges[-1] = (ranges[-1][0], day)
        else:
            ranges.append((day, day))
    return ranges


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
    day_span: int = 1,
) -> bool:
    """Get free documents from pacer

    Get free documents from pacer and save each using PACERFreeDocumentRow model

    :param pacer_court_id: Pacer court id to fetch
    :param start: start date to query
    :param end: end date to query
    :param day_span: how many days each PACER sub-query should cover
    :return: true if the scrape failed else false
    """
    log = mark_court_in_progress(pacer_court_id, end)

    logger.info(
        "Attempting to get latest document references for "
        "%s between %s and %s",
        pacer_court_id,
        start,
        end,
    )
    try:
        status, document_count = get_and_save_free_document_report(
            pacer_court_id, start, end, log.pk, day_span=day_span
        )  # type: ignore
    except (
        RequestException,
        ReadTimeoutError,
        IndexError,
        TypeError,
        PacerLoginException,
        ValueError,
    ) as exc:
        if isinstance(exc, (RequestException | ReadTimeoutError)):
            reason = "network error."
        elif isinstance(exc, IndexError):
            reason = (
                "PACER 6.3 bug or incomplete/truncated response "
                "(likely proxy timeout)."
            )
        elif isinstance(exc, (TypeError | ValueError)):
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
        mark_court_done_on_date(log.pk, PACERFreeDocumentLog.SCRAPE_FAILED)
        return True

    if status != PACERFreeDocumentLog.SCRAPE_SUCCESSFUL:
        # The task exhausted its retries and reported failure without
        # raising. The result count is unknown, so it stays null.
        logger.error(
            "Failed to get free document references for %s between %s and %s.",
            pacer_court_id,
            start,
            end,
        )
        mark_court_done_on_date(log.pk, status)
        return True

    logger.info(
        "Got %s document references for %s between %s and %s",
        document_count,
        pacer_court_id,
        start,
        end,
    )
    mark_court_done_on_date(log.pk, status, document_count=document_count)
    return False


def get_and_save_free_document_reports(
    courts: list[str | None],
    date_start: datetime.date | None,
    date_end: datetime.date | None,
    day_span: int = 1,
) -> None:
    """Query the Free Doc Reports on PACER and get a list of all the free
    documents. Do not download those items, as that step is done later. For now
    just get the list.

    Note that the ``get_and_save_free_document_report`` Celery task is invoked
    synchronously (in-process) here, one court and date at a time, rather than
    being enqueued. A previous version dispatched the work asynchronously, but
    in Celery 4.2.0 (more accurately in redis-py 3.x.x) that failed nearly every
    time. This is simpler and slower, but reliable.

    :param courts: optionally a list of courts to scrape
    :param date_start: optionally a start date to query all the specified courts or all
    courts
    :param date_end: optionally an end date to query all the specified courts or all
    courts
    :param day_span: how many days each PACER sub-query should cover
    """
    # Kill any *old* logs that report they're in progress. (They've failed.)
    three_hrs_ago = now() - datetime.timedelta(hours=3)
    PACERFreeDocumentLog.objects.filter(
        date_started__lt=three_hrs_ago,
        status=PACERFreeDocumentLog.SCRAPE_IN_PROGRESS,
    ).update(status=PACERFreeDocumentLog.SCRAPE_FAILED)

    base_filter = Q(in_use=True, end_date=None) & ~Q(pk__in=EXCLUDED_COURT_IDS)
    if courts:
        base_filter &= Q(pk__in=courts)

    cl_court_ids = (
        Court.federal_courts.district_or_bankruptcy_pacer_courts()
        .filter(base_filter)
        .values_list("pk", flat=True)
    )

    pacer_court_ids = [map_cl_to_pacer_id(v) for v in cl_court_ids]

    explicit_dates = None
    if date_start and date_end:
        # If we pass the dates in the command then we generate the range on those dates
        # The first date queried is 1950-05-12 from ca9, that should be the starting
        # point for the sweep
        explicit_dates = make_date_range_tuples(
            date_start, date_end, gap=day_span
        )

    for pacer_court_id in pacer_court_ids:
        if explicit_dates is not None:
            # Explicit range from the command: query the same dates for every
            # court (manual run / backfill).
            court_dates = explicit_dates
        else:
            # No date args: resume each court from its own cursor.
            try:
                court_date_start = get_last_complete_date(pacer_court_id)
            except PACERFreeDocumentLog.DoesNotExist:
                # The court has no successful scrape to resume from. Skip it
                # until a baseline exists rather than crashing the whole run.
                logger.warning(
                    "No completed scrape log for %s; skipping until a "
                    "baseline exists.",
                    pacer_court_id,
                )
                continue
            if not court_date_start:
                logger.warning(
                    f"Free opinion scraper for {pacer_court_id} still "
                    "in progress."
                )
                continue
            court_date_end = datetime.date.today()
            forward_dates = make_date_range_tuples(
                court_date_start, court_date_end, gap=day_span
            )
            # Retry days that previously failed and never succeeded so that a
            # later success advancing the cursor doesn't leave a permanent gap.
            failed_dates = get_outstanding_failed_dates(
                pacer_court_id,
                before=court_date_start,
                floor=now().date()
                - datetime.timedelta(days=OUTSTANDING_FAILED_LOOKBACK_DAYS),
            )
            court_dates = [(d, d) for d in failed_dates] + forward_dates

        # Iterate through the dates, continuing past failures so good days
        # still advance the court instead of bailing the whole court.
        for _start, _end in court_dates:
            exc = fetch_doc_report(
                pacer_court_id,
                _start,
                _end,  # type: ignore
                day_span=day_span,
            )
            if exc:
                # This day failed (already recorded as SCRAPE_FAILED). Keep
                # going; it stays on the retry queue for a later run. The
                # failed row is kept as history; once the day later succeeds
                # it gets its own SCRAPE_SUCCESSFUL row, and
                # get_outstanding_failed_dates stops re-queuing it.
                logger.warning(
                    "Chunk failed for %s (%s to %s); continuing with the "
                    "next date.",
                    pacer_court_id,
                    _start,
                    _end,
                )

            # Wait 1s between queries to try to avoid a possible throttling/blocking
            # from the court
            time.sleep(1)


def get_pdfs(
    courts: list[str | None],
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
        .values_list("pk", "court_id")
    )

    # Materialize the ordered (pk, court_id) pairs up front. If done through a
    # cursor the connection will eventually die due to CeleryThrottle + sleeps.
    # Each row is (int, 15-char) string, so the backlog should fit. Currently
    # the pod has no memory limits. See #7507
    rows_list = list(rows)
    count = len(rows_list)
    task_name = "downloading"
    logger.info(
        f"{task_name} {count} items from PACER from {date_start} to {date_end}."
    )
    throttle = CeleryThrottle(queue_name=q)
    completed = 0
    cycle_checker = CycleChecker()
    for pk, court_id in rows_list:
        # Wait until the queue is short enough
        throttle.maybe_wait()

        if cycle_checker.check_if_cycled(court_id):
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
                f"Court cycle completed for: {court_id}. Current iteration: {cycle_checker.current_iteration}. Sleep 1 second "
                f"before starting the next cycle."
            )
            time.sleep(1)

        logger.info(f"Processing row id: {pk} from {court_id}")
        c = chain(
            process_free_opinion_result.si(
                pk,
                court_id,
                cnt,
            ).set(queue=q),
            get_and_process_free_pdf.s(pk, court_id, q).set(queue=q),
            # `recap_document_into_opinions` uses a different doctor extraction
            # endpoint, so it doesn't depend on the document's content
            # being extracted on `get_and_process_free_pdf`, where it's
            # only extracted if it doesn't require OCR
            recap_document_into_opinions.s().set(queue=q),
            delete_pacer_row.s(pk).set(queue=q),
        )

        # we accept same hash RecapDocuments; but we don't want duplicates in
        # Opinions. Introduce some time variability between consecutive tasks
        # to help the hash checks in `recap_document_into_opinions` work
        c.apply_async(countdown=random.uniform(3, 10))
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
        extract_pdf_document.si(pk, ocr_available=True, citation_queue=q).set(
            queue=q
        ).apply_async()
        if i % 1000 == 0:
            logger.info(f"Sent {i + 1}/{count} tasks to celery so far.")


def report_free_document_scrape_stalls(
    courts: list[str | None],
    stale_days: int = DEFAULT_STALE_DAYS,
) -> list[tuple[str, datetime.date | None]]:
    """Alert when a court's free-opinion scrape hasn't advanced or has gaps.

    For every in-use PACER court (optionally limited to ``courts``) this does
    two checks, each logged at error level with its own Sentry fingerprint:

    1. Stall: find the newest non-failed ``date_queried`` and flag any court
       whose newest success is older than ``stale_days`` (or which has no
       successful scrape at all) so a silent freeze is caught regardless of the
       underlying failure mode.
    2. Gaps: enumerate days that failed and never succeeded (older than the
       active re-query window, which is still being retried), so individual
       stuck days behind an advancing cursor are surfaced for investigation.

    :param courts: optionally a list of CL court ids to check
    :param stale_days: a court is stalled if its newest success is older than
    this many days
    :returns: list of (court_id, latest_success_date) for stalled courts
    :rtype: list[tuple[str, datetime.date | None]]
    """
    base_filter = Q(in_use=True, end_date=None) & ~Q(pk__in=EXCLUDED_COURT_IDS)
    if courts:
        base_filter &= Q(pk__in=courts)

    cl_court_ids = list(
        Court.federal_courts.district_or_bankruptcy_pacer_courts()
        .filter(base_filter)
        .values_list("pk", flat=True)
    )

    stale_threshold = now().date() - datetime.timedelta(days=stale_days)
    latest_by_court = dict(
        PACERFreeDocumentLog.objects.filter(court_id__in=cl_court_ids)
        .exclude(status=PACERFreeDocumentLog.SCRAPE_FAILED)
        .values_list("court_id")
        .annotate(latest=Max("date_queried"))
        .values_list("court_id", "latest")
    )

    stalled: list[tuple[str, datetime.date | None]] = []
    for court_id in cl_court_ids:
        latest = latest_by_court.get(court_id)
        if latest is None or latest < stale_threshold:
            stalled.append((court_id, latest))

    for court_id, latest in stalled:
        logger.error(
            "Free opinion scrape stalled for %s: last success %s "
            "(threshold %s days).",
            court_id,
            latest if latest else "never",
            stale_days,
            extra={"fingerprint": ["pacer-free-opinion-stall", court_id]},
        )

    # Enumerate individual gap days (failed, never succeeded) that are past the
    # active re-query window. Recent failures are excluded because they're still
    # being retried automatically.
    gap_cutoff = now().date() - datetime.timedelta(days=RECENT_REQUERY_DAYS)
    for court_id in cl_court_ids:
        gaps = get_outstanding_failed_dates(court_id, before=gap_cutoff)
        if not gaps:
            continue
        ranges = collapse_date_ranges(gaps)
        # One line per range: a single day shows the date, a span shows
        # "start to end". Each line is usable as --date-start / --date-end.
        range_lines = "\n".join(
            start.isoformat()
            if start == end
            else f"{start.isoformat()} to {end.isoformat()}"
            for start, end in ranges
        )
        logger.error(
            "Free opinion scrape has %s outstanding failed day(s) in %s "
            "range(s) for %s (some of these days may simply have no opinions; "
            "re-running them will mark them complete):\n%s",
            len(gaps),
            len(ranges),
            court_id,
            range_lines,
            # Constant fingerprint (no court_id) so every court's gap report
            # groups into a single Sentry issue; each court arrives as its own
            # event under it.
            extra={"fingerprint": ["pacer-free-opinion-gaps"]},
        )

    if not stalled:
        logger.info(
            "No stalled free opinion scrapes (threshold %s days).", stale_days
        )

    return stalled


def do_everything(courts, date_start, date_end, queue, day_span=1):
    """Execute the entire process of obtaining the metadata of the free documents,
    downloading them and ingesting them into the system

    :param courts: optionally a list of courts to scrape
    :param date_start: optionally a start date to query all the specified courts or all
    courts
    :param date_end: optionally an end date to query all the specified courts or all
    courts
    :param queue: the queue name
    :param day_span: how many days each PACER sub-query should cover
    """
    logger.info("Running and compiling free document reports.")
    get_and_save_free_document_reports(
        courts, date_start, date_end, day_span=day_span
    )
    logger.info("Getting PDFs from free document reports")
    get_pdfs(courts, date_start, date_end, queue)
    logger.info("Doing OCR and saving items.")
    ocr_available(queue)
    logger.info("Checking for stalled court scrapes.")
    report_free_document_scrape_stalls(courts)


class Command(VerboseCommand):
    help = "Get all the free content from PACER."

    def valid_actions(self, s: str) -> Callable:
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: {}".format(
                    ", ".join(self.VALID_ACTIONS.keys())
                )
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
            help="The action you wish to take. Valid choices are: {}".format(
                ", ".join(self.VALID_ACTIONS.keys())
            ),
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
        parser.add_argument(
            "--day-span",
            dest="day_span",
            required=False,
            type=int,
            default=1,
            help=(
                "How many days each PACER sub-query should cover. Defaults "
                "to 1 day at a time to stay within proxy read timeouts on "
                "busy courts. Use larger values for low-volume courts."
            ),
        )
        parser.add_argument(
            "--stale-days",
            dest="stale_days",
            required=False,
            type=int,
            default=DEFAULT_STALE_DAYS,
            help=(
                "For the report-stalls action: flag a court whose newest "
                "successful scrape is older than this many days."
            ),
        )

    def handle(self, *args: list[str], **options: OptionsType) -> None:
        super().handle(*args, **options)

        if not self.validate_date_args(options):
            return

        action = cast(Callable, options["action"])
        filtered_kwargs = self.filter_kwargs(action, options)
        action(**filtered_kwargs)

    VALID_ACTIONS: dict[str, Callable] = {
        "do-everything": do_everything,
        "get-report-results": get_and_save_free_document_reports,
        "get-pdfs": get_pdfs,
        "ocr-available": ocr_available,
        "report-stalls": report_free_document_scrape_stalls,
    }
