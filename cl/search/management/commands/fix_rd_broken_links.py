from datetime import datetime

from django.conf import settings
from django.db.models import Count, QuerySet

from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.search.models import SEARCH_TYPES
from cl.search.tasks import index_parent_and_child_docs
from cl.search.models import (
    Docket,
    DocketEvent,
)


def get_docket_events_to_check(cut_off_date:datetime, pk_offset:int)->QuerySet:
    """Retrieve docket events that need verification for broken links.

    :param cut_off_date: The cutoff date to filter docket events.
    :param pk_offset: The minimum ID value to consider.
    :return: A queryset of docket events annotated with their total event count.
    """

    return (
        DocketEvent.objects.filter(
            pgh_created_at__gte=cut_off_date,
            id__gte=pk_offset,
            source__in=Docket.RECAP_SOURCES(),
        )
        .values("id")
        .annotate(total_events=Count("id"))
        .order_by("id")
    )

def get_docket_events_count_by_slug(cut_off_date:datetime, docket_id:int, slug:str)->QuerySet:
    """Count docket events matching a given docket ID and slug after a cutoff date.

    :param cut_off_date: The cutoff date to filter docket events.
    :param docket_id: The ID of the docket to check.
    :param slug: The slug associated with the docket.
    :return: The count of matching docket events.
    """
    return DocketEvent.objects.filter(
        pgh_created_at__gte=cut_off_date,
        slug=slug,
        id=docket_id,
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


    def fix_broken_recap_document_links(self, cut_off_date:datetime)->None:
        """Fix broken RECAP document links by re-indexing affected dockets.

        :param cut_off_date: The cutoff date to filter docket events.
        :return: None
        """
        queue = self.options["queue"]
        testing_mode = self.options["testing_mode"]
        chunk_size = self.options["chunk_size"]
        chunk = []
        processed_count = 0
        throttle = CeleryThrottle(queue_name=queue)

        events_count_per_docket = get_docket_events_to_check(cut_off_date, self.pk_offset)
        for docket_event_count in events_count_per_docket.iterator():
            docket_id = docket_event_count["id"]
            current_docket = Docket.objects.filter(pk=docket_id).values_list("slug", flat=True)
            if not current_docket.exists():
                continue

            docket_slug_events_count = get_docket_events_count_by_slug(cut_off_date, docket_id, current_docket.first())
            if docket_event_count["total_events"] != docket_slug_events_count:
                chunk.append(docket_id)
                processed_count += 1

                # Process the chunk.
                if len(chunk) >= chunk_size:
                    throttle.maybe_wait()
                    self.stdout.write("Processing chunk: {}".format(chunk))
                    index_parent_and_child_docs.si(
                        chunk,
                        SEARCH_TYPES.RECAP,
                        testing_mode=testing_mode,
                    ).set(queue=queue).apply_async()
                    self.stdout.write(
                        "Processed {} items so far.".format(processed_count))
                    if processed_count % 1000 == 0:
                        log_last_document_indexed(docket_id,
                                                  compose_redis_key())
                    chunk = []

            # Process any remaining docket_ids in the final chunk.
            if chunk:
                throttle.maybe_wait()
                self.stdout.write("Processing final chunk: {}".format(chunk))
                index_parent_and_child_docs.si(
                    chunk,
                    SEARCH_TYPES.RECAP,
                    testing_mode=testing_mode,
                ).set(queue=queue).apply_async()

            self.stdout.write(
                f"Successfully fixed {processed_count} items from pk {self.pk_offset}."
            )



    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.options = options
        auto_resume = options["auto_resume"]
        if auto_resume:
            self.pk_offset = get_last_parent_document_id_processed(
                compose_redis_key()
            )
            self.stdout.write(
                f"Auto-resume enabled starting indexing from ID: {self.pk_offset}."
            )
        start_date: datetime = options["start_date"]
        self.fix_broken_recap_document_links(start_date)
