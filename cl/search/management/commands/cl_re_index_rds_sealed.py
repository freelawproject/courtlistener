from datetime import date, datetime
from typing import Iterable

from django.conf import settings

from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.search.models import SEARCH_TYPES, RECAPDocument
from cl.search.tasks import index_parent_or_child_docs_in_es


def compose_redis_key() -> str:
    """Compose a Redis key based on the search type for indexing log.
    :return: A Redis key as a string.
    """
    return f"es_re_index_rd_sealed:log"


class Command(VerboseCommand):
    help = "Re-index RECAPDocuments sealed from a date."

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
            "--chunk-size",
            type=int,
            default="100",
            help="The number of items to index in a single celery task.",
        )
        parser.add_argument(
            "--auto-resume",
            action="store_true",
            default=False,
            help="Auto resume the command using the last document_id logged in Redis. "
            "If --pk-offset is provided, it'll be ignored.",
        )
        parser.add_argument(
            "--testing-mode",
            action="store_true",
            default=False,
            help="Use this flag only when running the command in tests based on TestCase",
        )
        parser.add_argument(
            "--start-date",
            type=valid_date_time,
            required=True,
            help="Start date in ISO-8601 format for a range of documents to "
            "update.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.options = options
        auto_resume = options["auto_resume"]
        pk_offset = 0
        if auto_resume:
            pk_offset = get_last_parent_document_id_processed(
                compose_redis_key()
            )
            self.stdout.write(
                f"Auto-resume enabled starting indexing from ID: {pk_offset}."
            )
        start_date: datetime = options["start_date"]
        queryset = (
            RECAPDocument.objects.filter(
                pk__gte=pk_offset,
                is_sealed=True,
                date_modified__gte=start_date,
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        q = queryset.iterator()
        count = queryset.count()

        self.process_queryset(
            q,
            count,
            pk_offset,
        )

    def process_queryset(
        self,
        items: Iterable,
        count: int,
        pk_offset: int,
    ) -> None:
        """Process a queryset and execute tasks based on the specified celery
        task_to_use.

        :param items: Iterable of items to process. Items can be a simple
        iterable of IDs or a tuple of (ID, changed_fields) for cases requiring
        field changes.
        :param count: Total number of items expected to process.
        :param pk_offset:
        :return: None
        """

        queue = self.options["queue"]
        testing_mode = self.options["testing_mode"]
        chunk_size = self.options["chunk_size"]
        chunk = []
        processed_count = 0
        throttle = CeleryThrottle(queue_name=queue)
        use_streaming_bulk = True if testing_mode else False
        # Indexing Parent and their child documents.
        for item_id in items:
            chunk.append(item_id)
            processed_count += 1
            last_item = count == processed_count
            if processed_count % chunk_size == 0 or last_item:
                throttle.maybe_wait()
                index_parent_or_child_docs_in_es.si(
                    chunk,
                    SEARCH_TYPES.RECAP,
                    "child",
                    use_streaming_bulk=use_streaming_bulk,
                ).set(queue=queue).apply_async()

                chunk = []

                self.stdout.write(
                    "\rProcessed {}/{}, ({:.0%}), last PK indexed: {},".format(
                        processed_count,
                        count,
                        processed_count * 1.0 / count,
                        item_id,
                    )
                )
                if not processed_count % 1000:
                    # Log every 1000 parent documents processed.
                    log_last_document_indexed(item_id, compose_redis_key())
            self.stdout.write(
                f"Successfully indexed {processed_count} items from pk {pk_offset}."
            )
