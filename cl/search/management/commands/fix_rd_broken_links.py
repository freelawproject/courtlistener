from datetime import datetime

from django.conf import settings
from django.db.models import Count, QuerySet, Subquery

from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.search.models import SEARCH_TYPES, Docket, DocketEvent
from cl.search.tasks import index_parent_and_child_docs


def get_docket_events_to_check(
    cut_off_date: datetime, pk_offset: int
) -> QuerySet:
    """Retrieve docket events that need verification for broken links.

    :param cut_off_date: The cutoff date to filter docket events.
    :param pk_offset: The minimum ID value to consider.
    :return: A queryset of docket events annotated with their total event count.
    """

    # Get dockets that changed after cut_off_date using the Docket table for
    # better performance. The date_modified column in the Docket table has an
    # index, whereas the DocketEvent table does not have an index for date_modified
    docket_ids_subquery = Docket.objects.filter(
        pk__gte=pk_offset,
        date_modified__gte=cut_off_date,
        source__in=Docket.RECAP_SOURCES(),
    ).values_list("id", flat=True)
    return (
        DocketEvent.objects.filter(
            pgh_obj_id__in=Subquery(docket_ids_subquery),
        )
        .values("id")
        .annotate(total_events=Count("id"))
        .order_by("id")
    )


def get_docket_events_count_by_slug(
    cut_off_date: datetime, docket_id: int, slug: str
) -> QuerySet:
    """Count docket events matching a given docket ID and slug after a cutoff date.

    :param cut_off_date: The cutoff date to filter docket events.
    :param docket_id: The ID of the docket to check.
    :param slug: The slug associated with the docket.
    :return: The count of matching docket events.
    """
    return DocketEvent.objects.filter(
        pgh_obj_id=docket_id,
        pgh_created_at__gte=cut_off_date,
        slug=slug,
    ).count()


def compose_redis_key() -> str:
    """Compose a Redis key based on the search type for indexing log.
    :return: A Redis key as a string.
    """
    return f"es_fix_rd_broken_links:log"


class Command(VerboseCommand):
    help = "Re-index RECAP documents affected by broken links."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = {}
        self.pk_offset = 0
        self.throttle = None
        self.testing_mode = None
        self.queue = None
        self.chunk_size = None

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

    def get_count_or_process_chunks(
        self, cut_off_date: datetime, count: int = None
    ) -> int | None:
        """Get the count or process broken RECAPDocuments links
        by re-indexing affected dockets.

        :param cut_off_date: The cutoff date to filter docket events.
        :param count: Optional: the total number of dockets affected to be
        fixed, or None if it should be computed.
        :return: None
        """

        chunk = []
        affected_dockets = 0
        events_count_per_docket = get_docket_events_to_check(
            cut_off_date, self.pk_offset
        )
        for docket_event_count in events_count_per_docket.iterator():
            docket_id = docket_event_count["id"]
            current_docket_slug = Docket.objects.filter(
                pk=docket_id
            ).values_list("slug", flat=True)
            if not current_docket_slug.exists():
                continue

            docket_slug_events_count = get_docket_events_count_by_slug(
                cut_off_date, docket_id, current_docket_slug.first()
            )
            if docket_event_count["total_events"] != docket_slug_events_count:
                affected_dockets += 1
                if count is not None:
                    # If the count is provided, process the dockets to be fixed
                    # at this stage.
                    chunk.append(docket_id)
                    last_item = count == affected_dockets
                    if affected_dockets % self.chunk_size == 0 or last_item:
                        self.throttle.maybe_wait()
                        index_parent_and_child_docs.si(
                            chunk,
                            SEARCH_TYPES.RECAP,
                            testing_mode=self.testing_mode,
                        ).set(queue=self.queue).apply_async()
                        if self.testing_mode:
                            logger.info("Processing chunk: %s", chunk)

                        chunk = []
                        logger.info(
                            "Processed %d/%d (%.0f%%), last PK fixed: %s",
                            affected_dockets,
                            count,
                            (affected_dockets * 100.0) / count,
                            docket_id,
                        )
                        if not affected_dockets % 1000:
                            # Log every 1000 documents processed.
                            log_last_document_indexed(
                                docket_id, compose_redis_key()
                            )

        return affected_dockets

    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.options = options
        self.queue = self.options["queue"]
        self.testing_mode = self.options["testing_mode"]
        self.chunk_size = self.options["chunk_size"]
        self.throttle = CeleryThrottle(queue_name=self.queue)
        auto_resume = options["auto_resume"]
        if auto_resume:
            self.pk_offset = get_last_parent_document_id_processed(
                compose_redis_key()
            )
            self.stdout.write(
                f"Auto-resume enabled starting indexing from ID: {self.pk_offset}."
            )
        start_date: datetime = options["start_date"]
        # Due to the complexity of the queries, this is a two-step process.
        # First, get the total number of dockets affected by the broken links issue.
        affected_dockets = self.get_count_or_process_chunks(start_date)
        logger.info(
            "Count of dockets to be fixed: %d.",
            affected_dockets,
        )
        # As the second stage, use this count to process the affected docket
        # chunks and log the task progress.
        self.get_count_or_process_chunks(start_date, affected_dockets)

        logger.info(
            "Successfully fixed %d items from pk %s.",
            affected_dockets,
            self.pk_offset,
        )
