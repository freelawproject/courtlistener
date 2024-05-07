import logging
import socket
from datetime import date, timedelta
from importlib import import_module
from random import randint
from typing import Any, Generator

import scorched
import waffle
from celery import Task
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Prefetch, QuerySet
from django.utils.timezone import now
from elasticsearch.exceptions import (
    ApiError,
    ConflictError,
    ConnectionError,
    ConnectionTimeout,
    NotFoundError,
    RequestError,
)
from elasticsearch.helpers import (
    BulkIndexError,
    bulk,
    parallel_bulk,
    streaming_bulk,
)
from elasticsearch_dsl import Document, Q, UpdateByQuery, connections
from requests import Session
from scorched.exc import SolrError

from cl.audio.models import Audio
from cl.celery_init import app
from cl.lib.elasticsearch_utils import build_daterange_query
from cl.lib.search_index_utils import InvalidDocumentError
from cl.people_db.models import Person, Position
from cl.search.documents import (
    ES_CHILD_ID,
    AudioDocument,
    DocketDocument,
    ESRECAPDocument,
    OpinionClusterDocument,
    OpinionDocument,
    PersonDocument,
    PositionDocument,
)
from cl.search.models import (
    SEARCH_TYPES,
    Docket,
    DocketEntry,
    DocketEvent,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    OpinionsCitedByRECAPDocument,
    RECAPDocument,
)
from cl.search.types import (
    ESDictDocument,
    ESDocumentClassType,
    ESDocumentInstanceType,
    ESDocumentNameType,
    ESModelClassType,
    ESModelType,
    EventTable,
    SaveDocumentResponseType,
)

models_alert_support = [Audio]

logger = logging.getLogger(__name__)

es_document_module = import_module("cl.search.documents")


@app.task
def add_items_to_solr(item_pks, app_label, force_commit=False):
    """Add a list of items to Solr

    :param item_pks: An iterable list of item PKs that you wish to add to Solr.
    :param app_label: The type of item that you are adding.
    :param force_commit: Whether to send a commit to Solr after your addition.
    This is generally not advised and is mostly used for testing.
    """
    search_dicts = []
    model = apps.get_model(app_label)
    items = model.objects.filter(pk__in=item_pks).order_by()
    for item in items:
        try:
            if model in [OpinionCluster, Docket]:
                # Dockets make a list of items; extend, don't append
                search_dicts.extend(item.as_search_list())
            else:
                search_dicts.append(item.as_search_dict())
        except AttributeError as e:
            print(f"AttributeError trying to add: {item}\n  {e}")
        except ValueError as e:
            print(f"ValueError trying to add: {item}\n  {e}")
        except InvalidDocumentError:
            print(f"Unable to parse: {item}")

    with Session() as session:
        si = scorched.SolrInterface(
            settings.SOLR_URLS[app_label], http_connection=session, mode="w"
        )
        try:
            si.add(search_dicts)
            if force_commit:
                si.commit()
        except (socket.error, SolrError) as exc:
            add_items_to_solr.retry(exc=exc, countdown=30)
        else:
            # Mark dockets as updated if needed
            if model == Docket:
                items.update(date_modified=now(), date_last_index=now())


@app.task(ignore_resutls=True)
def add_or_update_recap_docket(
    data, force_commit=False, update_threshold=60 * 60
):
    """Add an entire docket to Solr or update it if it's already there.

    This is an expensive operation because to add or update a RECAP docket in
    Solr means updating every document that's a part of it. So if a docket has
    10,000 documents, we'll have to pull them *all* from the database, and
    re-index them all. It'd be nice to not have to do this, but because Solr is
    de-normalized, every document in the RECAP Solr index has a copy of every
    field in Solr. For example, if the name of the case changes, that has to get
    reflected in every document in the docket in Solr.

    To deal with this mess, we have a field on the docket that says when we last
    updated it in Solr. If that date is after a threshold, we just don't do the
    update unless we know the docket has something new.

    :param data: A dictionary containing the a key for 'docket_pk' and
    'content_updated'. 'docket_pk' will be used to find the docket to modify.
    'content_updated' is a boolean indicating whether the docket must be
    updated.
    :param force_commit: Whether to send a commit to Solr (this is usually not
    needed).
    :param update_threshold: Items staler than this number of seconds will be
    updated. Items fresher than this number will be a no-op.
    """
    if data is None:
        return

    with Session() as session:
        si = scorched.SolrInterface(
            settings.SOLR_RECAP_URL, http_connection=session, mode="w"
        )
        some_time_ago = now() - timedelta(seconds=update_threshold)
        d = Docket.objects.get(pk=data["docket_pk"])
        too_fresh = d.date_last_index is not None and (
            d.date_last_index > some_time_ago
        )
        update_not_required = not data.get("content_updated", False)
        if all([too_fresh, update_not_required]):
            return
        else:
            try:
                si.add(d.as_search_list())
                if force_commit:
                    si.commit()
            except SolrError as exc:
                add_or_update_recap_docket.retry(exc=exc, countdown=30)
            else:
                d.date_last_index = now()
                d.save()


@app.task
def add_docket_to_solr_by_rds(item_pks, force_commit=False):
    """Add RECAPDocuments from a single Docket to Solr.

    This is a performance enhancement that can be used when adding many RECAP
    Documents from a single docket to Solr. Instead of pulling the same docket
    metadata for these items over and over (adding potentially thousands of
    queries on a large docket), just pull the metadata once and cache it for
    every document that's added.

    :param item_pks: RECAPDocument pks to add or update in Solr.
    :param force_commit: Whether to send a commit to Solr (this is usually not
    needed).
    :return: None
    """
    with Session() as session:
        si = scorched.SolrInterface(
            settings.SOLR_RECAP_URL, http_connection=session, mode="w"
        )
        rds = RECAPDocument.objects.filter(pk__in=item_pks).order_by()
        try:
            metadata = rds[0].get_docket_metadata()
        except IndexError:
            metadata = None

        try:
            si.add(
                [item.as_search_dict(docket_metadata=metadata) for item in rds]
            )
            if force_commit:
                si.commit()
        except SolrError as exc:
            add_docket_to_solr_by_rds.retry(exc=exc, countdown=30)


@app.task
def delete_items(items, app_label, force_commit=False):
    with Session() as session:
        si = scorched.SolrInterface(
            settings.SOLR_URLS[app_label], http_connection=session, mode="w"
        )
        try:
            si.delete_by_ids(list(items))
            if force_commit:
                si.commit()
        except SolrError as exc:
            delete_items.retry(exc=exc, countdown=30)


