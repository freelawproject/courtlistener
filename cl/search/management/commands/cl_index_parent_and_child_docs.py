from typing import Iterable

from django.conf import settings

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.people_db.models import Person
from cl.search.models import SEARCH_TYPES, Docket
from cl.search.tasks import index_parent_and_child_docs


class Command(VerboseCommand):
    help = "Index existing Parent and Children docs into Elasticsearch."

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.options = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--search-type",
            type=str,
            required=True,
            choices=[SEARCH_TYPES.PEOPLE, SEARCH_TYPES.RECAP],
            help=f"The search type models to index: ({', '.join([SEARCH_TYPES.PEOPLE, SEARCH_TYPES.RECAP])})",
        )

        parser.add_argument(
            "--pk-offset",
            type=int,
            default=0,
            help="The parent document pk to start indexing from.",
        )
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

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.options = options
        search_type = options["search_type"]
        match search_type:
            case SEARCH_TYPES.PEOPLE:
                queryset = Person.objects.filter(
                    pk__gte=options["pk_offset"], is_alias_of=None
                ).order_by("pk")
                q = [item.pk for item in queryset if item.is_judge]
                count = len(q)
                self.process_queryset(q, count, SEARCH_TYPES.PEOPLE)
            case SEARCH_TYPES.RECAP:
                # Get Docket objects by pk_offset.
                queryset = (
                    Docket.objects.filter(pk__gte=options["pk_offset"])
                    .order_by("pk")
                    .values_list("pk", flat=True)
                )
                q = queryset.iterator()
                count = queryset.count()
                self.process_queryset(q, count, SEARCH_TYPES.RECAP)

    def process_queryset(
        self, iterable: Iterable, count: int, search_type: str
    ) -> None:
        pk_offset = self.options["pk_offset"]
        queue = self.options["queue"]
        chunk_size = self.options["chunk_size"]

        chunk = []
        processed_count = 0
        throttle = CeleryThrottle(queue_name=queue)
        # Indexing Parent and their child documents.
        for item_id in iterable:
            processed_count += 1
            last_item = count == processed_count
            chunk.append(item_id)
            if processed_count % chunk_size == 0 or last_item:
                throttle.maybe_wait()
                index_parent_and_child_docs.si(chunk, search_type).set(
                    queue=queue
                ).apply_async()
                chunk = []
                self.stdout.write(
                    "\rProcessed {}/{}, ({:.0%}), last PK indexed: {},".format(
                        processed_count,
                        count,
                        processed_count * 1.0 / count,
                        item_id,
                    )
                )

        self.stdout.write(
            f"Successfully indexed {processed_count} items from pk {pk_offset}."
        )
