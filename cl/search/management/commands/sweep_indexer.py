from datetime import datetime
from typing import Iterable, Mapping, cast

from django.apps import apps
from django.conf import settings

from cl.audio.models import Audio
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.redis_utils import get_redis_interface
from cl.people_db.models import Person
from cl.search.documents import (
    ES_CHILD_ID,
    AudioDocument,
    DocketDocument,
    ESRECAPDocument,
    OpinionClusterDocument,
    OpinionDocument,
    PersonDocument,
)
from cl.search.models import SEARCH_TYPES, Opinion, RECAPDocument
from cl.search.tasks import (
    index_parent_and_child_docs,
    index_parent_or_child_docs,
)
from cl.search.types import ESDocumentClassType

list_supported_models = [
    "audio.Audio",
    "people_db.Person",
    "search.OpinionCluster",
    "search.Opinion",
    "search.Docket",
    "search.RECAPDocument",
]


def compose_indexer_redis_key() -> str:
    """Compose the redis key for the sweep indexer
    :return: A Redis key as a string.
    """
    return f"es_sweep_indexer:log"


def log_indexer_last_status(
    document_name: str, document_pk: int, chunk_size: int, log_key: str
) -> Mapping[str | bytes, int | str]:
    """Log the sweep indexer last status to Redis.

    :param document_name: The document name being processed.
    :param document_pk: The last document_id processed.
    :param chunk_size: The last chunk size being processed.
    :param log_key: The log key to use in redis.
    :return: The data logged to redis.
    """

    r = get_redis_interface("CACHE")
    pipe = r.pipeline()
    pipe.hgetall(log_key)
    stored_values = pipe.execute()

    # Build the documents key containing the documents indexed dynamically.
    documents_dict = {model: 0 for model in list_supported_models}
    for document in list_supported_models:
        current_total = int(stored_values[0].get(document, 0))
        if document_name == document:
            current_total = chunk_size + current_total
        documents_dict[document] = current_total

    data_to_log = {
        "document_name": document_name,
        "last_document_id": document_pk,
        "date_time": datetime.now().isoformat(),
    }
    data_to_log.update(documents_dict)
    log_info = cast(Mapping[str | bytes, int | str], data_to_log)
    pipe.hset(log_key, mapping=log_info)
    pipe.execute()
    return log_info


def get_last_document_processed() -> tuple[str, int]:
    """Get the last document_name and ID indexed from Redis.
    :return: The last document name and ID indexed.
    """
    r = get_redis_interface("CACHE")
    log_key = compose_indexer_redis_key()
    stored_values = r.hgetall(log_key)
    document_name = str(stored_values.get("document_name", ""))
    last_document_id = int(stored_values.get("last_document_id", 0))

    return document_name, last_document_id


def get_documents_processed_count_and_restart() -> dict[str, int]:
    """Retrieve the number of documents processed and delete the Redis key to
     start a new indexing cycle.

    :return: A dict containing the number of documents processed of each type.
    """

    r = get_redis_interface("CACHE")
    log_key = compose_indexer_redis_key()
    stored_values = r.hgetall(log_key)

    # Retrieve the number of documents processed dinamically.
    documents_processed = {}
    for document in list_supported_models:
        documents_processed[document] = int(stored_values.get(document, 0))

    keys = r.keys(log_key)
    if keys:
        r.delete(*keys)
    return documents_processed


def find_starting_model(models: list[str], target_model: str) -> int | None:
    """Find the index of a model in the list whose name matches the target
    name.

    :param models: List of supported models name.
    :param target_model: The name of the model to find.
    :return: The index of the model if found, otherwise None.
    """

    for index, model_name in enumerate(models):
        if model_name == target_model:
            return index
    return None


def get_es_doc_id(es_document: ESDocumentClassType, instance_id: int) -> int:
    """Retrieve the Elasticsearch document ID according to their es_document.

    :param es_document: The ES document class type.
    :param instance_id: The DB instance ID related to the ES document.
    :return: A two-tuple containing the Elasticsearch document ID and the
    parent ID.
    """

    if es_document is ESRECAPDocument:
        doc_id = ES_CHILD_ID(instance_id).RECAP
    elif es_document is OpinionDocument:
        doc_id = ES_CHILD_ID(instance_id).OPINION
    else:
        doc_id = instance_id
    return doc_id


