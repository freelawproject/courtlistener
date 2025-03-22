import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management.base import CommandError
from django.db.models import Q
from django.utils import timezone

from cl import settings
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer_session import get_or_cache_pacer_cookies
from cl.lib.utils import append_value_in_cache
from cl.recap.models import PROCESSING_STATUS, REQUEST_TYPE, PacerFetchQueue
from cl.recap.tasks import fetch_pacer_doc_by_rd_and_mark_fq_completed
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import Court, RECAPDocument


class SkipReason(Enum):
    FAILED = 0
    MAX_RETRIES = 1
    FETCH_IN_PROGRESS = 2
    WAITING_INTERVAL = 3


@dataclass
class SkipStatus:
    should_skip: bool
    reason: SkipReason | None = None
    fetch_queue: PacerFetchQueue | None = None


class MinimumWait:
    """Tracks the minimum time to wait during an iteration."""

    def __init__(self):
        self.min_value = None

    def add(self, num: int) -> None:
        """Only store the value if it's smaller than the current min."""
        self.min_value = (
            num if self.min_value is None else min(self.min_value, num)
        )

    def get(self) -> int:
        """Return the value stored."""
        return self.min_value


def enough_time_elapsed(
    datetime_to_compare: datetime, time_interval: int
) -> bool:
    """Check if enough time has elapsed since datetime_to_compare

    :param datetime_to_compare: The datetime to compare against the
    current time.
    :param time_interval: The time interval to compare against in seconds.
    :return: True if the difference between now and the given date exceeds
    the defined interval, otherwise False.
    """
    now = timezone.now()
    return (now - datetime_to_compare) > timedelta(seconds=time_interval)


def is_retry_interval_elapsed(
    date_created: datetime, retry_count: int, time_start: float
) -> tuple[bool, int]:
    """Check if the retry interval has elapsed based on the exponential backoff
    policy.

    :param date_created: The datetime when the FQ was created.
    :param retry_count: The number of retry attempts already made.
    :param time_start: The base time interval for the exponential backoff.
    :return: A two tuple, a bool True if the required time has elapsed since
    date_created, otherwise False. An integer representing the next_time_to_wait
    """

    exponential_backoff = int(pow(time_start, retry_count + 1))
    prev_exponential_backoff = int(pow(time_start, retry_count))
    # exponential_backoff is the time in seconds used to compare against the
    # FQ's date_created, and it represents the maximum total time we want to
    # wait before an FQ completes all its retry attempts.
    # Therefore, the next_time_to_wait for a new iteration is calculated as the
    # difference between the previous backoff time and the current one.
    next_time_to_wait = (exponential_backoff - prev_exponential_backoff) + 1
    return (
        enough_time_elapsed(date_created, exponential_backoff),
        next_time_to_wait,
    )


