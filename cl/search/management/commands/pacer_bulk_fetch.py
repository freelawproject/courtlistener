import os
import time
from datetime import datetime, timedelta
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
from cl.recap.models import PROCESSING_STATUS, REQUEST_TYPE, PacerFetchQueue
from cl.recap.tasks import fetch_pacer_doc_by_rd_and_mark_fq_completed
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import Court, RECAPDocument


def append_value_in_cache(key, value):
    cached_docs = cache.get(key)
    if cached_docs is None:
        cached_docs = []
    cached_docs.append(value)
    one_month = 60 * 60 * 24 * 7 * 4
    cache.set(key, cached_docs, timeout=one_month)


class Command(VerboseCommand):
    help = "Download multiple documents from PACER with rate limiting"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = None
        self.user = None
        self.recap_documents = []
        self.courts_with_docs = {}
        self.total_launched = 0
        self.max_retries = 5
        self.pacer_username = os.environ.get(
            "PACER_USERNAME", settings.PACER_USERNAME
        )
        self.pacer_password = os.environ.get(
            "PACER_PASSWORD", settings.PACER_PASSWORD
        )
        self.throttle = None
        self.queue_name = None
        self.interval = None
        self.fetches_in_progress = {}  # {court_id: (fq_pk, retry_count)}

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--interval",
            type=float,
            default=2,
            help="The minimum wait in secs between PACER fetches to the same court.",
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

    def enough_time_elapsed(self, date_completed: datetime) -> bool:
        """Check if enough time has elapsed since task has been completed.

        :param date_completed: The date_completed to compare against the
        current time.
        :return: True if the difference between now and the given date exceeds
        the defined interval, otherwise False.
        """
        now = timezone.now()
        return (now - date_completed) > timedelta(seconds=self.interval)

    def should_skip(
        self, court_id: str, remaining_courts: dict[str, list[dict[str, Any]]]
    ) -> bool:
        """Determine if the court is ready to be queried again.

        To hit the same court again, the last fetch queue must have
        been completed more than `self.interval` seconds ago.
        """
        fetch_in_progress_court = self.fetches_in_progress.get(court_id)
        if not fetch_in_progress_court:
            return False

        fq_pk, retry_count = fetch_in_progress_court
        fetch_queue = PacerFetchQueue.objects.get(id=fq_pk)
        fq_failed = fetch_queue.status in [
            PROCESSING_STATUS.FAILED,
            PROCESSING_STATUS.INVALID_CONTENT,
            PROCESSING_STATUS.NEEDS_INFO,
        ]
        rd_pk = fetch_queue.recap_document_id
        if retry_count >= self.max_retries or fq_failed:
            # Either exceeded max retries or the fetch is explicitly failed.
            # Remove this from fetches_in_progress.
            self.fetches_in_progress.pop(court_id, None)
            # Also if this is the last document in the court, remove it from
            # remaining_courts as well.
            if not remaining_courts.get(court_id):
                remaining_courts.pop(court_id, None)
            # Then we store its PK in failed_docs cache to handle later.
            append_value_in_cache(self.failed_docs_cache_key(), (rd_pk, fq_pk))
            return False

        date_completed = fetch_queue.date_completed
        # If the fetch is still in progress, update retry count and skip.
        if date_completed is None:
            self.fetches_in_progress[court_id] = (fq_pk, retry_count + 1)
            return True

        if not self.enough_time_elapsed(date_completed):
            #  IF FQ has been completed but not enough time has elapsed, wait
            #  by skipping it for now.
            return True

        return False

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
        """
        fetch_in_progress = self.fetches_in_progress.get(court_id)
        if not remaining_courts.get(court_id) and fetch_in_progress:
            fq_pk, _ = fetch_in_progress
            fetch_queue = PacerFetchQueue.objects.get(id=fq_pk)
            # Only clean up if the FQ is completed
            if fetch_queue.date_completed:
                remaining_courts.pop(court_id, None)
                self.fetches_in_progress.pop(court_id, None)

    def fetch_docs_from_pacer(self) -> None:
        """Process documents with one fetch per court at a time"""
        self.handle_pacer_session()
        remaining_courts = self.courts_with_docs.copy()
        while remaining_courts:
            courts_at_start = len(remaining_courts)
            skipped_courts = 0
            for court_id in list(remaining_courts.keys()):
                if self.should_skip(court_id, remaining_courts):
                    skipped_courts += 1
                else:
                    self.fetch_next_doc_in_court(court_id, remaining_courts)

                # If this court doesn't have any more docs, remove from dicts:
                self.cleanup_finished_court(court_id, remaining_courts)

            # If we had to skip all courts that we tried this round,
            # add a small delay to avoid hammering the DB
            if skipped_courts == courts_at_start:
                time.sleep(self.interval)

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
        if self.options.get("testing"):
            self.max_retries = 1

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
