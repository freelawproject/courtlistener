import logging
import time

from django.conf import settings
from redis import ConnectionError

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.redis_utils import get_redis_interface
from cl.search.docket_number_cleaner import llm_clean_docket_numbers

logger = logging.getLogger(__name__)


class Command(VerboseCommand):
    help = """Run the docket number cleaning daemon.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = {}

    def add_arguments(self, parser):
        parser.add_argument(
            "--testing-iterations",
            type=int,
            default="0",
            required=False,
            help="The number of iterations to run on testing mode.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        testing_iterations = options["testing_iterations"]
        iterations_completed = 0
        testing = True if testing_iterations else False

        r = get_redis_interface("CACHE")
        redis_key = "docket_number_cleaning:llm_batch"

        while True and settings.DOCKET_NUMBER_CLEANING_ENABLED:
            # Use a Redis lock to avoid race conditions when getting and updating the llm_batch.
            try:
                llm_batch = r.smembers(redis_key)
                if llm_batch:
                    processed_ids = llm_clean_docket_numbers(llm_batch)
                    r.srem(redis_key, *processed_ids)
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
