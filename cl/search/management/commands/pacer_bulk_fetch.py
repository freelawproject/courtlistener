import logging
from datetime import datetime

from django.contrib.auth.models import User
from django.core.management.base import CommandError
from django.db.models import Q

from cl import settings
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.pacer_session import get_or_cache_pacer_cookies
from cl.recap.models import REQUEST_TYPE, PacerFetchQueue
from cl.recap.tasks import build_pdf_retrieval_task_chain
from cl.search.models import Court, RECAPDocument

logger = logging.getLogger(__name__)


class Command(VerboseCommand):
    help = "Download multiple documents from PACER with rate limiting"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.recap_documents = None
        self.courts_with_docs = {}
        self.total_launched = 0
        self.total_errors = 0
        self.pacer_username = None
        self.pacer_password = None
        self.throttle = None
        self.queue_name = None
        self.rate_limit = None

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--rate-limit",
            type=float,
            help="The maximum rate for requests, e.g. '1/m', or '10/2h' or similar. Defaults to 1/2s",
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

    @staticmethod
    def setup_logging(testing: bool = False) -> None:
        if not testing:
            logging.basicConfig(
                filename=f'pacer_bulk_fetch_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
                level=logging.INFO,
                format="%(asctime)s - %(levelname)s - %(message)s",
            )

    def setup_celery(self, options) -> None:
        """Setup Celery by setting the queue_name, rate_limit and throttle."""
        self.queue_name = options.get("queue_name", "pacer_bulk_fetch")
        self.rate_limit = options.get("rate_limit", "1/2s")
        self.throttle = CeleryThrottle(queue_name=self.queue_name)

    def handle_pacer_session(self, options) -> None:
        """Make sure we have an active PACER session for the user."""
        self.pacer_username = options.get(
            "pacer_username", settings.PACER_USERNAME
        )
        self.pacer_password = options.get(
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

    def identify_documents(self, options: dict) -> None:
        """Get eligible documents grouped by court"""
        filters = [
            Q(pacer_doc_id__isnull=False),
            Q(is_available=False),
        ]
        if options.get("min_page_count"):
            filters.append(Q(page_count__gte=options["min_page_count"]))
        if options.get("max_page_count"):
            filters.append(Q(page_count__lte=options["max_page_count"]))

        self.recap_documents = (
            RECAPDocument.objects.filter(*filters)
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

    def enqueue_pacer_fetch(self, doc: dict) -> None:
        self.throttle.maybe_wait()

        fq = PacerFetchQueue.objects.create(
            request_type=REQUEST_TYPE.PDF,
            recap_document_id=doc.get("id"),
            user_id=self.user.pk,
        )
        build_pdf_retrieval_task_chain(
            fq,
            rate_limit=self.rate_limit,
        ).apply_async(queue=self.queue_name)
        self.total_launched += 1
        logger.info(
            f"Launched download for doc {doc.get('id')} from court {doc.get('docket_entry__docket__court_id')}"
            f"\nProgress: {self.total_launched}/{len(self.recap_documents)}"
        )

    def execute_round(
        self, remaining_courts: dict, options: dict, is_last_round: bool
    ) -> dict:
        remaining_courts_copy = (
            remaining_courts.copy()
        )  # don't remove elements from list we're iterating over
        court_keys = remaining_courts.keys()
        for court_index, court_id in enumerate(court_keys):
            doc = remaining_courts[court_id].pop(0)

            try:
                self.enqueue_pacer_fetch(doc)
            except Exception as e:
                self.total_errors += 1
                logger.error(
                    f"Error queuing document {doc.get("id")}: {str(e)}",
                    exc_info=True,
                )
            finally:
                # If this court doesn't have any more docs, remove from dict:
                if len(remaining_courts[court_id]) == 0:
                    remaining_courts_copy.pop(court_id)

        return remaining_courts_copy

    def process_documents(self, options: dict) -> None:
        """Process documents in round-robin fashion by court"""
        remaining_courts = self.courts_with_docs
        court_doc_counts = [
            len(self.courts_with_docs[court_id])
            for court_id in self.courts_with_docs.keys()
        ]
        rounds = max(court_doc_counts)

        for i in range(rounds):
            is_last_round = i == rounds - 1
            remaining_courts = self.execute_round(
                remaining_courts, options, is_last_round
            )

        if self.total_errors:
            logger.error(
                f"Finished processing with {self.total_errors} error{"s" if self.total_errors > 1 else ""}."
            )

    def handle(self, *args, **options) -> None:
        self.setup_logging(options.get("testing", False))
        self.setup_celery(options)

        logger.info("Starting pacer_bulk_fetch command")

        try:
            self.set_user(options.get("username", "recap"))
            self.handle_pacer_session(options)

            self.identify_documents(options)

            logger.info(
                f"{self.user} found {len(self.recap_documents)} documents across {len(self.courts_with_docs)} courts."
            )

            self.process_documents(options)

            logger.info(
                f"Created {self.total_launched} processing queues for a total of {len(self.recap_documents)} docs found."
            )

        except Exception as e:
            logger.error(f"Fatal error in command: {str(e)}", exc_info=True)
            raise
