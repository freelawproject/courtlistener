import time
from datetime import datetime

from django.conf import settings
from django.db.models import (
    Count,
    Exists,
    F,
    Max,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
)

from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.search.models import (
    SEARCH_TYPES,
    Docket,
    DocketEntry,
    DocketEvent,
    RECAPDocument,
)
from cl.search.tasks import index_parent_or_child_docs_in_es


def get_docket_events_and_slug_count(
    cut_off_date: datetime,
    pk_offset: int,
    docket_ids: list[int] | None,
) -> QuerySet:
    """Retrieve docket events that need verification for broken links and their
     slug count.

    :param cut_off_date: The cutoff date for filtering docket events.
    :param pk_offset: The minimum Docket ID value to consider for auto-resume.
    :param docket_ids: Optional, the Docket IDs to consider.
    :return: A queryset of docket events annotated with their slug count,
    the current slug from the Docket table, and the latest slug in the
    DocketEvent table.
    """

    # Exclude dockets with no entries.
    docket_has_entries_subquery = DocketEntry.objects.filter(
        docket=OuterRef("id")
    ).values("id")[:1]

    docket_queryset = Docket.objects.filter(
        pk__gte=pk_offset,
        date_modified__gte=cut_off_date,
        source__in=Docket.RECAP_SOURCES(),
    )
    if docket_ids is not None:
        docket_queryset = docket_queryset.filter(pk__in=docket_ids)

    docket_ids_subquery = (
        docket_queryset.annotate(
            has_entries=Exists(docket_has_entries_subquery)
        )
        .filter(has_entries=True)
        .values_list("id", flat=True)
    )

    return (
        DocketEvent.objects.filter(
            pgh_obj_id__in=Subquery(docket_ids_subquery),
            pgh_created_at__gte=cut_off_date,
        )
        .values("pgh_obj_id")
        .annotate(
            slug_count=Count("slug", distinct=True),
            event_table_slug=Max("slug"),
            docket_table_slug=Max("pgh_obj__slug"),
        )
    )


def get_dockets_to_fix(
    cut_off_date: datetime,
    pk_offset: int,
    docket_ids: list[int] | None,
) -> QuerySet:
    """Retrieve dockets that require fixing due to broken links by filtering
    docket events based on their slug count to identify cases where the slugs
    are inconsistent or multiple unique slugs exist.

    :param cut_off_date: The cutoff date for filtering docket events.
    :param pk_offset: The minimum ID value to consider.
    :param docket_ids: Optional, the Docket IDs to consider.
    :return: A queryset of docket events that need to be fixed.
    """

    docket_events_and_slug_count = get_docket_events_and_slug_count(
        cut_off_date, pk_offset, docket_ids
    )

    # If the slug count is greater than 1, it indicates that the slug has changed,
    # so the related docket needs to be fixed. If the slug count is 1, an additional
    # check is required: if the slug in the event table differs from the current
    # slug in the docket table, the docket should also be fixed.
    # This ensures that changes in the slug, which are not yet reflected in the
    # DocketEvent table, are still detected and fixed.
    return docket_events_and_slug_count.filter(
        Q(slug_count__gt=1)
        | (Q(slug_count=1) & ~Q(event_table_slug=F("docket_table_slug")))
    ).values_list("pgh_obj_id", flat=True)


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
        self.interval = None
        self.ids = None

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
        parser.add_argument(
            "--interval",
            type=float,
            default=0.5,
            help="Wait before scheduling a new chunk, in seconds.",
        )
        parser.add_argument(
            "--id",
            dest="ids",
            nargs="+",
            help="Docket IDs to consider.",
            required=False,
        )

    def get_and_fix_rds(self, cut_off_date: datetime) -> int:
        """Get the dockets with broken RECAPDocument links and fix their RDs by
        re-indexing.

        :param cut_off_date: The cutoff date to filter docket events.
        :return: The number of dockets affected.
        """

        chunk = []
        affected_rds = 0
        docket_ids_to_fix_queryset = get_dockets_to_fix(
            cut_off_date, self.pk_offset, self.ids
        )
        rd_queryset = (
            RECAPDocument.objects.filter(
                docket_entry__docket_id__in=Subquery(
                    docket_ids_to_fix_queryset
                )
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        logger.info(
            "Getting the count of recap documents that need to be fixed."
        )
        count = rd_queryset.count()
        for rd_id_to_fix in rd_queryset.iterator():
            chunk.append(rd_id_to_fix)
            affected_rds += 1
            last_item = count == affected_rds
            if affected_rds % self.chunk_size == 0 or last_item:
                self.throttle.maybe_wait()
                index_parent_or_child_docs_in_es.si(
                    chunk,
                    SEARCH_TYPES.RECAP,
                    "child",
                    use_streaming_bulk=True,
                ).set(queue=self.queue).apply_async()
                if self.testing_mode:
                    logger.info("Processing chunk: %s", chunk)
                else:
                    # Does not wait between chunks in testing mode.
                    time.sleep(self.interval)

                chunk = []
                logger.info(
                    "Processed %d/%d (%.0f%%), last PK fixed: %s",
                    affected_rds,
                    count,
                    (affected_rds * 100.0) / count,
                    rd_id_to_fix,
                )

                if not affected_rds % 1000:
                    # Log every 1000 documents processed.
                    log_last_document_indexed(
                        rd_id_to_fix, compose_redis_key()
                    )

        return count

    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.options = options
        self.queue = self.options["queue"]
        self.testing_mode = self.options["testing_mode"]
        self.chunk_size = self.options["chunk_size"]
        self.throttle = CeleryThrottle(queue_name=self.queue)
        self.interval = self.options["interval"]
        self.ids = options.get("ids")
        auto_resume = options["auto_resume"]
        if auto_resume:
            self.pk_offset = get_last_parent_document_id_processed(
                compose_redis_key()
            )
            self.stdout.write(
                f"Auto-resume enabled starting indexing from ID: {self.pk_offset}."
            )
        start_date: datetime = options["start_date"]
        affected_rds = self.get_and_fix_rds(start_date)
        logger.info(
            "Successfully fixed %d items from pk %s.",
            affected_rds,
            self.pk_offset,
        )