def person_first_time_indexing(parent_id: int, position: Position) -> None:
    """Index a person and their no judiciary positions into Elasticsearch.

    It creates a parent document for the person and indexes each non-judiciary
    position as a child document.

    :param parent_id: The ID of the Person.
    :param position: A Position instance.
    :return: None
    """

    # Create the parent document if it does not exist yet in ES
    person_doc = PersonDocument()
    doc = person_doc.prepare(position.person)
    PersonDocument(meta={"id": parent_id}, **doc).save(
        skip_empty=False, return_doc_meta=True
    )

    # After indexing the person, look for non-judicial positions that have not
    # been indexed and index them.
    person_positions = Position.objects.filter(person_id=parent_id)
    non_judicial_positions = [
        pos for pos in person_positions if not pos.is_judicial_position
    ]
    for person_position in non_judicial_positions:
        doc_id = ES_CHILD_ID(person_position.pk).POSITION
        if PositionDocument.exists(id=doc_id, routing=parent_id):
            continue

        position_doc = PositionDocument()
        pos_doc = position_doc.prepare(person_position)
        es_args = {
            "_routing": parent_id,
            "meta": {"id": doc_id},
        }
        PositionDocument(**es_args, **pos_doc).save(
            skip_empty=False,
            return_doc_meta=False,
            refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
        )


def get_instance_from_db(
    instance_id: int, model: ESModelClassType
) -> ESModelType | None:
    """Get a model instance from DB or return None if it doesn't exist.

    :param instance_id: The primary key of the parent instance.
    :param model: The model class of the instance.
    :return: The object instance or None if it doesn't exist.
    """

    try:
        return model.objects.get(pk=instance_id)
    except ObjectDoesNotExist:
        logger.warning(
            f"The {model.__name__} with ID {instance_id} doesn't exists and it"
            "cannot be updated in ES."
        )
        return None


@app.task(
    bind=True,
    autoretry_for=(ConnectionError, ConflictError, ConnectionTimeout),
    max_retries=5,
    retry_backoff=1 * 60,
    retry_backoff_max=10 * 60,
    retry_jitter=True,
    queue=settings.CELERY_ETL_TASK_QUEUE,
    ignore_result=True,
)
def es_save_document(
    self: Task,
    instance_id: int,
    app_label: str,
    es_document_name: ESDocumentNameType,
) -> SaveDocumentResponseType | None:
    """Save a document in Elasticsearch using a provided callable.

    :param self: The celery task
    :param instance_id: The instance ID of the document to save.
    :param app_label: The app label and model that belongs to the document
    being added.
    :param es_document_name: A Elasticsearch DSL document name.
    :return: SaveDocumentResponseType or None
    """

    es_args = {}
    es_document = getattr(es_document_module, es_document_name)

    # Get the instance to save in ES from DB.
    model = apps.get_model(app_label)
    instance = get_instance_from_db(instance_id, model)
    if not instance:
        # Abort task the instance is not found in DB.
        self.request.chain = None
        return None
    match app_label:
        case "people_db.Position":
            parent_id = getattr(instance.person, "pk", None)
            if not all(
                [
                    parent_id,
                    # avoid indexing position records if the parent is not a judge
                    instance.person.is_judge,
                ]
            ):
                self.request.chain = None
                return None
            if not PersonDocument.exists(id=parent_id):
                person_first_time_indexing(parent_id, instance)

            doc_id = ES_CHILD_ID(instance.pk).POSITION
            es_args["_routing"] = parent_id
        case "people_db.Person":
            # index person records only if they were ever a judge.
            if not instance.is_judge:
                self.request.chain = None
                return None
            doc_id = instance.pk
        case "search.RECAPDocument":
            parent_id = getattr(instance.docket_entry.docket, "pk", None)
            if not parent_id:
                self.request.chain = None
                return None

            if not DocketDocument.exists(id=parent_id):
                # create the parent document if it does not exist in ES
                docket_doc = DocketDocument()
                doc = docket_doc.prepare(instance.docket_entry.docket)
                DocketDocument(meta={"id": parent_id}, **doc).save(
                    skip_empty=False, return_doc_meta=True
                )
            doc_id = ES_CHILD_ID(instance.pk).RECAP
            es_args["_routing"] = parent_id
        case "search.Opinion":
            parent_id = getattr(instance.cluster, "pk", None)
            if not parent_id:
                self.request.chain = None
                return None

            if not OpinionClusterDocument.exists(id=parent_id):
                # create the parent document if it does not exist in ES
                cluster_doc = OpinionClusterDocument()
                doc = cluster_doc.prepare(instance.cluster)
                OpinionClusterDocument(meta={"id": parent_id}, **doc).save(
                    skip_empty=False, return_doc_meta=True
                )

            doc_id = ES_CHILD_ID(instance.pk).OPINION
            es_args["_routing"] = parent_id
        case _:
            doc_id = instance_id

    es_args["meta"] = {"id": doc_id}
    es_doc = es_document()
    doc = es_doc.prepare(instance)
    response = es_document(**es_args, **doc).save(
        skip_empty=False,
        return_doc_meta=True,
        refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
    )
    if type(instance) in models_alert_support and response["_version"] == 1:
        # Only send search alerts when a new instance of a model that support
        # Alerts is indexed in ES _version:1
        if es_document == AudioDocument and not waffle.switch_is_active(
            "oa-es-alerts-active"
        ):
            # Disable ES Alerts if oa-es-alerts-active switch is not enabled
            self.request.chain = None
            return None
        return response["_id"], doc
    else:
        self.request.chain = None
        return None


def document_fields_to_update(
    es_document: ESDocumentClassType,
    main_instance: ESModelType,
    affected_fields: list[str],
    related_instance: ESModelType | None,
    fields_map: dict | None,
) -> dict[str, Any]:
    """Generate a dictionary of fields and values to update based on a
     provided map and an instance.

    :param es_document: The Elasticsearch DSL document class.
    :param main_instance: The main instance to update, this is the instance
    that's directly related to the document mapping.
    :param affected_fields: A list of field names that need to be updated.
    :param related_instance: The related instance which is not directly
    connected to the document mapping, although some of its fields are used to
    populate the document.
    :param fields_map: A map from which ES field names are to be extracted.
    :return: A dictionary with fields and values to update.
    """

    fields_to_update = {}

    if fields_map and related_instance:
        # If a fields_maps and a related instance is provided, extract the
        # fields values from the related instance or using the main instance
        # prepare methods.

        # If any of the changed fields has a "prepare" value, extract all the
        # values based on the foreign key relations.
        contains_prepare = any(
            fields_map.get(field, []) == ["prepare"]
            for field in affected_fields
        )
        if contains_prepare:
            return es_document().prepare(main_instance)

        for field in affected_fields:
            document_fields = fields_map[field]
            for doc_field in document_fields:
                if not doc_field:
                    continue
                if field.startswith("get_") and field.endswith("_display"):
                    fields_to_update[doc_field] = getattr(
                        related_instance, field
                    )()
                else:
                    prepare_method = getattr(
                        es_document(), f"prepare_{doc_field}", None
                    )
                    if prepare_method:
                        field_value = prepare_method(main_instance)
                    else:
                        field_value = getattr(related_instance, field)
                    fields_to_update[doc_field] = field_value
    else:
        # No fields_map is provided, extract field values only using the main
        # instance prepare methods.
        for field in affected_fields:
            prepare_method = getattr(es_document(), f"prepare_{field}", None)
            if not prepare_method:
                continue
            field_value = prepare_method(main_instance)
            fields_to_update[field] = field_value
    return fields_to_update


