import time

from django.conf import settings
from redis import ConnectionError, Redis

from cl.corpus_importer.tasks import (
    iquery_pages_probing,
    make_docket_by_iquery,
    make_iquery_probing_key,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.redis_utils import create_redis_semaphore, get_redis_interface
from cl.search.models import Court, Docket


def enqueue_iquery_binary_search(court_id: str) -> bool:
    """Get iquery forward probing semaphore.

    :param court_id: The identifier for the court.
    :return: A boolean indicating if the semaphore was successfully created.
    """
    key = make_iquery_probing_key(court_id)
    return create_redis_semaphore("CACHE", key, ttl=60 * 10)


def get_all_pacer_courts() -> list[str]:
    """Retrieve all district and bankruptcy  PACER courts from the database.

    :return: A list of Court IDs.
    """
    courts = (
        Court.federal_courts.district_or_bankruptcy_pacer_courts().exclude(
            pk__in=["uscfc", "arb", "cit"]
        )
    )
    return list(courts.values_list("pk", flat=True))


def get_latest_pacer_case_id(court_id: str) -> int:
    """Fetch the latest pacer_case_id from DB for a specific court.

    :param court_id: The court ID.
    :return: The latest pacer_case_id if found, otherwise None.
    """
    latest_docket = Docket.objects.filter(
        court_id=court_id, pacer_case_id__isnull=False
    ).latest("pacer_case_id")
    if latest_docket:
        return int(latest_docket.pacer_case_id)
    return 0


def update_pacer_case_id_final(court_id: str, r: Redis) -> int:
    """Update the final pacer_case_id for a court and store in Redis.

    :param court_id: The court ID.
    :param r: The Redis instance.
    :return: The latest pacer_case_id_final.
    """

    latest_pacer_case_id = get_latest_pacer_case_id(court_id)
    if latest_pacer_case_id:
        r.hset("pacer_case_id_final", court_id, latest_pacer_case_id)
        logger.info(
            f"Updated pacer_case_id_final for court {court_id} to {latest_pacer_case_id}"
        )
    return latest_pacer_case_id


def process_court(court_id: str, r: Redis) -> None:
    """Process a single court, handling the PACER case IDs and making docket requests.

    :param court_id: The court ID.
    :param r: The Redis instance.
    """

    pacer_case_id_init = int(r.hget("pacer_case_id_init", court_id) or 0)
    pacer_case_id_final = int(r.hget("pacer_case_id_final", court_id) or 0)
    if pacer_case_id_init >= pacer_case_id_final:
        # pacer_case_id_init has reached pacer_case_id_final, try to get a
        # higher watermark from the DB
        pacer_case_id_final = update_pacer_case_id_final(court_id, r)
        if pacer_case_id_final and pacer_case_id_final > pacer_case_id_init:
            r.hset("pacer_case_id_final", court_id, pacer_case_id_final)
            return
        else:
            # It was not possible to get a higher watermark from the DB.
            # Try to obtain it by probing using binary search.
            newly_enqueued = enqueue_iquery_binary_search(court_id)
            if newly_enqueued:
                # No other binary search is being conducted for the court. Enqueue it.
                iquery_pages_probing.delay(court_id)

            # Create a court limiter with 1 minute expiration.
            r.setex(
                f"court_limiter:{court_id}",
                settings.IQUERY_SCRAPER_LONG_WAIT,
                1,
            )
            return

    # pacer_case_id_init has not reached pacer_case_id_final, increase +1 and
    # continue the scrape.
    pacer_case_id_init = r.hincrby("pacer_case_id_init", court_id, 1)
    make_docket_by_iquery.apply_async(
        args=(court_id, pacer_case_id_init), queue=settings.CELERY_IQUERY_QUEUE
    )
    logger.info(
        f"Enqueued task for court {court_id} with pacer_case_id {pacer_case_id_init}"
    )

    if pacer_case_id_init >= pacer_case_id_final:
        # If after increasing pacer_case_id_init it has reached pacer_case_id_final
        # Wait for IQUERY_SCRAPER_LONG_WAIT seconds before doing a new
        # iteration for the court.
        r.setex(
            f"court_limiter:{court_id}", settings.IQUERY_SCRAPER_LONG_WAIT, 1
        )
    else:
        # Otherwise, only wait for IQUERY_SCRAPER_SHORT_WAIT seconds to keep
        # the court scraping rate under control.
        r.setex(
            f"court_limiter:{court_id}", settings.IQUERY_SCRAPER_SHORT_WAIT, 1
        )


class Command(VerboseCommand):
    help = "Run the iquery scraper daemon."

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
        r = get_redis_interface("CACHE")
        # If a new court is added to the DB. We should restart the daemon.
        courts = get_all_pacer_courts()
        iterations_completed = 0
        while True:
            for court_id in courts:
                if r.exists(f"court_limiter:{court_id}"):
                    continue
                try:
                    process_court(court_id, r)
                except ConnectionError:
                    logger.info(
                        "Failed to connect to redis. Waiting a bit and making "
                        "a new connection."
                    )
                    time.sleep(10)
                    r = get_redis_interface("CACHE")
                    # Continuing here will skip this court for this iteration; not
                    # a huge deal.
                    continue

                if testing_iterations:
                    # Avoid waiting in testing mode.
                    r.delete(f"court_limiter:{court_id}")

            if testing_iterations:
                iterations_completed += 1
            if (
                testing_iterations
                and iterations_completed >= testing_iterations
            ):
                # Perform only the indicated iterations for testing purposes.
                break
