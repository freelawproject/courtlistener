import sys
import time
from collections.abc import Iterable
from typing import cast

from django.core.management import CommandError
from django.core.management.base import CommandParser
from localflavor.us.us_states import OBSOLETE_STATES, USPS_CHOICES

from cl.citations.tasks import (
    find_citations_and_parentheticals_for_opinion_by_pks,
)
from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.types import OptionsType
from cl.search.models import Courthouse, Opinion

DEFAULT_THROTTLE_MIN_ITEMS = 50
DEFAULT_OPINIONS_PER_TASK = 50


class Command(VerboseCommand):
    help = "Parse citations and parentheticals from court opinions."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--doc-id",
            type=int,
            nargs="*",
            help="ids of citing opinions",
        )
        parser.add_argument(
            "--start-id",
            type=int,
            help="start id for a range of documents to update (inclusive)",
        )
        parser.add_argument(
            "--end-id",
            type=int,
            help="end id for a range of documents to update (inclusive)",
        )
        parser.add_argument(
            "--filed-after",
            type=valid_date_time,
            help="Start date in ISO-8601 format for a range of documents to "
            "update.",
        )
        parser.add_argument(
            "--filed-before",
            type=valid_date_time,
            help="End date in ISO-8601 format for a range of documents to "
            "update.",
        )
        parser.add_argument(
            "--modified-after",
            type=valid_date_time,
            help="The modification date ISO-8601 format for a range of "
            "Opinion objects to update.",
        )
        parser.add_argument(
            "--modified-before",
            type=valid_date_time,
            help="The modification date ISO-8601 format for a range of "
            "Opinion objects to update.",
        )
        parser.add_argument(
            "--state",
            choices=[key[0] for key in USPS_CHOICES + OBSOLETE_STATES],
            help="State abbreviation E.g. NY, MA, CA.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            default=False,
            help="Parse citations for all items",
        )
        parser.add_argument(
            "--no-html-with-citations",
            action="store_true",
            default=False,
            help="Parse only opinions without html_with_citations",
        )
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--throttle-min-items",
            default=DEFAULT_THROTTLE_MIN_ITEMS,
            type=int,
            help=(
                "Control the max number of tasks sent to Celery. To be used "
                "on `CeleryThrottle.update_min_items`"
            ),
        )
        parser.add_argument(
            "--opinions-per-task",
            default=DEFAULT_OPINIONS_PER_TASK,
            type=int,
            help="Number of opinions in a single parent task",
        )
        parser.add_argument(
            "--disable-parenthetical-groups",
            action="store_true",
            default=False,
            help="Do not create ParentheticalGroups and disconnect their "
            "ElasticSearch signals",
        )
        parser.add_argument(
            "--disable-citation-count-update",
            action="store_true",
            default=False,
            help=(
                "Disconnect OpinionCluster.citation_count and related ES "
                "documents update"
            ),
        )

    def handle(self, *args: list[str], **options: OptionsType) -> None:
        super().handle(*args, **options)
        both_list_and_endpoints = options.get("doc_id") is not None and (
            options.get("start_id") is not None
            or options.get("end_id") is not None
            or options.get("filed_after") is not None
            or options.get("filed_before") is not None
            or options.get("modified_after") is not None
            or options.get("modified_before") is not None
        )
        no_option = not any(
            [
                options.get("doc_id") is None,
                options.get("start_id") is None,
                options.get("end_id") is None,
                options.get("filed_after") is None,
                options.get("filed_before") is None,
                options.get("modified_after") is None,
                options.get("modified_before") is None,
                options.get("state") is not None,
                options.get("no_html_with_citations") is False,
                options.get("all") is False,
            ]
        )
        if both_list_and_endpoints or no_option:
            raise CommandError(
                "Please specify either a list of documents, a "
                "range of ids, a range of dates, a state or "
                "everything."
            )

        # Use query chaining to build the query
        query = Opinion.objects.all().order_by("pk")
        if options.get("state"):
            court_ids = Courthouse.objects.filter(
                state=options["state"]
            ).values_list("court", flat=True)
            if not court_ids:
                raise CommandError(
                    f"No courts associated with {options['state']}"
                )
            query = query.filter(cluster__docket__court__in=court_ids)
        if options.get("doc_id"):
            query = query.filter(pk__in=options["doc_id"])
        if options.get("end_id"):
            query = query.filter(pk__lte=options["end_id"])
        if options.get("start_id"):
            query = query.filter(pk__gte=options["start_id"])
        if options.get("filed_after"):
            query = query.filter(
                cluster__date_filed__gte=options["filed_after"]
            )
        if options.get("filed_before"):
            query = query.filter(
                cluster__date_filed__lte=options["filed_before"]
            )
        if options.get("modified_after"):
            query = query.filter(date_modified__gte=options["modified_after"])
        if options.get("modified_before"):
            query = query.filter(date_modified__lte=options["modified_before"])
        if options.get("no_html_with_citations"):
            query = query.filter(html_with_citations="")
        if options.get("all"):
            query = Opinion.objects.all()
            # force disconnection for batch jobs
            disable_parenthetical_groups = True
            disable_citation_count_update = True
        else:
            disable_parenthetical_groups = cast(
                bool, options["disable_parenthetical_groups"]
            )
            disable_citation_count_update = cast(
                bool, options["disable_citation_count_update"]
            )

        self.count = query.count()
        self.average_per_s = 0.0
        self.timings: list[float] = []
        opinion_pks = query.values_list("pk", flat=True).iterator()
        self.update_documents(
            opinion_pks,
            cast(str, options["queue"]),
            cast(int, options["throttle_min_items"]),
            cast(int, options["opinions_per_task"]),
            disable_parenthetical_groups,
            disable_citation_count_update,
        )

    def log_progress(self, processed_count: int, last_pk: int) -> None:
        if processed_count % 1000 == 1:
            self.t1 = time.time()
        if processed_count % 1000 == 0:
            self.t2 = time.time()
            self.timings.append(self.t2 - self.t1)
            self.average_per_s = 1000 / (
                sum(self.timings) / float(len(self.timings))
            )
        template = (
            "\rProcessing items in Celery queue: {:.0%} ({}/{}, "
            "{:.1f}/s, Last id: {})"
        )
        sys.stdout.write(
            template.format(
                float(processed_count) / self.count,  # Percent
                processed_count,
                self.count,
                self.average_per_s,
                last_pk,
            )
        )
        sys.stdout.flush()

    def update_documents(
        self,
        opinion_pks: Iterable,
        queue_name: str,
        throttle_min_items: int = DEFAULT_THROTTLE_MIN_ITEMS,
        opinions_per_task: int = DEFAULT_OPINIONS_PER_TASK,
        disable_parenthetical_groups: bool = False,
        disable_citation_count_update: bool = False,
    ) -> None:
        sys.stdout.write(f"Graph size is {self.count:d} nodes.\n")
        sys.stdout.flush()

        chunk = []
        processed_count = 0
        throttle = CeleryThrottle(queue_name=queue_name)
        throttle.update_min_items(throttle_min_items)

        for opinion_pk in opinion_pks:
            throttle.maybe_wait()
            processed_count += 1
            last_item = self.count == processed_count
            chunk.append(opinion_pk)
            if processed_count % opinions_per_task == 0 or last_item:
                find_citations_and_parentheticals_for_opinion_by_pks.apply_async(
                    args=(
                        chunk,
                        disable_parenthetical_groups,
                        disable_citation_count_update,
                    ),
                    queue=queue_name,
                )
                chunk = []

            self.log_progress(processed_count, opinion_pk)
