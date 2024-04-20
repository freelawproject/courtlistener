from datetime import date, datetime
from typing import Iterable

from django.conf import settings

from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.redis_utils import get_redis_interface
from cl.search.documents import DocketDocument, OpinionDocument
from cl.search.management.commands.cl_index_parent_and_child_docs import (
    log_last_document_indexed,
)
from cl.search.models import Docket
from cl.search.tasks import remove_documents_by_query


def compose_redis_key_remove_content() -> str:
    """Compose a Redis key for storing the removal action status.
    :return: A Redis key as a string.
    """
    return "es_remove_content_from_es:log"


def get_last_parent_document_id_processed() -> int:
    """Get the last document ID indexed.
    :return: The last document ID indexed.
    """

    r = get_redis_interface("CACHE")
    log_key = compose_redis_key_remove_content()
    stored_values = r.hgetall(log_key)
    last_document_id = int(stored_values.get("last_document_id", 0))

    return last_document_id


class Command(VerboseCommand):
    help = "Remove content from an ES index."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = {}

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue",
            type=str,
            default=settings.CELERY_ETL_TASK_QUEUE,
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--queue-size",
            type=int,
            default="10",
            help="The min_items queue size used for celery throttling.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default="100",
            help="The number of items to index in a single celery task.",
        )
        parser.add_argument(
            "--auto-resume",
            action="store_true",
            help="Auto resume the command using the last document_id logged in Redis.",
        )
        parser.add_argument(
            "--action",
            type=str,
            required=False,
            choices=["non-recap-dockets", "opinions-removal"],
            help="The removal action to perform.",
        )
        parser.add_argument(
            "--start-date",
            type=valid_date_time,
            help="Start date in ISO-8601 format for a range of documents to "
            "delete.",
        )
        parser.add_argument(
            "--end-date",
            type=valid_date_time,
            help="Start date in ISO-8601 format for a range of documents to "
            "delete.",
        )
        parser.add_argument(
            "--testing-mode",
            action="store_true",
            help="Use this flag only when running the command in tests based on TestCase",
        )
        parser.add_argument(
            "--max-docs",
            type=int,
            default="0",
            help="The max number of documents to process. Default to 0 means no limit.",
        )
        parser.add_argument(
            "--requests-per-second",
            type=int,
            default="8",
            help="The max number of sub-requests per second for a removal operation. "
            "Defaults to 8",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.options = options
        start_date: date | None = options.get("start_date", None)
        end_date: date | None = options.get("end_date", None)
        action = options.get("action")
        testing_mode = self.options.get("testing_mode", False)

        chunk_size = self.options["chunk_size"]
        auto_resume = options.get("auto_resume", False)
        max_docs = options.get("max_docs", 0)
        requests_per_second = options.get("requests_per_second")

        pk_offset = 0
        if auto_resume:
            pk_offset = get_last_parent_document_id_processed()
            self.stdout.write(
                f"Auto-resume enabled starting indexing from ID: {pk_offset}."
            )

        match action:
            case "non-recap-dockets":
                # Dockets that don't belong to RECAP_SOURCES.
                queryset = (
                    Docket.objects.filter(pk__gte=pk_offset)
                    .exclude(source__in=Docket.RECAP_SOURCES())
                    .order_by("pk")
                    .values_list("pk", flat=True)
                )
                q = queryset.iterator()
                count = queryset.count()
            case "opinions-removal" if start_date and end_date:
                if isinstance(start_date, datetime):
                    start_date = start_date.date()
                if isinstance(end_date, datetime):
                    end_date = end_date.date()
                response = remove_documents_by_query(
                    OpinionDocument.__name__,
                    start_date=start_date,
                    end_date=end_date,
                    testing_mode=testing_mode,
                    requests_per_second=requests_per_second,
                    max_docs=max_docs,
                )
                logger.info(
                    f"Removal task successfully scheduled. Task ID: {response}"
                )
                return
            case _:
                return

        self.process_queryset(q, count, chunk_size)

    def process_queryset(
        self,
        items: Iterable,
        count: int,
        chunk_size: int,
    ) -> None:
        """Process the queryset that removes non-recap dockets from ES.

        :param items: Iterable of items IDS to process.
        :param count: Total number of items expected to process.
        :param chunk_size: The number of items to process in a single chunk.
        :return: None
        """
        queue = self.options["queue"]
        queue_size = self.options["queue_size"]
        chunk = []
        processed_count = 0
        throttle = CeleryThrottle(min_items=queue_size, queue_name=queue)
        for item_id in items:
            processed_count += 1
            last_item = count == processed_count
            chunk.append(item_id)
            if processed_count % chunk_size == 0 or last_item:
                throttle.maybe_wait()
                remove_documents_by_query.si(
                    DocketDocument.__name__, chunk
                ).set(queue=queue).apply_async()
                chunk = []
                self.stdout.write(
                    "\rProcessed {}/{}, ({:.0%}), last PK {}".format(
                        processed_count,
                        count,
                        processed_count * 1.0 / count,
                        item_id,
                    )
                )
                if not processed_count % 1000:
                    # Log every 1000 parent documents processed.
                    log_last_document_indexed(
                        item_id, compose_redis_key_remove_content()
                    )

        logger.info(
            f"Successfully removed {processed_count} non-recap dockets."
        )