@app.task(
    bind=True,
    autoretry_for=(ConnectionError, ConflictError, ConnectionTimeout),
    max_retries=5,
    retry_backoff=1 * 60,
    retry_backoff_max=10 * 60,
    retry_jitter=True,
    queue=settings.CELERY_ETL_TASK_QUEUE,
    ignore_result=True,
)
def update_es_document(
    self: Task,
    es_document_name: ESDocumentNameType,
    fields_to_update: list[str],
    main_instance_data: tuple[str, int],
    related_instance_data: tuple[str, int] | None = None,
    fields_map: dict | None = None,
) -> None:
    """Update a document in Elasticsearch.
    :param self: The celery task
    :param es_document_name: The Elasticsearch document type name.
    :param fields_to_update: A list containing the fields to update.
    :param main_instance_data: A two tuple, the main instance app label and the
    main instance ID to update.
    :param related_instance_data: A two-tuple: the related instance's app label
    and the related instance ID from which to extract field values. None if the
    update doesn't involve a related instance.
    :param fields_map: A dict containing fields that can be updated or None if
    mapping is not required for the update.
    :return: None
    """

    es_document = getattr(es_document_module, es_document_name)
    main_app_label, main_instance_id = main_instance_data
    # Get the main instance from DB, to extract the latest values.
    main_model = apps.get_model(main_app_label)
    main_model_instance = get_instance_from_db(main_instance_id, main_model)
    if not main_model_instance:
        return

    es_doc = get_doc_from_es(es_document, main_model_instance)
    if not es_doc:
        return

    related_instance = None
    # If provided, get the related instance from DB to extract the latest values.
    if related_instance_data:
        related_instance_app_label, related_instance_id = related_instance_data
        related_instance_model = apps.get_model(related_instance_app_label)
        related_instance = get_instance_from_db(
            related_instance_id, related_instance_model
        )
        if not related_instance:
            return

    # Get the fields to update and their values from DB.
    fields_values_to_update = document_fields_to_update(
        es_document,
        main_model_instance,
        fields_to_update,
        related_instance,
        fields_map,
    )
    if not fields_values_to_update:
        # Abort, avoid updating not indexed fields, like "source" in Docket.
        return

    Document.update(
        es_doc,
        **fields_values_to_update,
        refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
    )


def get_es_doc_id_and_parent_id(
    es_document: ESDocumentClassType, instance: ESModelType
) -> tuple[int | str, int | None]:
    """Retrieve the Elasticsearch document ID and parent ID for a given
     ES document type and DB instance.

    :param es_document: The ES document class type.
    :param instance: The DB instance related to the ES document.
    :return: A two-tuple containing the Elasticsearch document ID and the
    parent ID.
    """

    if es_document is PositionDocument:
        doc_id = ES_CHILD_ID(instance.pk).POSITION
        parent_id = getattr(instance, "person_id", None)
    elif es_document is ESRECAPDocument:
        doc_id = ES_CHILD_ID(instance.pk).RECAP
        parent_id = getattr(instance.docket_entry, "docket_id", None)
    elif es_document is OpinionDocument:
        doc_id = ES_CHILD_ID(instance.pk).OPINION
        parent_id = getattr(instance, "cluster_id", None)
    else:
        doc_id = instance.pk
        parent_id = None

    return doc_id, parent_id


def get_doc_from_es(
    es_document: ESDocumentClassType,
    instance: ESModelType,
) -> ESDocumentInstanceType | None:
    """Get a document in Elasticsearch.
    :param es_document: The Elasticsearch document type.
    :param instance: The instance of the document to retrieve.
    :return: An Elasticsearch document if found, otherwise None.
    """

    # Get doc_id and routing for parent and child documents.
    instance_id, parent_id = get_es_doc_id_and_parent_id(es_document, instance)
    get_args: dict[str, int | str] = (
        {"id": instance_id, "routing": parent_id}
        if parent_id
        else {"id": instance_id}
    )
    try:
        main_doc = es_document.get(**get_args)
    except NotFoundError:
        if isinstance(instance, Person) and not instance.is_judge:
            # If the instance is a Person and is not a Judge, avoid indexing.
            return None

        es_args: dict[str, int | str | dict] = (
            {"_routing": parent_id} if parent_id else {}
        )
        doc = es_document().prepare(instance)
        es_args["meta"] = {"id": instance_id}
        try:
            es_document(**es_args, **doc).save(
                skip_empty=False,
                return_doc_meta=False,
                refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
            )
        except (ConflictError, RequestError) as exc:
            logger.error(
                f"Error indexing the {es_document.Django.model.__name__.capitalize()} with ID: {instance_id}. "
                f"Exception was: {type(exc).__name__}"
            )

        return None
    return main_doc


def handle_ubq_retries(
    self: Task,
    exc: (
        ConnectionError
        | ConflictError
        | ConnectionTimeout
        | NotFoundError
        | ApiError
    ),
    count_query=QuerySet | None,
) -> None:
    """Handles the retry logic for update_children_docs_by_query task based on
    the exception received and number of documents to update.

    :param self: The celery task
    :param exc: The exception that triggered the retry.
    :param count_query: Optional a Queryset to retrieve the number of docs to
    update.
    :return: None
    """

    # If this is an ApiError exception, confirm the error type is
    # search_context_missing_exception, so it can be retried. Otherwise, raise
    # the error.
    if isinstance(exc, ApiError) and not (
        exc.info.get("error", {}).get("type", {})
        == "search_context_missing_exception"
    ):
        raise exc

    retry_count = self.request.retries
    if retry_count >= self.max_retries:
        raise exc

    if isinstance(exc, ConnectionError | ConnectionTimeout) and count_query:
        num_documents = count_query.count()
        estimated_time_ms = num_documents * 90  # 90ms per document
        # Convert ms to seconds
        estimated_delay_sec = round(estimated_time_ms / 1000)
        # Apply exponential backoff with jitter
        min_delay_sec = max(estimated_delay_sec, 10)
        jitter_sec = randint(10, 30)
        countdown_sec = ((retry_count + 1) * min_delay_sec) + jitter_sec
    else:
        # Default case for ConflictError, NotFoundError or ApiError search_context_missing_exception
        min_delay_sec = 10  # 10 seconds
        max_delay_sec = 15  # 15 seconds
        countdown_sec = ((retry_count + 1) * min_delay_sec) + randint(
            min_delay_sec, max_delay_sec
        )

    raise self.retry(exc=exc, countdown=countdown_sec)


