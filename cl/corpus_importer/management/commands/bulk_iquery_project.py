import time
from typing import Dict, Union, List

from django.core.management import CommandParser

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.corpus_importer.tasks import (
    make_docket_by_iquery,
)
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
    throttle = CeleryThrottle(queue_name=q)
    r = make_redis_interface("CACHE")

    courts = Court.federal_courts.district_pacer_courts()
    if options["courts"] != ["all"]:
        courts = courts.filter(pk__in=options["courts"])

    iterations_completed = 0
    while (
        options["iterations"] == 0
        or iterations_completed < options["iterations"]
    ):
        for court in courts:
            throttle.maybe_wait()
            try:
                pacer_case_id = r.hincrby("iquery_status", court.pk, 1)
                make_docket_by_iquery.apply_async(
                    args=(court.pk, pacer_case_id),
                    queue=q,
                )
            finally:
                # Cleanup
                r.hincrby("iquery_status", court.pk, -1)

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