class Command(VerboseCommand):
    help = "Sweep indexer for Elasticsearch documents."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = {}
        self.sweep_indexer_action = settings.ELASTICSEARCH_SWEEP_INDEXER_ACTION
        self.queue = settings.ELASTICSEARCH_SWEEP_INDEXER_QUEUE
        self.chunk_size = settings.ELASTICSEARCH_SWEEP_INDEXER_CHUNK_SIZE
        self.poll_interval = settings.ELASTICSEARCH_SWEEP_INDEXER_POLL_INTERVAL

    def add_arguments(self, parser):
        parser.add_argument(
            "--testing-mode",
            action="store_true",
            help="Use this flag only when running the command in tests based on TestCase",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.options = options

        testing_mode = self.options.get("testing_mode", False)
        while True:
            self.stdout.write(f"Starting a new sweep indexer cycle.")
            self.execute_sweep_indexer_cycle()
            document_counts = get_documents_processed_count_and_restart()
            self.stdout.write(
                f"\rSweep indexer '{self.sweep_indexer_action}' cycle finished successfully."
            )
            logger.info(f"\rDocuments Indexed: {document_counts}")
            if testing_mode:
                # Only execute one cycle for testing purposes.
                break

    def execute_sweep_indexer_cycle(self) -> None:
        """Executes a sweep indexing cycle by processing documents starting
        from the last processed document, if it's stored, or starting from
        scratch if the command initiates a new cycle.

        :return: None
        """

        document_name, last_document_id = get_last_document_processed()
        start_model_index = find_starting_model(
            list_supported_models, document_name
        )
        if start_model_index is not None and last_document_id:
            # create a sub-list from the start model to the end, then reverse
            # it to process it as a stack.
            models_stack = list_supported_models[start_model_index:][::-1]
            self.process_documents(models_stack, last_document_id)
        else:
            # Copy and reverse list_supported_models to process it as a stack.
            models_stack = list_supported_models[::-1]
            self.process_documents(models_stack)

    def process_documents(
        self, models_stack: list[str], last_document_id: int = 0
    ) -> None:
        """Processes models names and documents serially for indexing by
        iterating over the stack of model names.

        :param models_stack: A list of model names to be processed for indexing
        :param last_document_id: An optional integer indicating the last
        document ID processed, allowing the command to continue from where it
        left off. Defaults to 0.
        :return:None
        """
        while models_stack:
            app_label = models_stack.pop()
            task_to_use = "index_parent_or_child_docs"
            match app_label:
                case "people_db.Person":
                    queryset = (
                        Person.objects.prefetch_related("positions")
                        .filter(pk__gte=last_document_id, is_alias_of=None)
                        .order_by("pk")
                    )
                    q = [item.pk for item in queryset if item.is_judge]
                    count = len(q)
                    task_to_use = "index_parent_and_child_docs"
                case "search.Opinion":
                    queryset = (
                        Opinion.objects.filter(pk__gte=last_document_id)
                        .order_by("pk")
                        .values_list("pk", "cluster_id")
                    )
                    count = queryset.count()
                    q = queryset.iterator()
                case "search.RECAPDocument":
                    queryset = (
                        RECAPDocument.objects.filter(pk__gte=last_document_id)
                        .order_by("pk")
                        .values_list("pk", "docket_entry__docket_id")
                    )
                    count = queryset.count()
                    q = queryset.iterator()
                case "audio.Audio":
                    queryset = (
                        Audio.objects.filter(
                            pk__gte=last_document_id, processing_complete=True
                        )
                        .order_by("pk")
                        .values_list("pk", flat=True)
                    )
                    count = queryset.count()
                    q = queryset.iterator()
                case _:
                    # Base case for non parent-child documents type.
                    model = apps.get_model(app_label)
                    queryset = (
                        model.objects.filter(pk__gte=last_document_id)
                        .order_by("pk")
                        .values_list("pk", flat=True)
                    )
                    count = queryset.count()
                    q = queryset.iterator()

            self.process_queryset(q, count, app_label, task_to_use)
            #  After finishing each model, restart last_document_id to start
            # from the ID 0 in the next model.
            last_document_id = 0

    def process_queryset(
        self,
        items: Iterable,
        count: int,
        app_label: str,
        task_to_use: str,
    ) -> None:
        """Process a queryset and execute tasks based on the specified indexing
        task_to_use.

        :param items: Iterable of items to process. Items can be a simple
        iterable of IDs or a tuple of (ID, changed_fields) for cases requiring
        field changes.
        :param count: Total number of items expected to process.
        :param app_label: The app label and model that belongs to the queryset
        being indexed.
        :param task_to_use: The name of the celery task to execute.
        :return: None
        """
        testing_mode = self.options.get("testing_mode", False)
        model_options = {
            "audio.Audio": {
                "type": "parent",
                "search_type": SEARCH_TYPES.ORAL_ARGUMENT,
                "es_document": AudioDocument,
            },
            "people_db.Person": {
                "type": "parent",
                "search_type": SEARCH_TYPES.PEOPLE,
                "es_document": PersonDocument,
            },
            "search.OpinionCluster": {
                "type": "parent",
                "search_type": SEARCH_TYPES.OPINION,
                "es_document": OpinionClusterDocument,
            },
            "search.Opinion": {
                "type": "child",
                "search_type": SEARCH_TYPES.OPINION,
                "es_document": OpinionDocument,
            },
            "search.Docket": {
                "type": "parent",
                "search_type": SEARCH_TYPES.RECAP,
                "es_document": DocketDocument,
            },
            "search.RECAPDocument": {
                "type": "child",
                "search_type": SEARCH_TYPES.RECAP,
                "es_document": ESRECAPDocument,
            },
        }
        document_type = model_options[app_label].get("type")
        search_type = model_options[app_label].get("search_type")
        es_document = model_options[app_label].get("es_document")
        chunk = []
        processed_count = 0
        accumulated_chunk = 0
        throttle = CeleryThrottle(
            poll_interval=self.poll_interval,
            min_items=self.chunk_size,
            queue_name=self.queue,
        )
        for item in items:
            if isinstance(item, tuple):
                item_id = item[0]
                parent_document_id = item[1]
            else:
                item_id = item
                parent_document_id = item

            processed_count += 1
            last_item = count == processed_count
            if es_document and self.sweep_indexer_action == "missing":
                doc_id = get_es_doc_id(es_document, item_id)
                if not es_document.exists(
                    id=doc_id, routing=parent_document_id
                ):
                    chunk.append(item_id)
            else:
                chunk.append(item_id)
            if processed_count % self.chunk_size == 0 or last_item:
                throttle.maybe_wait()
                match task_to_use:
                    case "index_parent_and_child_docs":
                        index_parent_and_child_docs.si(
                            chunk, search_type, testing_mode=testing_mode
                        ).set(queue=self.queue).apply_async()

                    case "index_parent_or_child_docs":
                        index_parent_or_child_docs.si(
                            chunk,
                            search_type,
                            document_type,
                            testing_mode=testing_mode,
                        ).set(queue=self.queue).apply_async()

                accumulated_chunk += len(chunk)
                self.stdout.write(
                    "\rProcessed {}/{}, ({:.0%}), last {} PK indexed: {},".format(
                        processed_count,
                        count,
                        processed_count * 1.0 / count,
                        app_label,
                        item_id,
                    )
                )
                chunk = []

            if not processed_count % 1000 or last_item:
                # Log every 1000 parent documents processed.
                log_indexer_last_status(
                    app_label,
                    item_id,
                    accumulated_chunk,
                    compose_indexer_redis_key(),
                )
                # Restart accumulated_chunk
                accumulated_chunk = 0