@app.task(
    bind=True,
    max_retries=5,
    queue=settings.CELERY_ETL_TASK_QUEUE,
    ignore_result=True,
)
def update_children_docs_by_query(
    self: Task,
    es_document_name: ESDocumentNameType,
    parent_instance_id: int,
    fields_to_update: list[str],
    fields_map: dict[str, str] | None = None,
    event_table: EventTable | None = None,
) -> None:
    """Update child documents in Elasticsearch in bulk using the UpdateByQuery
    API.

    :param self: The celery task
    :param es_document_name: The Elasticsearch Document type name to update.
    :param parent_instance_id: The parent instance ID containing the fields to update.
    :param fields_to_update: List of field names to be updated.
    :param fields_map: A mapping from model fields to Elasticsearch document fields.
    :param event_table: Optional, the EventTable type that triggered the action
    :return: None
    """

    es_document = getattr(es_document_module, es_document_name)
    s = es_document.search()
    if es_document is PositionDocument:
        s = s.query("parent_id", type="position", id=parent_instance_id)
        parent_doc_class = PersonDocument
        main_doc = parent_doc_class.exists(parent_instance_id)
        parent_instance = get_instance_from_db(parent_instance_id, Person)
        if not parent_instance:
            return
        count_query = Position.objects.filter(person_id=parent_instance_id)

    elif es_document is ESRECAPDocument:
        main_instance_id = None
        if event_table == EventTable.DOCKET_ENTRY:
            s = s.query("term", docket_entry_id=parent_instance_id)
            parent_instance = get_instance_from_db(
                parent_instance_id, DocketEntry
            )
            if not parent_instance:
                return
            main_instance_id = parent_instance.docket.pk
            count_query = RECAPDocument.objects.filter(
                docket_entry_id=parent_instance_id
            )
        elif event_table in [None, EventTable.DOCKET]:
            s = s.query(
                "parent_id", type="recap_document", id=parent_instance_id
            )
            parent_instance = get_instance_from_db(parent_instance_id, Docket)
            if not parent_instance:
                return
            main_instance_id = parent_instance.pk
            count_query = RECAPDocument.objects.filter(
                docket_entry__docket_id=parent_instance_id
            )
        if not main_instance_id:
            return
        parent_doc_class = DocketDocument
        main_doc = parent_doc_class.exists(main_instance_id)
    elif (
        es_document is OpinionDocument or es_document is OpinionClusterDocument
    ):
        s = s.query("parent_id", type="opinion", id=parent_instance_id)
        parent_doc_class = OpinionClusterDocument
        parent_instance = get_instance_from_db(
            parent_instance_id, OpinionCluster
        )
        main_doc = parent_doc_class.exists(parent_instance_id)
        if not parent_instance:
            return
        count_query = Opinion.objects.filter(cluster_id=parent_instance_id)

    else:
        # Abort UBQ update for a not supported document
        return

    if not main_doc:
        # Abort for non-existing parent document in ES.
        return

    client = connections.get_connection(alias="no_retry_connection")
    ubq = (
        UpdateByQuery(using=client, index=es_document._index._name)
        .query(s.to_dict()["query"])
        .params(timeout=f"{settings.ELASTICSEARCH_TIMEOUT}s")
    )

    # Build the UpdateByQuery script and execute it
    script_lines = []
    params = {}
    for field_to_update in fields_to_update:
        field_list = (
            fields_map[field_to_update] if fields_map else [field_to_update]
        )
        for field_name in field_list:
            script_lines.append(
                f"ctx._source.{field_name} = params.{field_name};"
            )
            prepare_method = getattr(
                parent_doc_class(), f"prepare_{field_name}", None
            )
            if prepare_method:
                # This work for DE but might not work for other types or fields that
                # require some processing.
                params[field_name] = prepare_method(parent_instance)
            else:
                params[field_name] = getattr(parent_instance, field_to_update)
    script_source = "\n".join(script_lines)

    ubq = ubq.script(source=script_source, params=params)
    try:
        ubq.execute()
    except (
        ConnectionError,
        ConflictError,
        ConnectionTimeout,
        NotFoundError,
        ApiError,
    ) as exc:
        handle_ubq_retries(self, exc, count_query=count_query)

    if settings.ELASTICSEARCH_DSL_AUTO_REFRESH:
        # Set auto-refresh, used for testing.
        es_document._index.refresh()


@app.task(
    bind=True,
    autoretry_for=(
        ConnectionError,
        NotFoundError,
        ConflictError,
        ConnectionTimeout,
    ),
    max_retries=5,
    retry_backoff=1 * 60,
    retry_backoff_max=10 * 60,
    retry_jitter=True,
    queue=settings.CELERY_ETL_TASK_QUEUE,
    ignore_result=True,
)
def index_docket_parties_in_es(
    self: Task,
    docket_id: int,
) -> None:
    """Update a document in Elasticsearch.
    :param self: The celery task
    :param docket_id: The docket ID to update in ES.
    :return: None
    """

    docket = get_instance_from_db(docket_id, Docket)
    if not docket:
        return
    parties_prepared = DocketDocument().prepare_parties(docket)
    fields_to_update = {
        key: list(set_values) for key, set_values in parties_prepared.items()
    }
    docket_document = DocketDocument.get(id=docket_id)
    Document.update(
        docket_document,
        **fields_to_update,
        refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
    )


