# !/usr/bin/python
# -*- coding: utf-8 -*-
import time
from functools import lru_cache

from asgiref.sync import async_to_sync
from django.db.models import Q

from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.lookup_utils import lookup_judge_by_full_name
from cl.people_db.models import Person
from cl.search.models import Docket


@lru_cache(maxsize=30_000)
def cached_lookup_judge_by_full_name(
    full_name: str, court_id: int, date_filed: str
) -> Person | None:
    """Fetch a judge by full name with LRU caching. Store 30,000 judge lookups.

    :param full_name: The full name of the judge.
    :param court_id: The ID of the court.
    :param date_filed: The date the case was filed.
    :return: A Person object if the judge is found, otherwise None.
    """
    return async_to_sync(lookup_judge_by_full_name)(
        full_name, court_id, date_filed
    )


def find_and_fix_docket_judges(
    iteration_wait: float, testing_mode: bool
) -> None:
    """Find and fix Dockets referred_to and assigned_to judges.

    :param iteration_wait: A float that indicates the time to wait between iterations.
    :param testing_mode: True if testing mode is enabled to avoid wait between
    iterations.
    :return: None
    """

    logger.info("Finding dockets with judges.")
    dockets_with_judges = Docket.objects.filter(
        Q(referred_to__isnull=False) | Q(assigned_to__isnull=False)
    )
    total_dockets = dockets_with_judges.count()
    logger.info(f"Total dockets to process: {total_dockets}")

    fixed_dockets = 0
    for iteration, d in enumerate(dockets_with_judges.iterator(), start=1):
        new_referred = (
            cached_lookup_judge_by_full_name(
                d.referred_to_str, d.court_id, d.date_filed
            )
            if d.referred_to_str
            else None
        )
        new_assigned = (
            cached_lookup_judge_by_full_name(
                d.assigned_to_str, d.court_id, d.date_filed
            )
            if d.assigned_to_str
            else None
        )

        if d.referred_to != new_referred or d.assigned_to != new_assigned:
            logger.info("Fixing Docket with ID %s", d.pk)
            d.referred_to = new_referred
            d.assigned_to = new_assigned
            d.save()
            fixed_dockets += 1
            if not testing_mode:
                # This will hit ES. So better to do it slowly.
                time.sleep(iteration_wait)

        # Log progress every 100 items.
        if iteration % 100 == 0 or iteration == total_dockets:
            progress_percentage = (iteration / total_dockets) * 100
            logger.info(
                f"Progress: {iteration}/{total_dockets} ({progress_percentage:.2f}%) dockets processed. Fixed: {fixed_dockets}"
            )

    logger.info(
        f"Completed. Total dockets processed: {total_dockets}, Fixed: {fixed_dockets} Dockets"
    )


class Command(VerboseCommand):
    help = "Find and fix Dockets referred and assigned judges."

    def add_arguments(self, parser):
        parser.add_argument(
            "--iteration-wait",
            type=float,
            default="0.1",
            help="The time to wait between each iteration.",
        )
        parser.add_argument(
            "--testing-mode",
            action="store_true",
            help="Use this flag only when running the command in tests based on TestCase",
        )

    def handle(self, *args, **options):
        testing_mode = options.get("testing_mode", False)
        iteration_wait = options.get("iteration_wait", 0.1)
        find_and_fix_docket_judges(iteration_wait, testing_mode)
