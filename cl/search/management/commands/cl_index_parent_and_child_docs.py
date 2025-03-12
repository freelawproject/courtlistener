from datetime import date
from itertools import batched
from typing import Iterable

from django.conf import settings
from django.db.models import QuerySet

from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.es_signal_processor import (
    check_fields_that_changed,
    get_fields_to_update,
)
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.people_db.models import Person
from cl.search.documents import (
    DocketDocument,
    ESRECAPDocument,
    OpinionClusterDocument,
    OpinionDocument,
    PersonDocument,
)
from cl.search.management.commands.sweep_indexer import get_es_doc_id
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
    index_parent_or_child_docs_in_es,
    remove_parent_and_child_docs_by_query,
    update_children_docs_by_query,
)
from cl.search.types import ESDocumentClassType, EventTable


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
        return f"es_{search_type}_{event_doc_type}_indexing:log"
    return f"es_{search_type}_indexing:log"


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
                    source__in=Docket.RECAP_SOURCES(),
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
        case EventTable.RECAP_DOCUMENT:
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
    events_to_update: QuerySet,
    search_type: str,
    event_doc_type: EventTable | None,
    chunk_size: int,
) -> tuple[list[int], list[tuple[int, list[str]]], list[int]]:
    """Determines the documents to update or remove based on changes in
    specified fields.

    :param events_to_update: A queryset of the event table instances to update.
    :param search_type: The search type related to the update/remove action.
    :param event_doc_type: An optional EventTable enum member specifying the
    document type to be processed.
    :param chunk_size: The number of items to retrieve from DB at a time.
    :return: A four tuple containing, a list of strings containing the fields
    to be updated, a list containing IDs of parent documents to update, a list
    containing IDs of child documents to update, a list containing IDs of
    documents to delete.
    """

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

        case SEARCH_TYPES.RECAP if event_doc_type == EventTable.RECAP_DOCUMENT:
            tracked_set = RECAPDocument.es_rd_field_tracker
            fields_map = recap_document_field_mapping["save"][RECAPDocument][
                "self"
            ]
            document_model = RECAPDocument
            related_child_name = ""

        case _:
            return [], [], []

    main_documents_to_update = []
    child_documents_to_update = []
    documents_to_delete = []
    event_ids = list(events_to_update.values_list("id", flat=True))
    event_ids_count = len(event_ids)
    processed_count = 0
    for event_ids_chunk in batched(event_ids, chunk_size):
        # Fetch event objects and current instances in bulk for the current
        # chunk, thereby minimizing database queries and mitigating memory
        # issues simultaneously.
        event_ids_list = list(event_ids_chunk)
        events_bulk = {
            event.id: event
            for event in events_to_update.filter(id__in=event_ids_list)
        }
        current_instances_bulk = document_model.objects.in_bulk(event_ids_list)
        for event_id in event_ids_list:
            event = events_bulk.get(event_id)
            current_instance = current_instances_bulk.get(event_id)
            if not current_instance:
                # The instance no longer exists in the database and needs to be
                # removed from the ES index.
                documents_to_delete.append(event_id)
                continue
            # Check each tracked field to determine if it has changed.
            changed_fields = check_fields_that_changed(
                current_instance, tracked_set, event
            )
            fields_to_update = get_fields_to_update(changed_fields, fields_map)
            if fields_to_update:
                # Append main documents that need to be updated.
                main_documents_to_update.append(event_id)
                if (
                    related_child_name
                    and getattr(current_instance, related_child_name).exists()
                ):
                    # Append child documents that need to be updated.
                    child_documents_to_update.append(
                        (event_id, fields_to_update)
                    )

        processed_count += len(event_ids_list)
        logger.info(
            "\rChecking documents to update:  {}/{} ({:.0%})".format(
                processed_count,
                event_ids_count,
                processed_count / event_ids_count,
            )
        )
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
            help="The document type to index, only 'parent' or 'child' documents. "
            "If not provided, parent and child documents will be indexed.",
        )
        parser.add_argument(
            "--update-from-event-tables",
            type=str,
            required=False,
            choices=[member for member in EventTable],
            help="The document type to update from event history tables. "
            "'search.Docket' for dockets, 'search.DocketEntry' for docket "
            "entries or 'search.RECAPDocument' for RECAP Documents.",
            default="",
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
        parser.add_argument(
            "--missing",
            action="store_true",
            help="Use this flag to only index documents missing in the index.",
        )
        parser.add_argument(
            "--non-null-field",
            type=str,
            required=False,
            choices=["ordering_key"],
            help="Include only documents where this field is not Null.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.options = options
        search_type = options["search_type"]
        document_type = options.get("document_type", None)
        chunk_size = self.options["chunk_size"]
        pk_offset = options["pk_offset"]
        auto_resume = options.get("auto_resume", False)
        update_from_event_tables = EventTable(
            options.get("update_from_event_tables", None)
        )
        if auto_resume:
            pk_offset = get_last_parent_document_id_processed(
                compose_redis_key(search_type, update_from_event_tables)
            )
            self.stdout.write(
                f"Auto-resume enabled starting indexing from ID: {pk_offset}."
            )
        start_date: date | None = options.get("start_date", None)
        end_date: date | None = options.get("end_date", None)
        non_null_field: str | None = options.get("non_null_field", None)

        es_document = None
        match search_type:
            case SEARCH_TYPES.PEOPLE:
                queryset = Person.objects.filter(
                    pk__gte=pk_offset, is_alias_of=None
                ).order_by("pk")
                q = [item.pk for item in queryset if item.is_judge]
                count = len(q)
                task_to_use = "index_parent_and_child_docs"
                es_document = PersonDocument
            case SEARCH_TYPES.RECAP:
                if update_from_event_tables and start_date and end_date:
                    # Get unique oldest events from history table.
                    queryset = get_unique_oldest_history_rows(
                        start_date,
                        end_date,
                        pk_offset,
                        update_from_event_tables,
                    )
                    self.index_documents_from_event_table(
                        queryset, SEARCH_TYPES.RECAP
                    )
                    return
                elif document_type == "child":
                    # Get Docket objects by pk_offset.
                    queryset = (
                        RECAPDocument.objects.filter(pk__gte=pk_offset)
                        .order_by("pk")
                        .values_list("pk", "docket_entry__docket_id")
                    )
                    task_to_use = "index_parent_or_child_docs_in_es"
                    es_document = ESRECAPDocument
                else:
                    queryset = (
                        Docket.objects.filter(
                            pk__gte=pk_offset,
                            source__in=Docket.RECAP_SOURCES(),
                        )
                        .order_by("pk")
                        .values_list("pk", flat=True)
                    )
                    task_to_use = "index_parent_and_child_docs"
                    if document_type == "parent":
                        task_to_use = "index_parent_or_child_docs_in_es"
                        es_document = DocketDocument
                q = queryset.iterator()
                count = queryset.count()

            case SEARCH_TYPES.OPINION:
                if document_type == "child":
                    filters = {"pk__gte": pk_offset}
                    # If non_null_field is not None use it as a filter
                    if non_null_field:
                        filters[f"{non_null_field}__isnull"] = False

                    queryset = (
                        Opinion.objects.filter(**filters)
                        .order_by("pk")
                        .values_list("pk", "cluster_id")
                    )
                    task_to_use = "index_parent_or_child_docs_in_es"
                    es_document = OpinionDocument
                else:
                    # Get Opinion Clusters objects by pk_offset.
                    queryset = (
                        OpinionCluster.objects.filter(pk__gte=pk_offset)
                        .order_by("pk")
                        .values_list("pk", flat=True)
                    )
                    task_to_use = "index_parent_and_child_docs"
                    if document_type == "parent":
                        task_to_use = "index_parent_or_child_docs_in_es"
                        es_document = OpinionClusterDocument

                q = queryset.iterator()
                count = queryset.count()

            case _:
                return

        self.process_queryset(
            q, count, search_type, chunk_size, task_to_use, es_document
        )

    def process_queryset(
        self,
        items: Iterable,
        count: int,
        search_type: str,
        chunk_size: int,
        task_to_use: str,
        es_document: ESDocumentClassType | None = None,
    ) -> None:
        """Process a queryset and execute tasks based on the specified celery
        task_to_use.

        :param items: Iterable of items to process. Items can be a simple
        iterable of IDs or a tuple of (ID, changed_fields) for cases requiring
        field changes.
        :param count: Total number of items expected to process.
        :param search_type: The search type related to the update/remove action.
        :param chunk_size: The number of items to process in a single chunk.
        :param task_to_use: The name of the celery task to execute.
        :param es_document: Optional: The ES document class for checking
        document existence in ES.
        :return: None
        """

        event_doc_type = EventTable(
            self.options.get("update_from_event_tables", "")
        )
        queue = self.options["queue"]
        testing_mode = self.options.get("testing_mode", False)
        pk_offset = self.options["pk_offset"]
        document_type = self.options.get("document_type", None)
        missing = self.options.get("missing", False)
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

        if event_doc_type == EventTable.RECAP_DOCUMENT:
            fields_map = recap_document_field_mapping["save"][RECAPDocument][
                "self"
            ]
            document_type = "child"

        chunk = []
        processed_count = 0
        throttle = CeleryThrottle(queue_name=queue)
        use_streaming_bulk = True if testing_mode else False
        # Indexing Parent and their child documents.
        for item in items:
            item_id = item
            changed_fields = []
            if missing and es_document:
                # If the "missing" flag is passed, check if the document
                # already exists in ES to avoid scheduling it for indexing.
                if isinstance(item, tuple):
                    item_id = item[0]
                    parent_document_id = item[1]
                else:
                    item_id = item
                    parent_document_id = item

                doc_id = get_es_doc_id(es_document, item_id)
                if not es_document.exists(
                    id=doc_id, routing=parent_document_id
                ):
                    chunk.append(item_id)
            else:
                if isinstance(item, tuple):
                    item_id, changed_fields = item
                chunk.append(item_id)
            processed_count += 1
            last_item = count == processed_count
            if processed_count % chunk_size == 0 or last_item:
                throttle.maybe_wait()
                match task_to_use:
                    case "index_parent_and_child_docs":
                        index_parent_and_child_docs.si(
                            chunk,
                            search_type,
                            use_streaming_bulk=True,
                        ).set(queue=queue).apply_async()

                    case "index_parent_or_child_docs_in_es":
                        index_parent_or_child_docs_in_es.si(
                            chunk,
                            search_type,
                            document_type,
                            use_streaming_bulk=use_streaming_bulk,
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
                        event_doc_type if event_doc_type else "",
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
        events_to_update: QuerySet,
        search_type: str,
    ) -> None:
        """Index documents that have changed based on the model history tables.

        :param events_to_update: A queryset of the event table instances to update
        :param search_type: The search type related to the update/remove action.
        :return: None
        """
        event_doc_type = EventTable(
            self.options.get("update_from_event_tables", "")
        )
        chunk_size = self.options["chunk_size"]
        (
            main_documents_to_update,
            child_documents_to_update,
            documents_to_delete,
        ) = get_documents_to_update_or_remove(
            events_to_update, search_type, event_doc_type, chunk_size
        )

        if event_doc_type == EventTable.DOCKET:
            # Process Docket documents to update.
            count = len(main_documents_to_update)
            self.process_queryset(
                main_documents_to_update,
                count,
                search_type,
                chunk_size,
                "index_parent_or_child_docs_in_es",
            )

        if event_doc_type == EventTable.RECAP_DOCUMENT:
            # Process RECAP documents to update.
            count = len(main_documents_to_update)
            self.process_queryset(
                main_documents_to_update,
                count,
                search_type,
                1,
                "index_parent_or_child_docs_in_es",
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
        if not event_doc_type == EventTable.RECAP_DOCUMENT:
            chunk_size = 1
        count = len(documents_to_delete)
        self.process_queryset(
            documents_to_delete,
            count,
            search_type,
            chunk_size,
            "remove_parent_and_child_docs_by_query",
        )