def bulk_indexing_generator(
    docs_query_set: QuerySet,
    es_document: ESDocumentClassType,
    base_doc: dict[str, str],
    child_id_property: str | None = None,
    parent_id: int | None = None,
) -> Generator[ESDictDocument, None, None]:
    """Generate ES documents for bulk indexing.

    :param docs_query_set: The queryset of model instances to be indexed.
    :param es_document: The Elasticsearch document class corresponding to
    the instance model.
    :param child_id_property: Optional, the property to be used for generating
     ES child document ID.
    :param parent_id: Optional, the parent instance ID used for routing in ES.
    This parameter must only be provided when indexing documents that belong to
    the same parent document.
    :param base_doc: The base ES document fields.
    :return: Yields ES child documents for bulk indexing.
    """

    parent_id_mappings = {
        "RECAP": lambda document: document.docket_entry.docket_id,
        "OPINION": lambda document: document.cluster_id,
    }
    for doc in docs_query_set.iterator():
        es_doc = es_document().prepare(doc)
        if child_id_property:
            if not parent_id:
                routing_id_lambda = parent_id_mappings.get(child_id_property)
                if not routing_id_lambda:
                    continue
                # Get the routing_id from the parent document's ID.
                routing_id = routing_id_lambda(doc)
            else:
                # The parent_id was provided when indexing documents that
                # belong to the same parent.
                routing_id = parent_id
            doc_params = {
                "_id": getattr(ES_CHILD_ID(doc.pk), child_id_property),
                "_routing": f"{routing_id}",
            }
        else:
            doc_params = {
                "_id": doc.pk,
            }
        es_doc.update(base_doc)
        es_doc.update(doc_params)
        yield es_doc


def index_documents_in_bulk_from_queryset(
    docs_queryset: QuerySet,
    es_document: ESDocumentClassType,
    base_doc: dict[str, str],
    child_id_property: str | None = None,
    parent_instance_id: int | None = None,
    testing_mode: bool = False,
) -> list[str]:
    """Index documents in bulk from a queryset into ES. Indexes documents
    using either streaming or parallel bulk  operations, depending on the mode.

    :param docs_queryset: A queryset containing the documents to index.
    :param es_document: The Elasticsearch document class corresponding to
    the instance model.
    :param child_id_property: Optional, the property to be used for generating
     ES child document ID.
    :param base_doc: The base ES document fields.
    :param parent_instance_id: Optional, the parent instance ID used for
    routing in ES.
    :param testing_mode: Set to True to enable streaming bulk, which is used in
     TestCase-based tests because parallel_bulk is incompatible with them.
    https://github.com/freelawproject/courtlistener/pull/3324#issue-1970675619
    Default is False.
    :return: A list of IDs of documents that failed to index.
    """

    client = connections.get_connection()
    failed_child_docs = []

    if testing_mode:
        # Use streaming_bulk in TestCase based tests. Since parallel_bulk
        # doesn't work on them.
        for success, info in streaming_bulk(
            client,
            bulk_indexing_generator(
                docs_queryset,
                es_document,
                base_doc,
                child_id_property,
                parent_instance_id,
            ),
            chunk_size=settings.ELASTICSEARCH_BULK_BATCH_SIZE,
        ):
            if not success:
                failed_child_docs.append(info["index"]["_id"])
    else:
        # Use parallel_bulk in production and tests based on TransactionTestCase
        for success, info in parallel_bulk(
            client,
            bulk_indexing_generator(
                docs_queryset,
                es_document,
                base_doc,
                child_id_property,
                parent_instance_id,
            ),
            thread_count=settings.ELASTICSEARCH_PARALLEL_BULK_THREADS,
            chunk_size=settings.ELASTICSEARCH_BULK_BATCH_SIZE,
        ):
            if not success:
                failed_child_docs.append(info["index"]["_id"])

    return failed_child_docs


@app.task(
    bind=True,
    autoretry_for=(ConnectionError,),
    max_retries=3,
    interval_start=5,
    ignore_result=True,
)
def index_parent_and_child_docs(
    self: Task,
    instance_ids: list[int],
    search_type: str,
    testing_mode: bool = False,
) -> None:
    """Index parent and child documents in Elasticsearch.

    :param self: The Celery task instance
    :param instance_ids: The parent instance IDs to index.
    :param search_type: The Search Type to index parent and child docs.
    :param testing_mode: Set to True to enable streaming bulk, which is used in
     TestCase-based tests because parallel_bulk is incompatible with them.
    https://github.com/freelawproject/courtlistener/pull/3324#issue-1970675619
    Default is False.
    :return: None
    """

    match search_type:
        case SEARCH_TYPES.PEOPLE:
            parent_es_document = PersonDocument
            child_es_document = PositionDocument
            child_id_property = "POSITION"
        case SEARCH_TYPES.RECAP:
            parent_es_document = DocketDocument
            child_es_document = ESRECAPDocument
            child_id_property = "RECAP"
        case SEARCH_TYPES.OPINION:
            parent_es_document = OpinionClusterDocument
            child_es_document = OpinionDocument
            child_id_property = "OPINION"
        case _:
            return

    model_label = parent_es_document.Django.model.__name__.capitalize()
    for instance_id in instance_ids:
        if search_type == SEARCH_TYPES.PEOPLE:
            instance = Person.objects.prefetch_related("positions").get(
                pk=instance_id
            )
            child_docs = instance.positions.all()
        elif search_type == SEARCH_TYPES.RECAP:
            instance = Docket.objects.get(pk=instance_id)
            child_docs = RECAPDocument.objects.filter(
                docket_entry__docket=instance
            )
        elif search_type == SEARCH_TYPES.OPINION:
            instance = OpinionCluster.objects.get(pk=instance_id)
            child_docs = instance.sub_opinions.all()
        else:
            return

        if not parent_es_document.exists(instance_id):
            # Parent document is not yet indexed, index it.
            doc = parent_es_document().prepare(instance)
            es_args = {
                "meta": {"id": instance_id},
            }
            try:
                parent_es_document(**es_args, **doc).save(
                    skip_empty=False,
                    return_doc_meta=False,
                    refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
                )
            except (ConflictError, RequestError) as exc:
                logger.error(
                    f"Error indexing the {model_label} with ID: {instance_id}. "
                    f"Exception was: {type(exc).__name__}"
                )
                continue

        # Index child documents in bulk.
        base_doc = {
            "_op_type": "index",
            "_index": parent_es_document._index._name,
        }

        failed_child_docs = index_documents_in_bulk_from_queryset(
            child_docs,
            child_es_document,
            base_doc,
            child_id_property=child_id_property,
            parent_instance_id=instance_id,
            testing_mode=testing_mode,
        )

        if failed_child_docs:
            logger.error(
                f"Error indexing child documents from the {model_label}"
                f" with ID: {instance_id}. Child IDs are: {failed_child_docs}"
            )

    if settings.ELASTICSEARCH_DSL_AUTO_REFRESH:
        # Set auto-refresh, used for testing.
        parent_es_document._index.refresh()


