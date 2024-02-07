from datetime import date, datetime
from typing import Iterable, Mapping

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet

from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.es_signal_processor import (
    check_fields_that_changed,
    get_fields_to_update,
)
from cl.lib.redis_utils import make_redis_interface
from cl.people_db.models import Person
from cl.search.documents import ESRECAPDocument
from cl.search.models import (
    SEARCH_TYPES,
    Docket,
    DocketEntry,
    DocketEntryEvent,
    DocketEvent,
    Opinion,
    OpinionCluster,
    RECAPDocument,
    RECAPDocumentEvent,
)
from cl.search.signals import recap_document_field_mapping
from cl.search.tasks import (
    index_parent_and_child_docs,
    index_parent_or_child_docs,
    remove_parent_and_child_docs_by_query,
    update_children_docs_by_query,
)
from cl.search.types import EventTable


def compose_redis_key(
    search_type: str, event_doc_type: EventTable | None = None
) -> str:
    """Compose a Redis key based on the search type for indexing log.

    :param search_type: The type of search.
    :param event_doc_type: An optional EventTable enum member specifying the
    document type being processed.
    :return: A Redis key as a string.
    """
    if event_doc_type:
        return f"es_{search_type}_{event_doc_type.value}_indexing:log"
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


def get_last_parent_document_id_processed(
    search_type: str, event_doc_type: EventTable | None = None
) -> int:
    """Get the last document ID indexed.

    :param search_type: The search type key to get the last document ID.
    :param event_doc_type: An optional EventTable enum member specifying the
    document type being processed.
    :return: The last document ID indexed.
    """

    r = make_redis_interface("CACHE")
    log_key = compose_redis_key(search_type, event_doc_type)
    stored_values = r.hgetall(log_key)
    last_document_id = int(stored_values.get("last_document_id", 0))

    return last_document_id


def get_unique_oldest_history_rows(
    start_date: date,
    end_date: date,
    pk_offset: int,
    update_from_event_tables: EventTable | None,
) -> QuerySet | None:
    """Retrieve the oldest unique history rows within a given date range for
    specified event tables.

    :param start_date: The start date for filtering the history rows.
    :param end_date: The end date for filtering the history rows.
    :param pk_offset: The PK offset to start from.
    :param update_from_event_tables: An optional EventTable member to specify
    the type of event table from which to retrieve history rows.
    :return: A QuerySet of the oldest unique events within the specified date
    range for the given event table, or None if no event table is specified.
    """

    oldest_unique_events = None
    match update_from_event_tables:
        case EventTable.DOCKET:
            oldest_unique_events = (
                DocketEvent.objects.filter(
                    pgh_id__gte=pk_offset,
                    pgh_created_at__gte=start_date,
                    pgh_created_at__lte=end_date,
                )
                .order_by("id", "pgh_created_at")
                .distinct("id")
            )
        case EventTable.DOCKET_ENTRY:
            oldest_unique_events = (
                DocketEntryEvent.objects.filter(
                    pgh_id__gte=pk_offset,
                    pgh_created_at__gte=start_date,
                    pgh_created_at__lte=end_date,
                )
                .order_by("id", "pgh_created_at")
                .distinct("id")
            )
        case EventTable.RECAP_DOC:
            oldest_unique_events = (
                RECAPDocumentEvent.objects.filter(
                    pgh_id__gte=pk_offset,
                    pgh_created_at__gte=start_date,
                    pgh_created_at__lte=end_date,
                )
                .order_by("id", "pgh_created_at")
                .distinct("id")
            )
    return oldest_unique_events


def get_documents_to_update_or_remove(
    iterable: Iterable, search_type: str, event_doc_type: EventTable | None
) -> tuple[list[int], list[tuple[int, list[str]]], list[int]]:
    """Determines the documents to update or remove based on changes in
    specified fields.

    :param iterable: An iterable of the event table instances.
    :param search_type: The search type related to the update/remove action.
    :param event_doc_type: An optional EventTable enum member specifying the
    document type to be processed.
    :return: A four tuple containing, a list of strings containing the fields
    to be updated, a list containing IDs of parent documents to update, a list
    containing IDs of child documents to update, a list containing IDs of
    documents to delete.
    """

    main_documents_to_update = []
    child_documents_to_update = []
    documents_to_delete = []
    match search_type:
        case SEARCH_TYPES.RECAP if event_doc_type == EventTable.DOCKET:
            tracked_set = Docket.es_rd_field_tracker
            fields_map = recap_document_field_mapping["save"][Docket][
                "docket_entry__docket"
            ]
            document_model = Docket
            related_child_name = "docket_entries"

        case SEARCH_TYPES.RECAP if event_doc_type == EventTable.DOCKET_ENTRY:
            tracked_set = DocketEntry.es_rd_field_tracker
            fields_map = recap_document_field_mapping["save"][DocketEntry][
                "docket_entry"
            ]
            document_model = DocketEntry
            related_child_name = "recap_documents"

        case SEARCH_TYPES.RECAP if event_doc_type == EventTable.RECAP_DOC:
            tracked_set = RECAPDocument.es_rd_field_tracker
            fields_map = recap_document_field_mapping["save"][RECAPDocument][
                "self"
            ]
            document_model = RECAPDocument
            related_child_name = ""

        case _:
            return [], [], []

    for event in iterable:
        try:
            current_instance = document_model.objects.get(pk=event.id)
        except ObjectDoesNotExist:
            # The document needs to be removed from the ES index.
            documents_to_delete.append(event.id)
            continue

        # Check each tracked field to determine if it has changed.
        changed_fields = check_fields_that_changed(
            current_instance, tracked_set, event
        )
        fields_to_update = get_fields_to_update(changed_fields, fields_map)
        if fields_to_update:
            # Append main documents that need to be updated.
            main_documents_to_update.append(event.id)
            if (
                related_child_name
                and getattr(current_instance, related_child_name).exists()
            ):
                # Append child documents that need to be updated.
                child_documents_to_update.append((event.id, fields_to_update))

    return (
        main_documents_to_update,
        child_documents_to_update,
        documents_to_delete,
    )


