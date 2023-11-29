from datetime import datetime
from typing import Iterable, Mapping

from django.conf import settings

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.redis_utils import make_redis_interface
from cl.people_db.models import Person
from cl.search.models import SEARCH_TYPES, Docket
from cl.search.tasks import index_parent_and_child_docs


def compose_redis_key(search_type: str) -> str:
    """Compose a Redis key based on the search type for indexing log.

    :param search_type: The type of search.
    :return: A Redis key as a string.
    """
    return f"es_{search_type}_indexing:log"


def log_last_document_indexed(
    document_pk: int, log_key: str
) -> Mapping[str | bytes, int | str]:
    """Log the last document_id indexed.

    :param document_pk: The last document_id processed.
    :param log_key: The log key to use in redis.
    :return: The data logged to redis.
    """

    r = make_redis_interface("CACHE")
    pipe = r.pipeline()
    pipe.hgetall(log_key)
    log_info: Mapping[str | bytes, int | str] = {
        "last_document_id": document_pk,
        "date_time": datetime.now().isoformat(),
    }
    pipe.hset(log_key, mapping=log_info)
    pipe.expire(log_key, 60 * 60 * 24 * 28)  # 4 weeks
    pipe.execute()

    return log_info


def get_last_parent_document_id_processed(search_type: str) -> int:
    """Get the last document ID indexed.

    :param search_type: The search type key to get the last document ID.
    :return: The last document ID indexed.
    """

    r = make_redis_interface("CACHE")
    log_key = compose_redis_key(search_type)
    stored_values = r.hgetall(log_key)
    last_document_id = int(stored_values.get("last_document_id", 0))

    return last_document_id


class Command(VerboseCommand):
    help = "Index existing Parent and Children docs into Elasticsearch."

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.options = {}

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
        parser.add_argument(
            "--auto-resume",
            action="store_true",
            help="Auto resume the command using the last document_id logged in Redis. "
            "If --pk-offset is provided, it'll be ignored.",
        )
        parser.add_argument(
            "--testing-mode",
            action="store_true",
            help="Use this flag only when running the command in tests based on TestCase",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.options = options
        search_type = options["search_type"]
        auto_resume = options.get("auto_resume", False)

        pk_offset = options["pk_offset"]
        if auto_resume:
            pk_offset = get_last_parent_document_id_processed(search_type)
            self.stdout.write(
                f"Auto-resume enabled starting indexing from ID: {pk_offset}."
            )

        match search_type:
            case SEARCH_TYPES.PEOPLE:
                queryset = Person.objects.filter(
                    pk__gte=pk_offset, is_alias_of=None
                ).order_by("pk")
                q = [item.pk for item in queryset if item.is_judge]
                count = len(q)
                self.process_queryset(q, count, SEARCH_TYPES.PEOPLE, pk_offset)
            case SEARCH_TYPES.RECAP:
                # Get Docket objects by pk_offset.
                queryset = (
                    Docket.objects.filter(pk__gte=pk_offset)
                    .order_by("pk")
                    .values_list("pk", flat=True)
                )
                q = queryset.iterator()
                count = queryset.count()
                self.process_queryset(q, count, SEARCH_TYPES.RECAP, pk_offset)

    def process_queryset(
        self,
        iterable: Iterable,
        count: int,
        search_type: str,
        pk_offset: int,
    ) -> None:
        queue = self.options["queue"]
        chunk_size = self.options["chunk_size"]
        testing_mode = self.options.get("testing_mode", False)

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
                index_parent_and_child_docs.si(
                    chunk, search_type, testing_mode=testing_mode
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
                log_last_document_indexed(
                    item_id, compose_redis_key(search_type)
                )
        self.stdout.write(
            f"Successfully indexed {processed_count} items from pk {pk_offset}."
        )