class Command(VerboseCommand):
    help = "Download multiple documents from PACER with rate limiting"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = None
        self.user = None
        self.recap_documents = []
        self.courts_with_docs = {}
        self.total_launched = 0
        self.max_retries = 6
        self.pacer_username = os.environ.get(
            "PACER_USERNAME", settings.PACER_USERNAME
        )
        self.pacer_password = os.environ.get(
            "PACER_PASSWORD", settings.PACER_PASSWORD
        )
        self.throttle = None
        self.queue_name = None
        self.interval = None
        self.initial_backoff_time = None
        self.max_fq_wait = 3600  # 1 hour. Maximum wait time for an FQ to be completed to prevent a deadlock
        self.fetches_in_progress = {}  # {court_id: (fq_pk, retry_count)}

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--interval",
            type=int,
            default=2,
            help="The minimum wait in secs between PACER fetches to the same court.",
        )
        parser.add_argument(
            "--initial-backoff-time",
            type=float,
            default=2.85,
            help="Initial wait time (in seconds) for the exponential backoff "
            "policy before rechecking if an FQ has been completed.",
        )
        parser.add_argument(
            "--min-page-count",
            type=int,
            help="Get docs with this number of pages or more",
        )
        parser.add_argument(
            "--max-page-count",
            type=int,
            default=10_000,
            help="Get docs with this number of pages or less",
        )
        parser.add_argument(
            "--username",
            type=str,
            default="recap",
            help="Username to associate with the processing queues (defaults to 'recap')",
        )
        parser.add_argument(
            "--queue-name",
            type=str,
            default="batch0",
            help="Celery queue name used for processing tasks",
        )
        parser.add_argument(
            "--testing",
            type=str,
            help="Useful for testing purposes. Reduce retries to 1.",
        )
        parser.add_argument(
            "--stage",
            type=str,
            choices=["fetch", "process"],
            required=True,
            help="Stage of the command to run: fetch or process",
        )

    @staticmethod
    def docs_to_process_cache_key():
        """Helper method to improve testability."""
        return "pacer_bulk_fetch.docs_to_process"

    @staticmethod
    def failed_docs_cache_key():
        """Helper method to improve testability."""
        return "pacer_bulk_fetch.failed_docs"

    def setup_celery(self) -> None:
        """Setup Celery by setting the queue_name and throttle."""
        self.queue_name = self.options["queue_name"]
        self.throttle = CeleryThrottle(queue_name=self.queue_name)

    def handle_pacer_session(self) -> None:
        """Make sure we have an active PACER session for the user."""
        get_or_cache_pacer_cookies(
            self.user.pk,
            username=self.pacer_username,
            password=self.pacer_password,
        )

    def identify_documents(self) -> None:
        """Get eligible documents grouped by court"""
        filters = [
            Q(pacer_doc_id__isnull=False),
            Q(is_available=False),
            Q(page_count__gte=self.options["min_page_count"]),
            Q(page_count__lte=self.options["max_page_count"]),
        ]

        # Do not attempt to fetch docs that were already fetched:
        cached_fetches = cache.get(self.docs_to_process_cache_key(), [])
        previously_fetched = [rd_pk for (rd_pk, _) in cached_fetches]
        ids_to_skip = set(previously_fetched)
        self.recap_documents = (
            RECAPDocument.objects.filter(*filters)
            .exclude(pk__in=ids_to_skip)
            .select_related("docket_entry__docket")
            .values(
                "id",
                "page_count",
                "docket_entry__docket__court_id",
                "pacer_doc_id",
            )
            .order_by("pacer_doc_id")
            .distinct(
                "pacer_doc_id"
            )  # Exclude duplicate documents for subdockets
        )

        courts = (
            Court.objects.filter(
                id__in=[
                    recap_doc_id["docket_entry__docket__court_id"]
                    for recap_doc_id in self.recap_documents
                ]
            )
            .order_by("pk")
            .distinct()
        )

        self.courts_with_docs = {
            court.pk: [
                doc
                for doc in self.recap_documents
                if doc["docket_entry__docket__court_id"] == court.pk
            ]
            for court in courts
        }

    def enqueue_pacer_fetch(self, doc: dict) -> PacerFetchQueue:
        """Actually apply the task to fetch the doc from PACER.

        The ids for the fetched RD and their corresponding FQ are stored
        in cache so we know which ones to process in a later stage of
        this command.
        """
        self.throttle.maybe_wait()
        rd_pk = doc.get("id")
        fq = PacerFetchQueue.objects.create(
            request_type=REQUEST_TYPE.PDF,
            recap_document_id=rd_pk,
            user_id=self.user.pk,
        )
        fetch_pacer_doc_by_rd_and_mark_fq_completed.si(
            rd_pk, fq.pk
        ).apply_async(queue=self.queue_name)
        append_value_in_cache(self.docs_to_process_cache_key(), (rd_pk, fq.pk))
        self.total_launched += 1
        logger.info(
            "Launched download for doc %s from court %s",
            doc.get("id"),
            doc.get("docket_entry__docket__court_id"),
        )
        logger.info(
            "Progress: %s/%s", self.total_launched, len(self.recap_documents)
        )
        return fq

    def should_skip(self, court_id: str) -> SkipStatus:
        """Determine if the court is ready to be queried again.

        To hit the same court again, the last fetch queue must have
        been completed more than `self.interval` seconds ago.

        :return: A two-tuple containing True if the court is ready to be queried again,
        False otherwise, and whether a long wait is needed.
        """
        fetch_in_progress_court = self.fetches_in_progress.get(court_id)
        if not fetch_in_progress_court:
            return SkipStatus(should_skip=False)

        fq_pk, retry_count = fetch_in_progress_court
        fetch_queue = PacerFetchQueue.objects.get(id=fq_pk)
        fq_failed = fetch_queue.status in [
            PROCESSING_STATUS.FAILED,
            PROCESSING_STATUS.INVALID_CONTENT,
            PROCESSING_STATUS.NEEDS_INFO,
        ]

        if retry_count >= self.max_retries:
            # max retries exceeded.
            return SkipStatus(
                should_skip=True,
                reason=SkipReason.MAX_RETRIES,
                fetch_queue=fetch_queue,
            )

        if fq_failed:
            # Fetch is explicitly failed.
            return SkipStatus(
                should_skip=True,
                reason=SkipReason.FAILED,
                fetch_queue=fetch_queue,
            )

        date_completed = fetch_queue.date_completed
        if date_completed is None:
            # Fetch is still in progress
            return SkipStatus(
                should_skip=True,
                reason=SkipReason.FETCH_IN_PROGRESS,
                fetch_queue=fetch_queue,
            )

        if not enough_time_elapsed(date_completed, self.interval):
            #  IF FQ has been completed but not enough time has elapsed, wait
            #  by skipping it for now.
            return SkipStatus(
                should_skip=True,
                reason=SkipReason.WAITING_INTERVAL,
                fetch_queue=fetch_queue,
            )

        return SkipStatus(should_skip=False)

    def fetch_next_doc_in_court(
        self,
        court_id: str,
        remaining_courts: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Pop next doc in court and add fetch task to get it from PACER.

        If the last FQ for the court is still in progress or was completed
        less than `self.interval` seconds ago, we skip it and wait for
        the next round to try the same court again.
        """
        if remaining_courts.get(court_id):
            doc = remaining_courts[court_id].pop(0)
            fq = self.enqueue_pacer_fetch(doc)
            self.fetches_in_progress[court_id] = (fq.pk, 0)

    def cleanup_finished_court(
        self, court_id: str, remaining_courts: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Remove a court from remaining_courts and fetches_in_progress
        if no documents remain and its last FQ task has completed.

        :param court_id: the court to clean up
        :param remaining_courts: the remaining courts
        :return: None
        """
        fetch_in_progress = self.fetches_in_progress.get(court_id)
        if not remaining_courts.get(court_id) and fetch_in_progress:
            fq_pk, _ = fetch_in_progress
            fetch_queue = PacerFetchQueue.objects.get(id=fq_pk)
            # Only clean up if the FQ is completed
            if fetch_queue.date_completed:
                remaining_courts.pop(court_id, None)
                self.fetches_in_progress.pop(court_id, None)

    def process_skip_reason(
        self,
        court_id: str,
        skip_status: SkipStatus,
        remaining_courts: dict[str, list[dict[str, Any]]],
    ) -> int | None:
        """Handle the reason for skipping a fetch attempt and update tracking data accordingly.

        :param court_id: The court_id for which the fetch attempt is being processed.
        :param skip_status: The SkipStatus response.
        :param remaining_courts: A dictionary mapping court IDs to lists of pending fetch attempts.
        :return: None or the corresponding exponential_backoff computed in seconds.
        """
        fetch_queue = skip_status.fetch_queue
        fetch_in_progress_court = self.fetches_in_progress.get(court_id)
        if fetch_queue is None or fetch_in_progress_court is None:
            return None
        fq_pk, retry_count = fetch_in_progress_court
        rd_pk = fetch_queue.recap_document_id
        fq_date_created = fetch_queue.date_created
        match skip_status.reason:
            case SkipReason.MAX_RETRIES | SkipReason.FAILED:
                # Either exceeded max retries or the fetch is explicitly failed.
                # Remove this from fetches_in_progress.
                self.fetches_in_progress.pop(court_id, None)
                # Also if this is the last document in the court, remove it from
                # remaining_courts as well.
                if not remaining_courts.get(court_id):
                    remaining_courts.pop(court_id, None)
                # Then we store its PK in failed_docs cache.
                append_value_in_cache(
                    self.failed_docs_cache_key(), (rd_pk, fq_pk)
                )
                logger.info(
                    "Max retries reached for RD %s from Court %s. Retry count: %s, fq_failed: %s – removing from fetches_in_progress.",
                    rd_pk,
                    court_id,
                    retry_count,
                    skip_status.reason == SkipReason.FAILED,
                )
                return None

            case SkipReason.FETCH_IN_PROGRESS:
                # As a safeguard: If the FQ hasn't been processed within max_fq_wait,
                # stop waiting to prevent a deadlock for the current court.
                if enough_time_elapsed(fq_date_created, self.max_fq_wait):
                    self.fetches_in_progress[court_id] = (
                        fq_pk,
                        self.max_retries,
                    )
                    logger.info(
                        "Stale FQ %s - Court %s Aborting it.",
                        fq_pk,
                        court_id,
                    )
                    return None

                # If the FQ is still in progress, compare the elapsed time and
                # check if it matches the next backoff interval.
                # If it does, increase the retry count.

                interval_elapsed, exponential_backoff = (
                    is_retry_interval_elapsed(
                        fq_date_created, retry_count, self.initial_backoff_time
                    )
                )
                if interval_elapsed:
                    new_retry_count = retry_count + 1
                    self.fetches_in_progress[court_id] = (
                        fq_pk,
                        new_retry_count,
                    )
                    logger.info(
                        "Court %s: fetch still in progress. Incrementing retry_count to %d.",
                        court_id,
                        new_retry_count,
                    )
                    return exponential_backoff

            case SkipReason.WAITING_INTERVAL:
                logger.info(
                    "Court %s: fetch completed at %s, but waiting for the interval to elapse; skipping for now.",
                    court_id,
                    fetch_queue.date_completed,
                )
                return None

        return None

    def fetch_docs_from_pacer(self) -> None:
        """Process documents with one fetch per court at a time"""
        self.handle_pacer_session()
        remaining_courts = self.courts_with_docs.copy()
        while remaining_courts:
            courts_at_start = len(remaining_courts)
            skipped_courts = 0
            minimum_wait = None
            minimum_wait_round = MinimumWait()
            for court_id in list(remaining_courts.keys()):
                skip_status = self.should_skip(court_id)
                if skip_status.should_skip:
                    skipped_courts += 1
                    exponential_backoff = self.process_skip_reason(
                        court_id, skip_status, remaining_courts
                    )
                    if exponential_backoff:
                        minimum_wait_round.add(exponential_backoff)
                else:
                    self.fetch_next_doc_in_court(court_id, remaining_courts)

                # If this court doesn't have any more docs, remove from dicts:
                self.cleanup_finished_court(court_id, remaining_courts)

            if skipped_courts == courts_at_start:
                # If all courts were skipped in this round, wait for the
                # minimum time returned by any FQ in progress, following the
                # exponential backoff policy, before starting the next iteration.
                # This delay allows pending tasks to complete or be retried
                # before making another attempt.
                minimum_wait = minimum_wait_round.get()
            wait = minimum_wait if minimum_wait else self.interval
            logger.info(
                "%s courts were skipped. Waiting for: %s seconds.",
                skipped_courts,
                wait,
            )
            time.sleep(wait)

    def handle_process_docs(self):
        """Apply tasks to process docs that were successfully fetched from PACER."""
        cached_fetches = cache.get(self.docs_to_process_cache_key(), [])
        fetch_queues_to_process = [fq_pk for (_, fq_pk) in cached_fetches]
        fetch_queues = (
            PacerFetchQueue.objects.filter(pk__in=fetch_queues_to_process)
            .select_related("recap_document")
            .only(
                "pk",
                "status",
                "recap_document__id",
                "recap_document__ocr_status",
                "recap_document__is_available",
                "recap_document__filepath_local",
            )
        )
        total_fq_queues = fetch_queues.count()
        processed_count = 0
        for fq in fetch_queues:
            rd = fq.recap_document
            needs_ocr = rd.needs_extraction
            has_pdf = rd.filepath_local is not None
            fetch_was_successful = fq.status == PROCESSING_STATUS.SUCCESSFUL
            if fetch_was_successful and has_pdf and needs_ocr:
                self.throttle.maybe_wait()
                extract_recap_pdf.si(rd.pk).apply_async(queue=self.queue_name)
                processed_count += 1
                logger.info(
                    "Processed %d/%d (%.0f%%), last document scheduled: %d",
                    processed_count,
                    total_fq_queues,
                    (
                        (processed_count / total_fq_queues) * 100
                        if total_fq_queues
                        else 0
                    ),
                    rd.pk,
                )

    def handle_fetch_docs(self):
        """Run only the fetching stage."""
        logger.info("Starting fetch stage in pacer_bulk_fetch command.")
        self.user = User.objects.get(username=self.options["username"])
        self.identify_documents()
        logger.info(
            "%s found %s documents across %s courts.",
            self.user,
            len(self.recap_documents),
            len(self.courts_with_docs),
        )

        self.fetch_docs_from_pacer()

        logger.info(
            "Created %s processing queues for a total of %s docs found.",
            self.total_launched,
            len(self.recap_documents),
        )
        logger.info(
            "The following PacerFetchQueues did not complete successfully: %s",
            cache.get(self.failed_docs_cache_key(), []),
        )

    def handle(self, *args, **options) -> None:
        self.options = options
        self.setup_celery()
        self.interval = self.options["interval"]
        self.initial_backoff_time = self.options["initial_backoff_time"]
        if self.options.get("testing"):
            self.max_retries = 1
            self.max_fq_wait = 0.001

        stage = options["stage"]
        if stage == "fetch" and options.get("min_page_count") is None:
            raise CommandError(
                "--min-page-count is required for --stage 'fetch'."
            )

        if stage == "fetch":
            self.handle_fetch_docs()
        elif stage == "process":
            self.handle_process_docs()
        else:
            raise CommandError(
                "Invalid stage passed to pacer_bulk_fetch command."
            )
