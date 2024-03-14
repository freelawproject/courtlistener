from typing import Iterable

from django.conf import settings

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.redis_utils import get_redis_interface
from cl.search.documents import DocketDocument
from cl.search.management.commands.cl_index_parent_and_child_docs import (
    log_last_document_indexed,
)
from cl.search.models import Docket
from cl.search.tasks import remove_documents_by_query


def compose_redis_key_non_recap() -> str:
    """Compose a Redis key based on the search type for indexing log.

    document type being processed.
    :return: A Redis key as a string.
    """
    return f"es_remove_non_recap_docket:log"


def get_last_parent_document_id_processed() -> int:
    """Get the last document ID indexed.
    :return: The last document ID indexed.
    """

    r = get_redis_interface("CACHE")
    log_key = compose_redis_key_non_recap()
    stored_values = r.hgetall(log_key)
    last_document_id = int(stored_values.get("last_document_id", 0))

    return last_document_id


class Command(VerboseCommand):
    help = "Remove non-recap dockets from RECAP index in ES."

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
            help="Auto resume the command using the last document_id logged in Redis.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.options = options

        chunk_size = self.options["chunk_size"]
        auto_resume = options.get("auto_resume", False)

        pk_offset = 0
        if auto_resume:
            pk_offset = get_last_parent_document_id_processed()
            self.stdout.write(
                f"Auto-resume enabled starting indexing from ID: {pk_offset}."
            )
        # Dockets that don't belong to RECAP_SOURCES.
        queryset = (
            Docket.objects.filter(pk__gte=pk_offset)
            .exclude(source__in=Docket.RECAP_SOURCES)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        q = queryset.iterator()
        count = queryset.count()

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

        chunk = []
        processed_count = 0
        throttle = CeleryThrottle(queue_name=queue)
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
                        item_id, compose_redis_key_non_recap()
                    )

        logger.info(
            f"Successfully removed {processed_count} non-recap dockets."
        )