@app.task(
    bind=True,
    autoretry_for=(ConnectionError,),
    max_retries=3,
    interval_start=5,
    ignore_result=True,
)
def index_parent_or_child_docs(
    self: Task,
    instance_ids: list[int],
    search_type: str,
    document_type: str | None,
    testing_mode: bool = False,
) -> None:
    """Index parent or child documents in Elasticsearch.

    :param self: The Celery task instance
    :param instance_ids: The parent instance IDs to index.
    :param search_type: The Search Type to index parent and child docs.
    :param document_type: The document type to index, 'parent' or 'child' documents
    :param testing_mode: Set to True to enable streaming bulk, which is used in
     TestCase-based tests because parallel_bulk is incompatible with them.
    https://github.com/freelawproject/courtlistener/pull/3324#issue-1970675619
    Default is False.
    :return: None
    """

    parent_instances = QuerySet()
    child_instances = QuerySet()
    parent_ids = []
    match search_type:
        case SEARCH_TYPES.RECAP:
            parent_es_document = DocketDocument
            child_es_document = ESRECAPDocument
            child_id_property = "RECAP"
            parent_model = Docket
            if document_type == "parent":
                parent_instances = Docket.objects.filter(pk__in=instance_ids)
            elif document_type == "child":
                child_instances = RECAPDocument.objects.filter(
                    pk__in=instance_ids
                )
                # Get unique parent_ids for RECAPDocuments
                parent_ids = list(
                    RECAPDocument.objects.filter(pk__in=instance_ids)
                    .values_list("docket_entry__docket_id", flat=True)
                    .order_by("docket_entry__docket_id")
                    .distinct("docket_entry__docket_id")
                )
        case SEARCH_TYPES.OPINION:
            parent_es_document = OpinionClusterDocument
            child_es_document = OpinionDocument
            child_id_property = "OPINION"
            parent_model = OpinionCluster
            if document_type == "parent":
                parent_instances = OpinionCluster.objects.filter(
                    pk__in=instance_ids
                )
            elif document_type == "child":
                child_instances = Opinion.objects.filter(pk__in=instance_ids)
                # Get unique parent_ids for Opinions
                parent_ids = list(
                    Opinion.objects.filter(pk__in=instance_ids)
                    .values_list("cluster_id", flat=True)
                    .distinct()
                )
        case SEARCH_TYPES.ORAL_ARGUMENT:
            parent_es_document = AudioDocument
            if document_type == "parent":
                parent_instances = Audio.objects.filter(pk__in=instance_ids)
        case _:
            return

    base_doc = {
        "_op_type": "index",
        "_index": parent_es_document._index._name,
    }
    if document_type == "child":
        # Index only child documents.
        parent_ids_to_index = []
        for parent_id in parent_ids:
            # Confirm all the child's parent documents are already indexed.
            # Otherwise, index them.
            if not parent_es_document.exists(parent_id):
                parent_ids_to_index.append(parent_id)

        missing_parent_instances = parent_model.objects.filter(
            pk__in=parent_ids_to_index
        )
        if parent_ids_to_index:
            # Index missing parent documents in bulk.
            failed_docs = index_documents_in_bulk_from_queryset(
                missing_parent_instances,
                parent_es_document,
                base_doc,
                testing_mode=testing_mode,
            )
            if failed_docs:
                model_label = (
                    parent_es_document.Django.model.__name__.capitalize()
                )
                logger.error(
                    f"Error indexing documents from {model_label}, "
                    f"Failed Doc IDs are: {failed_docs}"
                )

        # Then index only child documents in bulk.
        failed_docs = index_documents_in_bulk_from_queryset(
            child_instances,
            child_es_document,
            base_doc,
            child_id_property=child_id_property,
            testing_mode=testing_mode,
        )

        if failed_docs:
            model_label = child_es_document.Django.model.__name__.capitalize()
            logger.error(
                f"Error indexing documents from {model_label}, "
                f"Failed Doc IDs are: {failed_docs}"
            )

    if document_type == "parent":
        # Index only parent documents.
        failed_docs = index_documents_in_bulk_from_queryset(
            parent_instances,
            parent_es_document,
            base_doc,
            testing_mode=testing_mode,
        )
        if failed_docs:
            model_label = parent_es_document.Django.model.__name__.capitalize()
            logger.error(
                f"Error indexing documents from {model_label}, "
                f"Failed Doc IDs are: {failed_docs}"
            )

    if settings.ELASTICSEARCH_DSL_AUTO_REFRESH:
        # Set auto-refresh, used for testing.
        parent_es_document._index.refresh()


@app.task(
    bind=True,
    autoretry_for=(ConnectionError, ConflictError, ConnectionTimeout),
    max_retries=5,
    retry_backoff=1 * 60,
    retry_backoff_max=10 * 60,
    retry_jitter=True,
    ignore_result=True,
    queue=settings.CELERY_ETL_TASK_QUEUE,
)
def remove_document_from_es_index(
    self: Task,
    es_document_name: ESDocumentNameType,
    instance_id: int,
    routing: int | None,
) -> None:
    """Remove a document from an Elasticsearch index.

    :param self: The celery task
    :param es_document_name: The Elasticsearch document type name.
    :param instance_id: The ID of the instance to be removed from the
    Elasticsearch index.
    :param routing: The routing value used to look up the document.
    :return: None
    """

    es_document = getattr(es_document_module, es_document_name)
    delete_args: dict[str, int | str] = {
        "index": es_document._index._name,
        "id": instance_id,
    }
    if routing:
        delete_args["routing"] = routing
    es = connections.get_connection()
    try:
        es.delete(**delete_args)
        if settings.ELASTICSEARCH_DSL_AUTO_REFRESH:
            # Set auto-refresh, used for testing.
            es_document._index.refresh()
    except NotFoundError:
        model_label = es_document.Django.model.__name__.capitalize()
        logger.warning(
            f"The {model_label} can't be deleted from the ES index, it doesn't exist."
        )


