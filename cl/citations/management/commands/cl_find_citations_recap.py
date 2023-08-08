import sys
import time
from typing import Iterable, List, cast

from django.conf import settings
from django.core.management import CommandError, call_command
from django.core.management.base import CommandParser

from cl.citations.tasks import (
    find_citations_and_parantheticals_for_recap_documents,
)
from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.types import OptionsType
from cl.search.models import RECAPDocument


class Command(VerboseCommand):
    help = "Parse citations from court filings we have stored through RECAP"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--doc-ids",
            type=int,
            nargs="*",
            help="pks of citing RECAP documents",
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
            "documents to update.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            default=False,
            help="Parse citations for all stored RECAP documents",
        )
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )

        def update_documents(self, pks: Iterable, queue_name: str):
            sys.stdout.write(f"Graph size is {self.count:d} nodes.\n")
            sys.stdout.flush()

            chunk = []
            chunk_size = 100
            processed_count = 0
            throttle = CeleryThrottle(queue_name=queue_name)

            for pk in pks:
                throttle.maybe_wait()
                processed_count += 1
                last_item = self.count == processed_count
                chunk.append(pk)

                if processed_count % chunk_size == 0 or last_item:
                    find_citations_and_parantheticals_for_recap_documents.apply_async(
                        args=(chunk),
                        queue=queue_name,
                    )
                    chunk = []

                self.log_progress(processed_count, pk)

        def handle(self, *args: List[str], **options: OptionsType):
            super(Command, self).handle(*args, **options)
            both_list_and_endpoints = options.get("doc_id") is not None and (
                options.get("start_id") is not None
                or options.get("end_id") is not None
                or options.get("filed_after") is not None
                or options.get("filed_before") is not None
                or options.get("modified_after") is not None
            )
            no_option = not any(
                [
                    options.get("doc_id") is None,
                    options.get("start_id") is None,
                    options.get("end_id") is None,
                    options.get("filed_after") is None,
                    options.get("filed_before") is None,
                    options.get("modified_after") is None,
                    options.get("all") is False,
                ]
            )
            if both_list_and_endpoints or no_option:
                raise CommandError(
                    "Please specify either a list of documents, a "
                    "range of ids, a range of dates, or "
                    "everything."
                )

            self.index = options["index"]
            query = RECAPDocument.objects.all().order_by("pk")
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
                query = query.filter(
                    date_modified__gte=options["modified_after"]
                )

            if options.get("all"):
                query = RECAPDocument.objects.all()

            self.count = query.count()
            self.average_per_s = 0.0
            self.timings = []

            document_pks = query.values_list("pk", flat=True).iterator()
            queue = cast(str, options["queue"])
            self.update_documents(document_pks, queue)

            def log_progreess(self, processed_count: int, last_pk: int):
                if processed_count % 1000 == 1:
                    self.t1 = time.time()
                if processed_count % 1000 == 0:
                    self.t2 = time.time()
                    self.timings.append(self.t2 - self.t1)
                    self.average_per_s = (
                        1000 / sum(self.timings) / float(len(self.timings))
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
