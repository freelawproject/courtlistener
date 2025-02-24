from datetime import datetime

from django.conf import settings
from django.db.models import Count, Exists, F, OuterRef, Q, QuerySet, Subquery

from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.search.models import SEARCH_TYPES, Docket, DocketEntry, DocketEvent
from cl.search.tasks import index_parent_and_child_docs


def get_docket_events_and_slug_count(
    cut_off_date: datetime,
    pk_offset: int,
) -> QuerySet:
    """Retrieve docket events that need verification for broken links and their
     slug count.

    :param cut_off_date: The cutoff date for filtering docket events.
    :param pk_offset: The minimum Docket ID value to consider for auto-resume.
    :return: A queryset of docket events annotated with their slug count,
    the current slug from the Docket table, and the latest slug in the
    DocketEvent table.
    """

    # Exclude dockets with no entries.
    docket_has_entries_subquery = DocketEntry.objects.filter(
        docket=OuterRef("id")
    ).values("id")[:1]

    docket_ids_subquery = (
        Docket.objects.filter(
            pk__gte=pk_offset,
            date_modified__gte=cut_off_date,
            source__in=Docket.RECAP_SOURCES(),
        )
        .annotate(has_entries=Exists(docket_has_entries_subquery))
        .filter(has_entries=True)
        .values_list("id", flat=True)
    )

    # Get the current slug in the Docket table.
    docket_slug_subquery = Docket.objects.filter(
        id=OuterRef("pgh_obj_id")
    ).values("slug")[:1]

    # Get the latest slug in the DocketEvent table.
    last_docket_event_slug_subquery = (
        DocketEvent.objects.filter(
            pgh_obj_id=OuterRef("pgh_obj_id"),
            pgh_created_at__gte=cut_off_date,
        )
        .order_by("-pgh_id")
        .values("slug")[:1]
    )

    return (
        DocketEvent.objects.filter(
            pgh_obj_id__in=Subquery(docket_ids_subquery),
            pgh_created_at__gte=cut_off_date,
        )
        .values("pgh_obj_id")
        .annotate(
            slug_count=Count("slug", distinct=True),
            event_table_slug=Subquery(last_docket_event_slug_subquery),
            docket_table_slug=Subquery(docket_slug_subquery),
        )
    )


def get_dockets_to_fix(
    cut_off_date: datetime,
    pk_offset: int,
) -> QuerySet:
    """Retrieve dockets that require fixing due to broken links by filtering
    docket events based on their slug count to identify cases where the slugs
    are inconsistent or multiple unique slugs exist.

    :param cut_off_date: The cutoff date for filtering docket events.
    :param pk_offset: The minimum ID value to consider.
    :return: A queryset of docket events that need to be fixed.
    """

    docket_events_and_slug_count = get_docket_events_and_slug_count(
        cut_off_date, pk_offset
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
    )


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

    def get_and_fix_dockets(self, cut_off_date: datetime) -> int:
        """Get the dockets with broken RECAPDocument links and fix them by
        re-indexing the affected dockets and their RDs.

        :param cut_off_date: The cutoff date to filter docket events.
        :return: The number of dockets affected.
        """

        chunk = []
        affected_dockets = 0
        dockets_to_fix_queryset = get_dockets_to_fix(
            cut_off_date, self.pk_offset
        )
        count = dockets_to_fix_queryset.count()
        for docket_to_fix in dockets_to_fix_queryset.iterator():
            docket_id = docket_to_fix["pgh_obj_id"]
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
                    log_last_document_indexed(docket_id, compose_redis_key())

        return count

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
        affected_dockets = self.get_and_fix_dockets(start_date)
        logger.info(
            "Successfully fixed %d items from pk %s.",
            affected_dockets,
            self.pk_offset,
        )