@app.task(
    bind=True,
    autoretry_for=(ConnectionError,),
    max_retries=5,
    interval_start=5,
    ignore_result=True,
)
def index_dockets_in_bulk(
    self: Task, instance_ids: list[int], testing_mode: bool = False
) -> None:
    """Index dockets in bulk in Elasticsearch.

    :param self: The Celery task instance
    :param instance_ids: The Docket IDs to index.
    :param testing_mode: Set to True to enable streaming bulk, which is used in
     TestCase-based tests because parallel_bulk is incompatible with them.
    https://github.com/freelawproject/courtlistener/pull/3324#issue-1970675619
    Default is False.
    :return: None
    """

    dockets = Docket.objects.filter(pk__in=instance_ids)
    # Index dockets in bulk.
    client = connections.get_connection()
    base_doc = {
        "_op_type": "index",
        "_index": DocketDocument._index._name,
    }
    failed_docs = []
    if testing_mode:
        # Use streaming_bulk in TestCase based tests. Since parallel_bulk
        # doesn't work on them.
        for success, info in streaming_bulk(
            client,
            bulk_indexing_generator(
                dockets,
                DocketDocument,
                base_doc,
            ),
            chunk_size=settings.ELASTICSEARCH_BULK_BATCH_SIZE,
        ):
            if not success:
                failed_docs.append(info["index"]["_id"])

    else:
        for success, info in parallel_bulk(
            client,
            bulk_indexing_generator(
                dockets,
                DocketDocument,
                base_doc,
            ),
            thread_count=settings.ELASTICSEARCH_PARALLEL_BULK_THREADS,
            chunk_size=settings.ELASTICSEARCH_BULK_BATCH_SIZE,
        ):
            if not success:
                failed_docs.append(info["index"]["_id"])

    if failed_docs:
        logger.error(f"Error indexing Dockets in bulk IDs are: {failed_docs}")

    if settings.ELASTICSEARCH_DSL_AUTO_REFRESH:
        # Set auto-refresh, used for testing.
        DocketDocument._index.refresh()


def build_bulk_cites_doc(
    es_child_doc_class: ESDocumentClassType,
    child_id: int,
    child_doc_model: ESModelClassType,
) -> ESDictDocument:
    """Builds a bulk document for updating cites field in an ES document.

    :param es_child_doc_class: The ES child document class to update.
    :param child_id: The child document ID to update.
    :param child_doc_model: The child document to update model class.
    :return: A dictionary representing the ES update operation if the document
    exists, otherwise, it returns an empty dictionary.
    """

    child_instance = get_instance_from_db(child_id, child_doc_model)
    if not child_instance:
        return {}

    match child_doc_model.__name__:
        case "RECAPDocument":
            parent_document_id = child_instance.docket_entry.docket.pk
            child_id_property = "RECAP"
        case "Opinion":
            parent_document_id = child_instance.cluster.pk
            child_id_property = "OPINION"
        case _:
            return {}

    cites_prepared = es_child_doc_class().prepare_cites(child_instance)
    doc_id = getattr(ES_CHILD_ID(child_id), child_id_property)
    if not es_child_doc_class.exists(id=doc_id, routing=parent_document_id):
        # If the ChildDocument does not exist, it might not be indexed yet.
        # Raise a NotFoundError to retry the task; hopefully, it will be
        # indexed soon.
        raise NotFoundError(
            f"The {child_doc_model.__name__} {child_instance.pk} is not indexed.",
            "",
            {"id": child_instance.pk},
        )

    doc_to_update = {
        "_id": doc_id,
        "_routing": parent_document_id,
        "doc": {"cites": cites_prepared},
    }
    return doc_to_update


def check_bulk_indexing_exception(
    errors: list[dict[str, Any]], exception: str
) -> bool:
    """Check for a specific exception type in bulk indexing errors.
    :param errors: A list of dictionaries representing errors from a bulk
    indexing operation.
    :param exception: The exception type string to check for in the error
    details.
    :return: True if the specified exception is found in any of the error
    dictionaries; otherwise, returns False.
    """
    for error in errors:
        if error.get("update", {}).get("error", {}).get("type") == exception:
            return True
    return False


@app.task(
    bind=True,
    autoretry_for=(
        ConnectionError,
        ConflictError,
        NotFoundError,
        ConnectionTimeout,
    ),
    max_retries=6,
    retry_backoff=2 * 60,
    retry_backoff_max=20 * 60,
    retry_jitter=True,
    queue=settings.CELERY_ETL_TASK_QUEUE,
    ignore_result=True,
)
def index_related_cites_fields(
    self: Task,
    model_name: str,
    child_id: int,
    cluster_ids_to_update: list[int] | None = None,
) -> None:
    """Index 'cites' and 'citeCount' fields in ES documents in a one request.
    :param self: The Celery task instance.
    :param model_name: The model name that originated the request.
    :param child_id: The child document ID to update with the cites.
    :param cluster_ids_to_update: Optional; the cluster IDs where 'citeCount'
    should be updated.
    :return: None.
    """

    documents_to_update = []
    cites_doc_to_update = {}
    base_doc = {}
    match model_name:
        case OpinionsCited.__name__:
            # Query all clusters to update and retrieve only their sub_opinions
            # with the necessary fields.
            prefetch = Prefetch(
                "sub_opinions", queryset=Opinion.objects.only("pk")
            )
            clusters_with_sub_opinions = (
                OpinionCluster.objects.filter(pk__in=cluster_ids_to_update)
                .only("pk", "citation_count")
                .prefetch_related(prefetch)
            )

            base_doc = {
                "_op_type": "update",
                "_index": OpinionClusterDocument._index._name,
            }
            for cluster in clusters_with_sub_opinions:
                if not OpinionClusterDocument.exists(id=cluster.pk):
                    # If the OpinionClusterDocument does not exist, it might
                    # not be indexed yet. Raise a NotFoundError to retry the
                    # task; hopefully, it will be indexed soon.
                    raise NotFoundError(
                        f"The OpinionCluster {cluster.pk} is not indexed.",
                        "",
                        {"id": cluster.pk},
                    )

                # Build the OpinionCluster dicts for updating the citeCount.
                doc_to_update = {
                    "_id": cluster.pk,
                    "doc": {"citeCount": cluster.citation_count},
                }
                doc_to_update.update(base_doc)
                documents_to_update.append(doc_to_update)

                for opinion in cluster.sub_opinions.all():
                    if not OpinionClusterDocument.exists(
                        id=ES_CHILD_ID(opinion.pk).OPINION, routing=cluster.pk
                    ):
                        # If the OpinionDocument does not exist, it might
                        # not be indexed yet. Raise a NotFoundError to retry the
                        # task; hopefully, it will be indexed soon.
                        raise NotFoundError(
                            f"The Opinion {opinion.pk} is not indexed.",
                            "",
                            {"id": opinion.pk},
                        )

                    # Build the Opinion dicts for updating the citeCount.
                    doc_to_update = {
                        "_id": ES_CHILD_ID(opinion.pk).OPINION,
                        "_routing": cluster.pk,
                        "doc": {"citeCount": cluster.citation_count},
                    }
                    doc_to_update.update(base_doc)
                    documents_to_update.append(doc_to_update)

            # Finally build the Opinion dict for updating the cites.
            child_doc_model = Opinion
            es_child_doc_class = OpinionDocument
            cites_doc_to_update = build_bulk_cites_doc(
                es_child_doc_class, child_id, child_doc_model
            )

        case OpinionsCitedByRECAPDocument.__name__:
            # Build the RECAPDocument dict for updating the cites.
            base_doc = {
                "_op_type": "update",
                "_index": DocketDocument._index._name,
            }

            child_doc_model = RECAPDocument
            es_child_doc_class = ESRECAPDocument
            cites_doc_to_update = build_bulk_cites_doc(
                es_child_doc_class, child_id, child_doc_model
            )

    if cites_doc_to_update and base_doc:
        cites_doc_to_update.update(base_doc)
        documents_to_update.append(cites_doc_to_update)

    if not documents_to_update:
        return

    client = connections.get_connection(alias="no_retry_connection")
    # Execute the bulk update
    try:
        bulk(client, documents_to_update)
    except BulkIndexError as exc:
        # Catch any BulkIndexError exceptions to handle specific error message.
        # If the error is a version conflict, raise a ConflictError for retrying it.
        if check_bulk_indexing_exception(
            exc.errors, "version_conflict_engine_exception"
        ):
            raise ConflictError(
                "ConflictError indexing cites.",
                "",
                {"id": child_id},
            )
        else:
            # If the error is of any other type, raises the original
            # BulkIndexError for debugging.
            raise exc

    if settings.ELASTICSEARCH_DSL_AUTO_REFRESH:
        # Set auto-refresh, used for testing.
        OpinionClusterDocument._index.refresh()
        DocketDocument._index.refresh()


