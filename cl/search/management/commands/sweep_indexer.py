from datetime import datetime
from typing import Iterable, Literal, Mapping, cast

from django.apps import apps
from django.conf import settings
from django.db.models import QuerySet

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
from cl.search.models import SEARCH_TYPES, Docket, Opinion, RECAPDocument
from cl.search.tasks import (
    index_parent_and_child_docs,
    index_parent_or_child_docs,
)
from cl.search.types import ESDocumentClassType

supported_models = [
    "audio.Audio",
    "people_db.Person",
    "search.OpinionCluster",
    "search.Opinion",
    "search.Docket",
    "search.RECAPDocument",
]
r = get_redis_interface("CACHE")


def compose_indexer_redis_key() -> str:
    """Compose the redis key for the sweep indexer
    :return: A Redis key as a string.
    """
    return "es_sweep_indexer:log"


def log_indexer_last_status(
    model_name: str, document_pk: int, chunk_size: int
) -> Mapping[str, int | str]:
    """Log the sweep indexer last status to Redis.

    :param model_name: The document name being processed.
    :param document_pk: The last document_id processed.
    :param chunk_size: The last chunk size being processed.
    :return: The data logged to redis.
    """

    log_key = compose_indexer_redis_key()
    stored_values = r.hgetall(log_key)
    # Build the documents key containing the documents indexed dynamically.
    documents_dict = {model: 0 for model in supported_models}
    for model in supported_models:
        current_total = int(stored_values.get(model, 0))
        if model_name == model:
            current_total = chunk_size + current_total
        documents_dict[model] = current_total

    data_to_log = {
        "model_name": model_name,
        "last_document_id": document_pk,
        "date_time": datetime.now().isoformat(),
    }
    data_to_log.update(documents_dict)
    log_info = cast(Mapping[str, int | str], data_to_log)
    r.hset(log_key, mapping=log_info)
    return log_info


def get_last_document_processed() -> tuple[str, int]:
    """Get the last model_name and ID indexed from Redis.
    :return: The last document name and ID indexed.
    """

    log_key = compose_indexer_redis_key()
    stored_values = r.hgetall(log_key)
    model_name = str(stored_values.get("model_name", ""))
    last_document_id = int(stored_values.get("last_document_id", 0))

    return model_name, last_document_id


def get_documents_processed_count_and_restart() -> dict[str, int]:
    """Retrieve the number of documents processed and delete the Redis key to
     start a new indexing cycle.

    :return: A dict containing the number of documents processed of each type.
    """

    log_key = compose_indexer_redis_key()
    stored_values = r.hgetall(log_key)

    # Retrieve the number of documents processed.
    documents_processed = {}
    for document in supported_models:
        documents_processed[document] = int(stored_values.get(document, 0))

    keys = r.keys(log_key)
    if keys:
        r.delete(*keys)
    return documents_processed


def find_starting_model(target_model: str) -> int | None:
    """Find the index of a model in the list whose name matches the target
    name.

    :param target_model: The name of the model to find.
    :return: The index of the model if found, otherwise None.
    """

    try:
        return supported_models.index(target_model)
    except ValueError:
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


def build_parent_model_queryset(
    app_label: str, last_document_id: int
) -> QuerySet:
    """
    Build a queryset for the parent model starting from the last document ID.

    :param app_label: The label of the app to which the model belongs.
    :param last_document_id: The instance ID from which to start the queryset.
    :return: A QuerySet that retrieves only IDs values.
    """
    model = apps.get_model(app_label)
    query_args: dict[str, int] = {"pk__gte": last_document_id}
    if model == Docket:
        # If the model is Docket, incorporate a source filter to only match
        # Dockets that belong to the RECAP collection.
        query_args["source__in"] = Docket.RECAP_SOURCES
    queryset = (
        model.objects.filter(**query_args)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    return queryset


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
            self.stdout.write("Starting a new sweep indexer cycle.")
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

        model_name, last_document_id = get_last_document_processed()
        start_model_index = find_starting_model(model_name)
        if start_model_index is not None and last_document_id:
            # create a sub-list from the start model to the end, then reverse
            # it to process it as a stack.
            models_stack = supported_models[start_model_index:][::-1]
            self.process_model_stack(models_stack, last_document_id)
        else:
            # Copy and reverse supported_models to process it as a stack.
            models_stack = supported_models[::-1]
            self.process_model_stack(models_stack)

    def process_model_stack(
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

        parent: Literal["parent", "child"] = "parent"
        child: Literal["parent", "child"] = "child"
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
                    task_params = (
                        parent,
                        SEARCH_TYPES.PEOPLE,
                        PersonDocument,
                    )
                case "search.Opinion":
                    queryset = (
                        Opinion.objects.filter(pk__gte=last_document_id)
                        .order_by("pk")
                        .values_list("pk", "cluster_id")
                    )
                    count = Opinion.objects.filter(
                        pk__gte=last_document_id
                    ).count()
                    q = queryset.iterator()
                    task_params = (
                        child,
                        SEARCH_TYPES.OPINION,
                        OpinionDocument,
                    )
                case "search.RECAPDocument":
                    queryset = (
                        RECAPDocument.objects.filter(pk__gte=last_document_id)
                        .order_by("pk")
                        .values_list("pk", "docket_entry__docket_id")
                    )
                    count = RECAPDocument.objects.filter(
                        pk__gte=last_document_id
                    ).count()
                    q = queryset.iterator()
                    task_params = (
                        child,
                        SEARCH_TYPES.RECAP,
                        ESRECAPDocument,
                    )
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
                    task_params = (
                        parent,
                        SEARCH_TYPES.ORAL_ARGUMENT,
                        AudioDocument,
                    )
                case "search.OpinionCluster":
                    queryset = build_parent_model_queryset(
                        app_label, last_document_id
                    )
                    q = queryset.iterator()
                    count = queryset.count()
                    task_params = (
                        parent,
                        SEARCH_TYPES.OPINION,
                        OpinionClusterDocument,
                    )
                case "search.Docket":
                    queryset = build_parent_model_queryset(
                        app_label, last_document_id
                    )
                    q = queryset.iterator()
                    count = queryset.count()
                    task_params = (
                        parent,
                        SEARCH_TYPES.RECAP,
                        DocketDocument,
                    )

                case _:
                    continue

            self.process_queryset(
                q, count, app_label, task_to_use, task_params
            )
            #  After finishing each model, restart last_document_id to start
            # from the ID 0 in the next model.
            last_document_id = 0

    def process_queryset(
        self,
        items: Iterable,
        count: int,
        app_label: str,
        task_to_use: str,
        task_params: tuple[
            Literal["parent", "child"], str, ESDocumentClassType
        ],
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
        :param task_params: A three tuple containing the task params, the
        document_type 'parent' or 'child', the Search type and the ES document
        class.
        :return: None
        """
        testing_mode = self.options.get("testing_mode", False)
        chunk = []
        processed_count = 0
        accumulated_chunk = 0
        throttle = CeleryThrottle(
            poll_interval=self.poll_interval,
            min_items=self.chunk_size,
            queue_name=self.queue,
        )
        document_type, search_type, es_document = task_params
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
                )
                # Restart accumulated_chunk
                accumulated_chunk = 0
