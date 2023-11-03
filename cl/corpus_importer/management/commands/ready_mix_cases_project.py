import time
from typing import List, TypedDict

from django.core.management import CommandParser  # type: ignore
from redis import Redis
from redis.exceptions import ConnectionError

from cl.corpus_importer.tasks import make_docket_by_iquery
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.redis_utils import make_redis_interface
from cl.search.models import Court, Docket


class OptionsType(TypedDict):
    queue: str
    courts: List[str]
    iterations: int
    iteration_delay: float
    stop_threshold: int
    year: int


def get_bankruptcy_courts(court_ids: list[str]) -> list[str]:
    """Retrieve a list of bankruptcy courts IDS from database.

    :param court_ids: A list of court ids or all.
    :return: A list of Court IDs.
    """
    bankr_courts = (
        Court.federal_courts.bankruptcy_pacer_courts().all().only("pk")
    )
    if court_ids != ["all"]:
        bankr_courts = bankr_courts.filter(pk__in=court_ids)

    return list(bankr_courts.values_list("pk", flat=True))


def get_latest_pacer_case_id(court_id: str, year: int) -> str | None:
    """Fetch the latest pacer_case_id for a specific court and year.

    :param court_id: The court ID.
    :param year: The year for which to find the latest pacer_case_id.
    :return: The latest pacer_case_id if found, otherwise None.
    """

    latest_docket = (
        Docket.objects.filter(
            court_id=court_id,
            date_filed__year=year,
            pacer_case_id__isnull=False,
        )
        .order_by("-date_filed")
        .first()
    )

    if latest_docket:
        return latest_docket.pacer_case_id
    return None


def get_and_store_starting_case_ids(options: OptionsType, r: Redis) -> None:
    """Get the starting pacer_case_id based on the provided year and store it
    in Redis for each court.

    :param options: The options from the handle method
    :param r: The Redis DB to connect to as a connection interface or str that
    can be handed off to make_redis_interface.
    :return None
    """

    court_ids = get_bankruptcy_courts(options["courts"])
    for court_id in court_ids:
        latest_pacer_case_id = get_latest_pacer_case_id(
            court_id, options["year"]
        )
        if not latest_pacer_case_id:
            r.hdel("iquery_status", court_id)
            continue
        r.hset("iquery_status", court_id, latest_pacer_case_id)
    logger.info(f"Finished setting starting pacer_case_ids.")


def query_results_in_es(r):
    """Query results in ES.
    :param r: The Redis DB to connect to as a connection interface or str that
    can be handed off to make_redis_interface.
    :return None
    """
    pass


def add_bank_cases_to_cl(options: OptionsType, r) -> None:
    """Iterate over courts and gather iquery results from them.
    :param options: The options from the handle method
    :param r: The Redis DB to connect to as a connection interface or str that
    can be handed off to make_redis_interface.
    :return None
    """
    q = options["queue"]
    stop_threshold = options["stop_threshold"]
    r = make_redis_interface("CACHE")

    court_ids = get_bankruptcy_courts(options["courts"])
    for court_id in court_ids:
        # Restart empty iquery results to 0.
        r.hset("iquery_empty_results", court_id, 0)

    # Create a queue that's a bit longer than the number of courts we're doing
    throttle = CeleryThrottle(queue_name=q, min_items=len(court_ids) * 2)
    iterations_completed = 0
    while (
        options["iterations"] == 0
        or iterations_completed < options["iterations"]
    ):
        if len(court_ids) == 0:
            # No more courts. Done!
            logger.info("Finished all courts. Exiting!")
            break

        for court_id in court_ids:
            iquery_empty_count = int(r.hget("iquery_empty_results", court_id))
            if iquery_empty_count >= stop_threshold:
                # Abort for consecutive empty results.
                # Stop doing this court.
                court_ids.remove(court_id)
                continue

            throttle.maybe_wait()
            try:
                pacer_case_id = r.hget("iquery_status", court_id)
                if pacer_case_id is None:
                    # Abort, no pacer_case_id found for the given year
                    court_ids.remove(court_id)
                    logger.info(
                        f"Aborting court: {court_id}, no pacer_case_id "
                        f"found in {options['year']}"
                    )
                    continue
                pacer_case_id = r.hincrby("iquery_status", court_id, 1)
                make_docket_by_iquery.apply_async(
                    args=(court_id, pacer_case_id),
                    kwargs={"log_results_redis": True},
                    queue=q,
                )
            except ConnectionError:
                logger.info(
                    "Failed to connect to redis. Waiting a bit and making "
                    "a new connection."
                )
                time.sleep(10)
                r = make_redis_interface("CACHE")
                # Continuing here will skip this court for this iteration; not
                # a huge deal.
                continue
            except Exception as e:
                # Cleanup
                r.hincrby("iquery_status", court_id, -1)
                raise e

        iterations_completed += 1
        remaining_iterations = options["iterations"] - iterations_completed
        if remaining_iterations > 0:
            time.sleep(options["iteration_delay"])


class Command(VerboseCommand):
    help = "Scrape bankruptcy iquery pages sequentially."

    def add_arguments(self, parser: CommandParser):
        parser.add_argument(
            "--queue",
            default="batch2",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--courts",
            type=str,
            default=["all"],
            nargs="*",
            help="The courts that you wish to parse.",
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=0,
            help="The number of iterations to take. Default is 0, which means "
            "to loop forever",
        )
        parser.add_argument(
            "--iteration-delay",
            type=float,
            default=1.0,
            help="How long to wait after completing an iteration of all "
            "courts before beginning another iteration",
        )
        parser.add_argument(
            "--task",
            type=str,
            choices=["scrape-iquery", "set-case-ids", "query-results"],
            help="Which task do you want to do?",
        )
        parser.add_argument(
            "--stop-threshold",
            type=int,
            default=5,
            help="How many empty iquery pages results before stopping the court.",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=2019,
            help="The year to extract the latest case from.",
        )

    def handle(self, *args, **options):
        r = make_redis_interface("CACHE")
        if options["task"] == "scrape-iquery":
            add_bank_cases_to_cl(options, r)

        if options["task"] == "set-case-ids":
            get_and_store_starting_case_ids(options, r)

        if options["task"] == "query-results":
            query_results_in_es(r)