@app.task(
    bind=True,
    max_retries=5,
    queue=settings.CELERY_ETL_TASK_QUEUE,
    ignore_result=True,
)
def remove_parent_and_child_docs_by_query(
    self: Task,
    es_document_name: ESDocumentNameType,
    main_instance_ids: list[int],
    event_table: EventTable | None = None,
) -> None:
    """Remove documents in Elasticsearch by query using the delete_by_query API

    :param self: The celery task
    :param es_document_name: The Elasticsearch Document type name to delete.
    :param main_instance_ids: The main instance IDs to remove.
    :param event_table: Optional, the EventTable type that triggered the action
    :return: None
    """

    es_document = getattr(es_document_module, es_document_name)
    s = es_document.search()
    # For EventTable.DOCKET and EventTable.DOCKET_ENTRY, main_instance_ids is
    # a list containing a single element, which is the parent ID used to remove
    # its child documents.
    instance_id = main_instance_ids[0]

    match event_table:
        case EventTable.DOCKET if es_document is ESRECAPDocument:
            parent_query = Q("term", _id=instance_id)
            child_query = Q("parent_id", type="recap_document", id=instance_id)
            should_query = Q(
                "bool",
                should=[parent_query, child_query],
                minimum_should_match=1,
            )
            s = s.query(should_query)
            query = s.to_dict()["query"]
            count_query = RECAPDocument.objects.filter(
                docket_entry__docket_id=instance_id
            )
        case EventTable.DOCKET_ENTRY if es_document is ESRECAPDocument:
            child_query = Q("term", docket_entry_id=instance_id)
            s = s.query(child_query)
            query = s.to_dict()["query"]
            count_query = RECAPDocument.objects.filter(
                docket_entry_id=instance_id
            )

        case EventTable.RECAP_DOCUMENT if es_document is ESRECAPDocument:
            ids_to_remove = [
                ES_CHILD_ID(doc_id).RECAP for doc_id in main_instance_ids
            ]
            child_query = Q("terms", _id=ids_to_remove)
            s = s.query(child_query)
            query = s.to_dict()["query"]
            count_query = RECAPDocument.objects.filter(
                pk__in=main_instance_ids
            )

        case _:
            # Abort DeleteByQuery request for a not supported document type.
            return

    client = connections.get_connection(alias="no_retry_connection")
    try:
        client.delete_by_query(
            index=es_document._index._name, body={"query": query}
        )
    except (ConnectionError, NotFoundError) as exc:
        handle_ubq_retries(self, exc, count_query=count_query)

    if settings.ELASTICSEARCH_DSL_AUTO_REFRESH:
        # Set auto-refresh, used for testing.
        es_document._index.refresh()


@app.task(
    bind=True,
    autoretry_for=(ConnectionError, NotFoundError),
    max_retries=5,
    interval_start=5,
    ignore_result=True,
)
def remove_documents_by_query(
    self: Task,
    es_document_name: ESDocumentNameType,
    instance_ids: list[int] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    testing_mode: bool = False,
    requests_per_second: int | None = None,
    max_docs: int = 0,
) -> None | dict[str, str]:
    """Remove documents from ES by query.

    This method deletes documents from a specified ES document type based on a
    combination of criteria such as document IDs, and a date range.

    :param self: The Celery task instance.
    :param es_document_name: The Elasticsearch Document type name to delete.
    :param instance_ids: Optional, a list of document IDs to delete. If None,
    deletion is based on the date range.
    :param start_date: Optional, the start date of the date range for document deletion.
    :param end_date: Optional, the end date of the date range for document deletion.
    :param testing_mode: Optional, if True, performs the removal synchronously.
    :param requests_per_second: Optional, the target number of sub-requests per
    second for a delete by query operation.
    :param max_docs: Optional, maximum number of documents to process.
    :return: The ES request response, or None for unsupported removal actions.
    """

    optional_params = {}
    es_document = getattr(es_document_module, es_document_name)
    s = es_document.search()
    match es_document_name:
        case "DocketDocument" if instance_ids:
            # Remove non-recap dockets.
            remove_query = Q("terms", _id=instance_ids)
            s = s.query(remove_query)
            query = s.to_dict()["query"]
        case "OpinionDocument" if start_date and end_date:
            # Remove OpinionDocument by a timestamp range date query.
            date_range_query = build_daterange_query(
                "timestamp", end_date, start_date
            )
            child_query_opinion = Q("match", cluster_child="opinion")
            remove_query = Q(
                "bool", must=[date_range_query[0], child_query_opinion]
            )
            s = s.query(remove_query)
            query = s.to_dict()["query"]
            if not testing_mode:
                # Execute the task asynchronously.
                optional_params.update({"wait_for_completion": "false"})
            if max_docs:
                optional_params.update({"max_docs": max_docs})
            if requests_per_second:
                optional_params.update(
                    {"requests_per_second": requests_per_second}
                )
        case _:
            # Abort DeleteByQuery request for a not supported document type.
            return None

    if not testing_mode:
        # Ignore ConflictErrors, by proceeding with the deletion.
        optional_params.update({"conflicts": "proceed"})

    client = connections.get_connection(alias="no_retry_connection")
    response = client.delete_by_query(
        index=es_document._index._name,
        body={"query": query},
        params=optional_params,
    )
    if settings.ELASTICSEARCH_DSL_AUTO_REFRESH:
        # Set auto-refresh, used for testing.
        es_document._index.refresh()

    return response
