import logging
import time
from datetime import datetime, timedelta

from celery import chain
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management.base import CommandError
from django.db.models import Q
from django.utils import timezone

from cl import settings
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.pacer_session import get_or_cache_pacer_cookies
from cl.recap.models import PROCESSING_STATUS, REQUEST_TYPE, PacerFetchQueue
from cl.recap.tasks import fetch_pacer_doc_by_rd, mark_fq_successful
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import Court, RECAPDocument

logger = logging.getLogger(__name__)


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
        self.recap_documents = None
        self.courts_with_docs = {}
        self.total_launched = 0
        self.total_errors = 0
        self.max_retries = 5
        self.pacer_username = None
        self.pacer_password = None
        self.throttle = None
        self.queue_name = None
        self.interval = None
        self.docs_to_process_cache_key = "pacer_bulk_fetch.docs_to_process"
        self.timed_out_docs_cache_key = "pacer_bulk_fetch.timed_out_docs"
        self.fetches_in_progress = {}  # {court_id: (fq_pk, retry_count)}

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--interval",
            type=float,
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
            help="Get docs with this number of pages or less",
        )
        parser.add_argument(
            "--username",
            type=str,
            help="Username to associate with the processing queues (defaults to 'recap')",
        )
        parser.add_argument(
            "--queue-name",
            type=str,
            help="Celery queue name used for processing tasks",
        )
        parser.add_argument(
            "--testing",
            type=str,
            help="Prevents creation of log file",
        )
        parser.add_argument(
            "--stage",
            type=str,
            choices=["fetch", "process"],
            default="fetch",
            help="Stage of the command to run: fetch or process",
        )

    @staticmethod
    def setup_logging(testing: bool = False) -> None:
        if not testing:
            logging.basicConfig(
                filename=f'pacer_bulk_fetch_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
                level=logging.INFO,
                format="%(asctime)s - %(levelname)s - %(message)s",
            )

    def setup_celery(self) -> None:
        """Setup Celery by setting the queue_name and throttle."""
        self.queue_name = self.options.get("queue_name", "pacer_bulk_fetch")
        self.throttle = CeleryThrottle(queue_name=self.queue_name)

    def handle_pacer_session(self) -> None:
        """Make sure we have an active PACER session for the user."""
        self.pacer_username = self.options.get(
            "pacer_username", settings.PACER_USERNAME
        )
        self.pacer_password = self.options.get(
            "pacer_password", settings.PACER_PASSWORD
        )
        get_or_cache_pacer_cookies(
            self.user.pk,
            username=self.pacer_username,
            password=self.pacer_password,
        )

    def set_user(self, username: str) -> None:
        """Get user or raise CommandError"""
        if not username:
            raise CommandError(
                "No username provided, cannot create PacerFetchQueues."
            )
        try:
            self.user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User {username} does not exist")

    def identify_documents(self) -> None:
        """Get eligible documents grouped by court"""
        filters = [
            Q(pacer_doc_id__isnull=False),
            Q(is_available=False),
        ]
        if self.options.get("min_page_count"):
            filters.append(Q(page_count__gte=self.options["min_page_count"]))
        if self.options.get("max_page_count"):
            filters.append(Q(page_count__lte=self.options["max_page_count"]))

        # Do not attempt to fetch docs that were already fetched:
        cached_fetches = cache.get(self.docs_to_process_cache_key)
        previously_fetched = [rd_pk for (rd_pk, _) in cached_fetches]
        # Only try again with those that were timed out before:
        cached_timed_out = cache.get(self.timed_out_docs_cache_key)
        previously_timed_out = [rd_pk for (rd_pk, _) in cached_timed_out]
        redundant = set(previously_fetched) - set(previously_timed_out)
        self.recap_documents = (
            RECAPDocument.objects.filter(*filters)
            .exclude(pk__in=redundant)
            .select_related("docket_entry__docket")
            .values(
                "id",
                "page_count",
                "docket_entry__docket__court_id",
                "pacer_doc_id",
            )
            .order_by("-page_count")
        )

        courts = (
            Court.objects.filter(
                dockets__docket_entries__recap_documents__in=[
                    recap_doc_id["id"] for recap_doc_id in self.recap_documents
                ]
            )
            .order_by("pk")
            .distinct()
        )

        for court in courts:
            self.courts_with_docs[court.pk] = [
                doc
                for doc in self.recap_documents
                if doc["docket_entry__docket__court_id"] == court.pk
            ]

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
        fetch_pacer_doc_by_rd.si(rd_pk, fq.pk).apply_async(
            queue=self.queue_name
        )
        append_value_in_cache(self.docs_to_process_cache_key, (rd_pk, fq.pk))
        self.total_launched += 1
        logger.info(
            f"Launched download for doc {doc.get('id')} from court {doc.get('docket_entry__docket__court_id')}"
            f"\nProgress: {self.total_launched}/{len(self.recap_documents)}"
        )
        return fq

    def should_skip(self, court_id: str) -> bool:
        """Determine if the court is ready to be queried again.

        To hit the same court again, the last fetch queue must have
        been completed more than `self.interval` seconds ago.
        """

        def enough_time_elapsed(date):
            now = timezone.now()
            return (now - date) < timedelta(seconds=self.interval)

        if court_id in self.fetches_in_progress:
            fq_pk, retry_count = self.fetches_in_progress[court_id]
            fetch_queue = PacerFetchQueue.objects.get(id=fq_pk)
            rd_pk = fetch_queue.recap_document_id
            if retry_count >= self.max_retries:
                # Too many retries means FQ was probably stuck and not handled gracefully, so we keep going.
                # We remove this FQ from fetches_in_progress as we'll stop checking this one
                self.fetches_in_progress.pop(court_id)
                # Then we store its PK in cache to handle FQs w/too many retries later
                append_value_in_cache(
                    self.timed_out_docs_cache_key, (rd_pk, fq_pk)
                )
                return False

            date_completed = fetch_queue.date_completed
            fq_in_progress = date_completed is None
            if fq_in_progress or not enough_time_elapsed(date_completed):
                return True

        return False

    def update_fetches_in_progress(self, court_id: str, fq_id: int):
        court_last_fetch = self.fetches_in_progress.get(court_id, (fq_id, 0))
        retry_count = court_last_fetch[1]
        if fq_id == court_last_fetch[0]:
            retry_count += 1
        self.fetches_in_progress[court_id] = (fq_id, retry_count)

    def fetch_next_doc_in_court(
        self,
        court_id: str,
        remaining_courts: dict,
    ) -> bool:
        """Pop next doc in court and add fetch task to get it from PACER.

        If the last FQ for the court is still in progress or was completed
        less than `self.interval` seconds ago, we skip it and wait for
        the next round to try the same court again.
        """
        should_skip = self.should_skip(court_id)
        if should_skip:
            return True

        if remaining_courts[court_id]:
            doc = remaining_courts[court_id].pop(0)
            try:
                fq = self.enqueue_pacer_fetch(doc)
                self.update_fetches_in_progress(court_id, fq.id)
            except Exception as e:
                self.total_errors += 1
                logger.error(
                    f"Error queuing document {doc.get('id')}: {str(e)}"
                )

        return False

    def fetch_docs_from_pacer(self) -> None:
        """Process documents with one fetch per court at a time"""
        self.handle_pacer_session()
        remaining_courts = self.courts_with_docs.copy()

        while remaining_courts:
            courts_at_start = len(remaining_courts)
            skipped_courts = 0
            for court_id in list(remaining_courts.keys()):
                was_skipped = self.fetch_next_doc_in_court(
                    court_id,
                    remaining_courts,
                )
                skipped_courts += int(was_skipped)
                # If this court doesn't have any more docs, remove from dict:
                if not remaining_courts[court_id]:
                    remaining_courts.pop(court_id)
                    self.fetches_in_progress.pop(court_id, None)

            # If we had to skip all courts that we tried this round,
            # add a small delay to avoid hammering the DB
            if skipped_courts == courts_at_start:
                time.sleep(self.interval)

    def process_docs_fetched(self):
        """Apply tasks to process docs that were successfully fetched from PACER."""
        cached_fetches = cache.get(self.docs_to_process_cache_key)
        fetch_queues_to_process = [fq_pk for (_, fq_pk) in cached_fetches]
        fetch_queues = (
            PacerFetchQueue.objects.filter(pk__in=fetch_queues_to_process)
            .select_related("recap_document")
            .only(
                "pk",
                "status",
                "recap_document__pk",
                "recap_document__needs_extraction",
                "recap_document__filepath_local",
            )
        )
        for fq in fetch_queues:
            rd = fq.recap_document
            needs_ocr = rd.needs_extraction
            has_pdf = rd.filepath_local is not None
            fetch_was_successful = fq.status == PROCESSING_STATUS.SUCCESSFUL
            if fetch_was_successful and has_pdf and needs_ocr:
                self.throttle.maybe_wait()
                chain(
                    extract_recap_pdf.si(rd.pk),
                    mark_fq_successful.si(fq.pk),
                ).apply_async(queue=self.queue_name)

    def handle_fetch_docs(self):
        """Run only the fetching stage."""
        logger.info("Starting fetch stage in pacer_bulk_fetch command.")
        try:
            self.set_user(self.options.get("username", "recap"))
            self.identify_documents()
            logger.info(
                f"{self.user} found {len(self.recap_documents)} documents "
                f"across {len(self.courts_with_docs)} courts."
            )

            self.fetch_docs_from_pacer()

            logger.info(
                f"Created {self.total_launched} processing queues for a total "
                f"of {len(self.recap_documents)} docs found."
            )
            logger.info(
                f"The following PacerFetchQueues were retried too many times: "
                f"{cache.get(self.timed_out_docs_cache_key)}"
            )
        except Exception as e:
            logger.error(
                f"Fatal error in fetch stage: {str(e)}", exc_info=True
            )
            raise e

    def handle_process_docs(self):
        """Run only the processing stage."""
        logger.info("Starting processing stage in pacer_bulk_fetch command.")
        try:
            self.process_docs_fetched()
        except Exception as e:
            logger.error(
                f"Fatal error in process stage: {str(e)}", exc_info=True
            )
            raise e

    def handle(self, *args, **options) -> None:
        self.options = options
        self.setup_logging(self.options.get("testing", False))
        self.setup_celery()
        self.interval = self.options.get("interval", 2)

        stage = options.get("stage")
        if stage == "fetch":
            self.handle_fetch_docs()
        elif stage == "process":
            self.handle_process_docs()
        else:
            raise CommandError(
                "Invalid stage passed to pacer_bulk_fetch command."
            )