class Command(VerboseCommand):
    help = "Index existing Parent and Children docs into Elasticsearch."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = {}

    def add_arguments(self, parser):
        parser.add_argument(
            "--search-type",
            type=str,
            required=True,
            choices=[
                SEARCH_TYPES.PEOPLE,
                SEARCH_TYPES.RECAP,
                SEARCH_TYPES.OPINION,
            ],
            help=f"The search type models to index: ({', '.join([SEARCH_TYPES.PEOPLE, SEARCH_TYPES.RECAP, SEARCH_TYPES.OPINION])})",
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
        parser.add_argument(
            "--document-type",
            type=str,
            required=False,
            choices=["parent", "child"],
            help=f"The document type to index, only 'parent' or 'child' documents. "
            f"If not provided, parent and child documents will be indexed.",
        )
        parser.add_argument(
            "--update-from-event-tables",
            type=str,
            required=False,
            choices=[member.value for member in EventTable],
            help=f"The document type to update from event history tables. "
            f"'docket' for dockets, 'de' for docket entries or 'rd' for "
            f"RECAP Documents.",
        )
        parser.add_argument(
            "--start-date",
            type=valid_date_time,
            help="Start date in ISO-8601 format for a range of documents to "
            "update.",
        )
        parser.add_argument(
            "--end-date",
            type=valid_date_time,
            help="Start date in ISO-8601 format for a range of documents to "
            "update.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.options = options
        search_type = options["search_type"]
        document_type = options.get("document_type", None)
        chunk_size = self.options["chunk_size"]
        pk_offset = options["pk_offset"]
        auto_resume = options.get("auto_resume", False)
        update_from_event_tables = EventTable.get_member(
            options.get("update_from_event_tables", None)
        )
        if auto_resume:
            pk_offset = get_last_parent_document_id_processed(
                search_type, update_from_event_tables
            )
            self.stdout.write(
                f"Auto-resume enabled starting indexing from ID: {pk_offset}."
            )
        start_date: date | None = options.get("start_date", None)
        end_date: date | None = options.get("end_date", None)

        match search_type:
            case SEARCH_TYPES.PEOPLE:
                queryset = Person.objects.filter(
                    pk__gte=pk_offset, is_alias_of=None
                ).order_by("pk")
                q = [item.pk for item in queryset if item.is_judge]
                count = len(q)
                task_to_use = "index_parent_and_child_docs"
            case SEARCH_TYPES.RECAP:
                if update_from_event_tables and start_date and end_date:
                    # Get unique oldest events from history table.
                    queryset = get_unique_oldest_history_rows(
                        start_date,
                        end_date,
                        pk_offset,
                        update_from_event_tables,
                    )
                    q = queryset.iterator()
                    self.index_documents_from_event_table(
                        q, SEARCH_TYPES.RECAP
                    )
                    return
                elif document_type == "child":
                    # Get Docket objects by pk_offset.
                    queryset = (
                        RECAPDocument.objects.filter(pk__gte=pk_offset)
                        .order_by("pk")
                        .values_list("pk", flat=True)
                    )
                    task_to_use = "index_parent_or_child_docs"
                else:
                    queryset = (
                        Docket.objects.filter(pk__gte=pk_offset)
                        .order_by("pk")
                        .values_list("pk", flat=True)
                    )
                    task_to_use = "index_parent_and_child_docs"
                    if document_type == "parent":
                        task_to_use = "index_parent_or_child_docs"

                q = queryset.iterator()
                count = queryset.count()

            case SEARCH_TYPES.OPINION:
                if document_type == "child":
                    queryset = (
                        Opinion.objects.filter(pk__gte=pk_offset)
                        .order_by("pk")
                        .values_list("pk", flat=True)
                    )
                    task_to_use = "index_parent_or_child_docs"
                else:
                    # Get Opinion Clusters objects by pk_offset.
                    queryset = (
                        OpinionCluster.objects.filter(pk__gte=pk_offset)
                        .order_by("pk")
                        .values_list("pk", flat=True)
                    )
                    task_to_use = "index_parent_and_child_docs"
                    if document_type == "parent":
                        task_to_use = "index_parent_or_child_docs"

                q = queryset.iterator()
                count = queryset.count()

            case _:
                return

        self.process_queryset(q, count, search_type, chunk_size, task_to_use)

    def process_queryset(
        self,
        iterable,
        count,
        search_type,
        chunk_size,
        task_to_use: str,
    ):
        event_doc_type = EventTable.get_member(
            self.options.get("update_from_event_tables", None)
        )
        queue = self.options["queue"]
        testing_mode = self.options.get("testing_mode", False)
        pk_offset = self.options["pk_offset"]
        document_type = self.options.get("document_type", None)

        fields_map = {}
        if event_doc_type == EventTable.DOCKET:
            fields_map = recap_document_field_mapping["save"][Docket][
                "docket_entry__docket"
            ]
            document_type = "parent"

        if event_doc_type == EventTable.DOCKET_ENTRY:
            fields_map = recap_document_field_mapping["save"][DocketEntry][
                "docket_entry"
            ]

        if event_doc_type == EventTable.RECAP_DOC:
            fields_map = recap_document_field_mapping["save"][RECAPDocument][
                "self"
            ]
            document_type = "child"

        chunk = []
        processed_count = 0
        throttle = CeleryThrottle(queue_name=queue)
        # Indexing Parent and their child documents.
        for item in iterable:
            item_id = item
            changed_fields = []
            if isinstance(item, tuple):
                item_id, changed_fields = item
            processed_count += 1
            last_item = count == processed_count
            chunk.append(item_id)
            if processed_count % chunk_size == 0 or last_item:
                throttle.maybe_wait()

                match task_to_use:
                    case "index_parent_and_child_docs":
                        index_parent_and_child_docs.si(
                            chunk, search_type, testing_mode=testing_mode
                        ).set(queue=queue).apply_async()

                    case "index_parent_or_child_docs":
                        index_parent_or_child_docs.si(
                            chunk,
                            search_type,
                            document_type,
                            testing_mode=testing_mode,
                        ).set(queue=queue).apply_async()
                    case "remove_parent_and_child_docs_by_query":
                        remove_parent_and_child_docs_by_query.si(
                            ESRECAPDocument.__name__, chunk, event_doc_type
                        ).set(queue=queue).apply_async()
                    case "update_children_docs_by_query":
                        update_children_docs_by_query.si(
                            ESRECAPDocument.__name__,
                            item_id,
                            changed_fields,
                            fields_map,
                            event_doc_type,
                        ).set(queue=queue).apply_async()

                chunk = []

                self.stdout.write(
                    "\rProcessed {}/{}, ({:.0%}), last {} PK indexed: {},".format(
                        processed_count,
                        count,
                        processed_count * 1.0 / count,
                        event_doc_type.value if event_doc_type else "",
                        item_id,
                    )
                )
                if not processed_count % 1000:
                    # Log every 1000 parent documents processed.
                    log_last_document_indexed(
                        item_id, compose_redis_key(search_type, event_doc_type)
                    )
            self.stdout.write(
                f"Successfully indexed {processed_count} items from pk {pk_offset}."
            )

    def index_documents_from_event_table(
        self,
        iterable: Iterable,
        search_type: str,
    ) -> None:
        """Index documents that have changed based on the model history tables.

        :param iterable: An iterable of the event table instances.
        :param search_type: The search type related to the update/remove action.
        :return: None
        """
        event_doc_type = EventTable.get_member(
            self.options.get("update_from_event_tables", None)
        )
        chunk_size = self.options["chunk_size"]
        (
            main_documents_to_update,
            child_documents_to_update,
            documents_to_delete,
        ) = get_documents_to_update_or_remove(
            iterable, search_type, event_doc_type
        )

        if event_doc_type == EventTable.DOCKET:
            # Process Docket documents to update.
            count = len(main_documents_to_update)
            self.process_queryset(
                main_documents_to_update,
                count,
                search_type,
                chunk_size,
                "index_parent_or_child_docs",
            )

        if event_doc_type == EventTable.RECAP_DOC:
            # Process RECAP documents to update.
            count = len(main_documents_to_update)
            self.process_queryset(
                main_documents_to_update,
                count,
                search_type,
                1,
                "index_parent_or_child_docs",
            )

        # Process child documents to update.
        count = len(child_documents_to_update)
        self.process_queryset(
            child_documents_to_update,
            count,
            search_type,
            1,
            "update_children_docs_by_query",
        )
        # Process parent and child documents to remove.
        # Remove multiple RECAPDocuments at once according to the chunk size.
        # Otherwise, remove one element at a time for main documents with children.
        if not event_doc_type == EventTable.RECAP_DOC:
            chunk_size = 1
        count = len(documents_to_delete)
        self.process_queryset(
            documents_to_delete,
            count,
            search_type,
            chunk_size,
            "remove_parent_and_child_docs_by_query",
        )
