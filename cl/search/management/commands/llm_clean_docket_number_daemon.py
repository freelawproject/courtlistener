import logging
import time
from datetime import datetime

from django.conf import settings
from django.utils import timezone
from redis import ConnectionError

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.redis_utils import get_redis_interface
from cl.search.docket_number_cleaner import (
    create_llm_court_batches,
    get_redis_key,
)
from cl.search.tasks import clean_docket_number_by_court

logger = logging.getLogger(__name__)


class Command(VerboseCommand):
    help = """Run the docket number cleaning daemon."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.throttle = None

    def add_arguments(self, parser):
        parser.add_argument(
            "--testing-iterations",
            type=int,
            default="0",
            required=False,
            help="The number of iterations to run on testing mode.",
        )
        parser.add_argument(
            "--celery-queue",
            type=str,
            default="batch2",
            help="Which celery queue to use for cleaning.",
        )
        parser.add_argument(
            "--throttle-min-items",
            type=int,
            default=5,
            help="The celery throttle min items.",
        )

    def ll_clean_docket_number(
        self,
        celery_queue: str,
        court_batch: list[dict[int, str]],
        court_mapping: str,
        start_timestamp: datetime,
    ) -> None:
        """
        Processes a batch of court data for LLM cleaning by using one Celery task per court_mapping.

        :param celery_queue: The name of the Celery queue to use for task dispatch.
        :param court_batch: A batch of court records with docket IDs and numbers.
        :param court_mapping: Identifier for the court mapping.
        :param start_timestamp: Timestamp marking the start of the daemon job.
        """
        self.throttle.maybe_wait()
        clean_docket_number_by_court.apply_async(
            args=(court_batch, court_mapping, start_timestamp),
            queue=celery_queue,
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        celery_queue = options["celery_queue"]
        min_items = options["throttle_min_items"]
        self.throttle = CeleryThrottle(
            queue_name=celery_queue, min_items=min_items
        )

        testing_iterations = options["testing_iterations"]
        iterations_completed = 0

        r = get_redis_interface("CACHE")
        redis_key = get_redis_key()

        while True and settings.DOCKET_NUMBER_CLEANING_ENABLED:
            try:
                llm_batch = r.smembers(redis_key)
                llm_batch = [
                    int(item) for item in llm_batch
                ]  # cast docket_id to int
                if llm_batch:
                    start_timestamp = timezone.now()
                    court_batches = create_llm_court_batches(llm_batch)
                    for court_mapping, court_batch in court_batches.items():
                        self.ll_clean_docket_number(
                            celery_queue,
                            court_batch,
                            court_mapping,
                            start_timestamp,
                        )
            except ConnectionError:
                logger.info(
                    "Failed to connect to redis. Waiting a bit and making "
                    "a new connection."
                )
                time.sleep(10)
                # Continuing here will skip this iteration; not a huge deal.
                continue

            if not testing_iterations:
                # Avoid waiting in testing mode.
                time.sleep(settings.DOCKET_NUMBER_CLEANING_WAIT_TIME)

            if testing_iterations:
                iterations_completed += 1
            if (
                testing_iterations
                and iterations_completed >= testing_iterations
            ):
                # Perform only the indicated iterations for testing purposes.
                break
