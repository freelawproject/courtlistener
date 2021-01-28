import itertools
import time
from typing import Dict, List, Union

from django.conf import settings
from django.core.management import CommandParser

from cl.corpus_importer.tasks import make_docket_by_iquery
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.redis_utils import make_redis_interface
from cl.search.models import Court


def add_all_cases_to_cl(
    options: Dict[str, Union[List[str], int, str, float]],
) -> None:
    """Iterate over courts and gather iquery results from them.

    :param options: The options from the handle method
    :return None
    """
    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q, min_items=500)
    r = make_redis_interface("CACHE")
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

    iterations_completed = 0
    db_key_cycle = itertools.cycle(settings.DATABASES.keys())
    while (
        options["iterations"] == 0
        or iterations_completed < options["iterations"]
    ):
        if len(court_ids) == 0:
            # No more courts. Done!
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
            except Exception as e:
                # Cleanup
                r.hincrby("iquery_status", court_id, -1)
                raise e

        iterations_completed += 1
        remaining_iterations = options["iterations"] - iterations_completed
        if remaining_iterations > 0:
            time.sleep(options["iteration_delay"])


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

    def handle(self, *args, **options):
        add_all_cases_to_cl(options)
