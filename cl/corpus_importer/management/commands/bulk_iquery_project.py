import itertools
import time
from collections import defaultdict
from typing import List, TypedDict

from django.conf import settings
from django.core.management import CommandParser  # type: ignore
from django.db.models import F, Window
from django.db.models.functions import RowNumber
from redis.exceptions import ConnectionError

from cl.corpus_importer.tasks import make_docket_by_iquery
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.redis_utils import get_redis_interface
from cl.scrapers.tasks import update_docket_info_iquery
from cl.search.models import Court, Docket


class OptionsType(TypedDict):
    queue: str
    courts: List[str]
    iterations: int
    iteration_delay: float


def add_all_cases_to_cl(options: OptionsType) -> None:
    """Iterate over courts and gather iquery results from them.

    :param options: The options from the handle method
    :return None
    """
    q = options["queue"]
    r = get_redis_interface("CACHE")
    # This is a simple dictionary that's populated with the maximum
    # pacer_case_id in the CL DB as of 2021-01-18. The idea is to use this to
    # prevent the scraper from going forever. You can reset it by querying the
    # latest item in the DB by date_filed, and then using r.hmset to save it.
    max_ids = r.hgetall("iquery_max_ids")

    courts = Court.federal_courts.district_pacer_courts().exclude(
        pk__in=["uscfc", "arb", "cit"]
    )
    if options["courts"] != ["all"]:
        courts = courts.filter(pk__in=options["courts"])
    court_ids = list(courts.values_list("pk", flat=True))

    # Create a queue that's a bit longer than the number of courts we're doing
    throttle = CeleryThrottle(queue_name=q, min_items=len(court_ids) * 2)

    iterations_completed = 0
    db_key_cycle = itertools.cycle(settings.DATABASES.keys())
    while (
        options["iterations"] == 0
        or iterations_completed < options["iterations"]
    ):
        if len(court_ids) == 0:
            # No more courts. Done!
            print("Finished all courts. Exiting!")
            break

        for court_id in court_ids:
            throttle.maybe_wait()
            try:
                pacer_case_id = r.hincrby("iquery_status", court_id, 1)
                if pacer_case_id > int(max_ids[court_id]):
                    # Enough scraping. Stop doing this court.
                    court_ids.remove(court_id)
                    continue
                make_docket_by_iquery.apply_async(
                    args=(court_id, pacer_case_id, next(db_key_cycle)),
                    queue=q,
                )
            except ConnectionError:
                print(
                    "Failed to connect to redis. Waiting a bit and making "
                    "a new connection."
                )
                time.sleep(10)
                r = get_redis_interface("CACHE")
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


class CycleChecker:
    """Keep track of a cycling list to determine each time it starts over.

    We plan to iterate over dockets that are ordered by a cycling court ID, so
    imagine if we had two courts, ca1 and ca2, we'd have rows like:

        docket: 1, court: ca1
        docket: 14, court: ca2
        docket: 15, court: ca1
        docket: xx, court: ca2

    In other words, they'd just go back and forth. In reality, we have about
    200 courts, but the idea is the same. This code lets us detect each time
    the cycle has started over, even if courts stop being part of the cycle,
    as will happen towards the end of the queryset.. For example, maybe ca1
    finishes, and now we just have:

        docket: x, court: ca2
        docket: y, court: ca2
        docket: z, court: ca2

    That's considered cycling each time we get to a new row.

    The way to use this is to just create an instance and then send it a
    cycling list of court_id's.

    Other fun requirements this hits:
     - No need to know the length of the cycle
     - No need to externally track the iteration count
    """

    def __init__(self) -> None:
        self.court_counts: defaultdict = defaultdict(int)
        self.current_iteration: int = 1

    def check_if_cycled(self, court_id: str) -> bool:
        """Check if the cycle repeated

        :param court_id: The ID of the court
        :return True if the cycle started over, else False
        """
        self.court_counts[court_id] += 1
        if self.court_counts[court_id] == self.current_iteration:
            return False
        else:
            # Finished cycle and court has been seen more times than the
            # iteration count. Bump the iteration count and return True.
            self.current_iteration += 1
            return True


def update_open_cases(options) -> None:
    """Update any cases that are in our system and not terminated."""
    # This is a very fancy query that fetches the results while cycling over
    # the court_id field. This way, we can do one hit per court per some
    # schedule. It should help us avoid getting banned. Hopefully!
    q = options["queue"]
    courts = Court.federal_courts.district_pacer_courts().exclude(
        pk__in=["uscfc", "arb", "cit", "jpml"]
    )
    ds = (
        Docket.objects.filter(
            source__in=Docket.RECAP_SOURCES,
            date_terminated=None,
            court__in=courts,
            pacer_case_id__isnull=False,
        )
        .exclude(
            date_modified__gt="2022-08-13T17:30:00-0800",
        )
        .annotate(
            row_number=Window(
                expression=RowNumber(),
                partition_by=[F("court_id")],
                order_by=F("pk").asc(),
            )
        )
        .order_by("row_number", "court_id")
        .only("pk", "pacer_case_id", "court_id")
        .iterator()
    )
    cc = CycleChecker()
    iterations_completed = 0
    for d in ds:
        if iterations_completed < options["skip_rows"]:
            iterations_completed += 1
            continue

        # Dispatch a crawl against all court websites simultaneously, every
        # iteration_delay seconds.
        if cc.check_if_cycled(d.court_id):
            print(
                f"Finished iteration {iterations_completed} on docket with id "
                f"{d.pk}. Sleeping {options['iteration_delay']} seconds."
            )
            time.sleep(options["iteration_delay"])

        update_docket_info_iquery.apply_async(args=(d.pk, d.court_id), queue=q)

        iterations_completed += 1
        if iterations_completed == options["iterations"]:
            print("Finished iterating. Quitting.")
            break


class Command(VerboseCommand):
    help = "Scrape all iquery pages sequentially."

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
            choices=["everything", "byu-project"],
            help="Which task do you want to do?",
        )
        parser.add_argument(
            "--skip-rows",
            type=int,
            default=0,
            help="How many rows to skip before doing work?",
        )

    def handle(self, *args, **options):
        if options["task"] == "everything":
            add_all_cases_to_cl(options)
        elif options["task"] == "byu-project":
            update_open_cases(options)
