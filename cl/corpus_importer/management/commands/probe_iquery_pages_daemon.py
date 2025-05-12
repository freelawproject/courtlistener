import time

from django.conf import settings
from redis import ConnectionError

from cl.corpus_importer.tasks import probe_or_scrape_iquery_pages
from cl.corpus_importer.utils import (
    get_iquery_pacer_courts_to_scrape,
    make_iquery_probing_key,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.redis_utils import create_redis_semaphore, get_redis_interface


def enqueue_iquery_probe(court_id: str) -> bool:
    """Get iquery forward probing semaphore.

    :param court_id: The identifier for the court.
    :return: A boolean indicating if the semaphore was successfully created.
    """
    key = make_iquery_probing_key(court_id)
    return create_redis_semaphore("CACHE", key, ttl=60 * 10)


def get_latest_pacer_case_id_for_courts(court_ids: list[str], r) -> dict:
    """Return the latest pacer_case_id for each given court from Redis.

    :param court_ids: List of court IDs to fetch the latest pacer_case_id for.
    :param r: The redis connection to use.
    :return: A dict mapping each court_id to its latest pacer_case_id.
    """
    latest_case_ids = {}
    for court_id in court_ids:
        latest_known_pacer_case_id = r.hget(
            "iquery:latest_known_pacer_case_id", court_id
        )
        if latest_known_pacer_case_id:
            latest_case_ids[court_id] = int(latest_known_pacer_case_id)
    return latest_case_ids


class Command(VerboseCommand):
    help = """Run the iquery pages probing daemon.

The goal of this daemon is to ensure that we always have every case in PACER.

It works by taking the highest pacer_case_id we know as of the last iteration,
and then doing geometric probing of higher numbers to discover the highest
current pacer_case_id in each court.

For example, if the highest ID we know about as of 12:00PT is 1000, we would
check ID 1002, then 1004, 1008, 1016, etc., until we stop finding valid cases.
Because cases can be sealed, deleted, etc, we also add jitter to the IDs we
select, to ensure that we don't get stuck due to bad luck.

Once the highest value is found, we schedule iquery download tasks one second
apart to fill in the missing section. For example, if we start at ID 1000, then
learn that ID 1032 is the highest, we'd create 31 celery tasks for items 1000
to 1032, and we'd schedule them over the next 31 seconds.

The last piece of this system is that we have content coming in from a lot of
sources all the time, so we use signals to backfill missing content as well.
For example, if we think 1,000 is the highest ID, and somebody RECAPs a docket
with ID of 1032, the signal will catch that and create tasks to fill in numbers
1001 to 1031.
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
        # If a new court is added to the DB. We should restart the daemon.
        court_ids = get_iquery_pacer_courts_to_scrape()
        iterations_completed = 0
        r = get_redis_interface("CACHE")
        testing = True if testing_iterations else False
        latest_case_ids = get_latest_pacer_case_id_for_courts(court_ids, r)

        while True and settings.IQUERY_CASE_PROBE_DAEMON_ENABLED:
            for court_id in court_ids:
                wait_key = f"iquery:court_wait:{court_id}"
                if r.exists(wait_key):
                    ttl = r.ttl(wait_key)
                    logger.info(
                        "Skipping court %s for %s hours.",
                        court_id,
                        round(ttl / 3600, 2),
                    )
                    continue
                try:
                    newly_enqueued = enqueue_iquery_probe(court_id)
                    if newly_enqueued:
                        # No other probing being conducted for the court.
                        # Enqueue it.
                        latest_know_case_id_db = latest_case_ids.get(court_id)
                        probe_or_scrape_iquery_pages.apply_async(
                            args=(court_id, latest_know_case_id_db, testing),
                            queue=settings.CELERY_IQUERY_QUEUE,
                        )
                        logger.info(
                            "Enqueued iquery probing for court %s", court_id
                        )
                except ConnectionError:
                    logger.info(
                        "Failed to connect to redis. Waiting a bit and making "
                        "a new connection."
                    )
                    time.sleep(10)
                    # Continuing here will skip this court for this iteration; not
                    # a huge deal.
                    continue

                if not testing_iterations:
                    # Avoid waiting in testing mode.
                    time.sleep(settings.IQUERY_PROBE_WAIT / len(court_ids))

            if testing_iterations:
                iterations_completed += 1
            if (
                testing_iterations
                and iterations_completed >= testing_iterations
            ):
                # Perform only the indicated iterations for testing purposes.
                break
