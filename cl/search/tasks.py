import logging
import socket
from collections import deque
from datetime import timedelta
from importlib import import_module
from random import randint
from typing import Any, Generator

import scorched
import waffle
from celery import Task
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from django.utils.timezone import now
from elasticsearch.exceptions import (
    ConflictError,
    ConnectionError,
    NotFoundError,
    RequestError,
)
from elasticsearch.helpers import parallel_bulk, streaming_bulk
from elasticsearch_dsl import Document, UpdateByQuery, connections
from requests import Session
from scorched.exc import SolrError

from cl.audio.models import Audio
from cl.celery_init import app
from cl.lib.elasticsearch_utils import es_index_exists
from cl.lib.search_index_utils import InvalidDocumentError
from cl.people_db.models import Person, Position
from cl.search.documents import (
    ES_CHILD_ID,
    AudioDocument,
    DocketDocument,
    ESRECAPDocument,
    PersonDocument,
    PositionDocument,
)
from cl.search.models import (
    SEARCH_TYPES,
    Docket,
    OpinionCluster,
    RECAPDocument,
)
from cl.search.types import (
    ESDictDocument,
    ESDocumentClassType,
    ESDocumentInstanceType,
    ESModelClassType,
    ESModelType,
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
        if PositionDocument.exists(id=doc_id):
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
            f"cannot be updated in ES."
        )
        return None


@app.task(
    bind=True,
    autoretry_for=(ConnectionError, ConflictError),
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
    es_document_name: str,
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
                    es_index_exists(es_document._index._name),
                    parent_id,
                    # avoid indexing position records if the parent is not a judge
                    instance.person.is_judge,
                ]
            ):
                self.request.chain = None
                return
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
            if not all(
                [
                    es_index_exists(es_document._index._name),
                    parent_id,
                ]
            ):
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
    fields_map: dict,
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
        for field in affected_fields:
            document_fields = fields_map[field]
            for doc_field in document_fields:
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
    autoretry_for=(ConnectionError, ConflictError),
    max_retries=5,
    retry_backoff=1 * 60,
    retry_backoff_max=10 * 60,
    retry_jitter=True,
    queue=settings.CELERY_ETL_TASK_QUEUE,
    ignore_result=True,
)
def update_es_document(
    self: Task,
    es_document_name: str,
    fields_to_update: list[str],
    main_instance_data: tuple[str, int],
    related_instance_data: tuple[str, int] | None,
    fields_map: dict | None,
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
    es_doc = get_doc_from_es(es_document, main_instance_id)
    if not es_doc:
        model_label = es_document.Django.model.__name__.capitalize()
        logger.warning(
            f"The {model_label} with ID:{main_instance_id} can't updated. "
            "It's not indexed."
        )
        return

    # Get the main instance from DB, to extract the latest values.
    main_model = apps.get_model(main_app_label)
    main_model_instance = get_instance_from_db(main_instance_id, main_model)
    if not main_model_instance:
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
    Document.update(
        es_doc,
        **fields_values_to_update,
        refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
    )


def get_doc_from_es(
    es_document: ESDocumentClassType,
    instance_id: int,
) -> ESDocumentInstanceType | None:
    """Get a document in Elasticsearch.
    :param es_document: The Elasticsearch document type.
    :param instance_id: The instance ID of the document to retrieve.
    :return: An Elasticsearch document if found, otherwise None.
    """

    # Get doc_id for parent-child documents.
    if es_document is PositionDocument:
        instance_id = ES_CHILD_ID(instance_id).POSITION
    elif es_document is ESRECAPDocument:
        instance_id = ES_CHILD_ID(instance_id).RECAP

    try:
        main_doc = es_document.get(id=instance_id)
    except NotFoundError:
        return None
    return main_doc


@app.task(
    bind=True,
    max_retries=5,
    queue=settings.CELERY_ETL_TASK_QUEUE,
    ignore_result=True,
)
def update_children_docs_by_query(
    self: Task,
    es_document_name: str,
    parent_instance_id: int,
    fields_to_update: list[str],
    fields_map: dict[str, str] | None = None,
) -> None:
    """Update child documents in Elasticsearch in bulk using the UpdateByQuery
    API.

    :param self: The celery task
    :param es_document_name: The Elasticsearch Document type name to update.
    :param parent_instance_id: The parent instance ID containing the fields to update.
    :param fields_to_update: List of field names to be updated.
    :param fields_map: A mapping from model fields to Elasticsearch document fields.
    :return: None
    """

    es_document = getattr(es_document_module, es_document_name)
    s = es_document.search()
    main_doc = None
    parent_instance = None
    parent_doc_class = None
    if es_document is PositionDocument:
        s = s.query("parent_id", type="position", id=parent_instance_id)
        parent_doc_class = PersonDocument
        main_doc = parent_doc_class.exists(parent_instance_id)
        parent_instance = get_instance_from_db(parent_instance_id, Person)
        if not parent_instance:
            return
    elif es_document is ESRECAPDocument:
        s = s.query("parent_id", type="recap_document", id=parent_instance_id)
        parent_doc_class = DocketDocument
        main_doc = parent_doc_class.exists(parent_instance_id)
        parent_instance = get_instance_from_db(parent_instance_id, Docket)
        if not parent_instance:
            return

    if not main_doc:
        # Abort bulk update for a not supported document or non-existing parent
        # document in ES.
        return

    client = connections.get_connection()
    ubq = (
        UpdateByQuery(using=client, index=es_document._index._name)
        .query(s.to_dict()["query"])
        .params(
            slices=es_document._index._settings[
                "number_of_shards"
            ],  # Set slices equal to the number of shards.
            scroll="3m",  # Keep the search context alive for 3 minutes
        )
    )

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
                params[field_name] = prepare_method(parent_instance)
            else:
                params[field_name] = getattr(parent_instance, field_to_update)
    script_source = "\n".join(script_lines)
    # Build the UpdateByQuery script and execute it
    ubq = ubq.script(source=script_source, params=params)
    try:
        ubq.execute()
    except (ConnectionError, ConflictError) as exc:
        retry_count = self.request.retries
        if retry_count >= self.max_retries:
            raise exc
        min_delay = 10  # 10 seconds
        max_delay = 15  # 15 seconds
        countdown = ((retry_count + 1) * min_delay) + randint(
            min_delay, max_delay
        )
        raise self.retry(exc=exc, countdown=countdown)

    if settings.ELASTICSEARCH_DSL_AUTO_REFRESH:
        # Set auto-refresh, used for testing.
        es_document._index.refresh()


@app.task(
    bind=True,
    autoretry_for=(ConnectionError, NotFoundError, ConflictError),
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
    child_docs: QuerySet,
    child_es_document: ESDocumentClassType,
    child_id_property: str,
    instance_id: int,
    base_doc: dict[str, str],
) -> Generator[ESDictDocument, None, None]:
    """Generate ES child documents for bulk indexing.

    :param child_docs: The queryset of child model instances to be indexed.
    :param child_es_document: The Elasticsearch document class corresponding to
    the child model.
    :param child_id_property: The property to be used for generating ES
    child document ID.
    :param instance_id: The parent instance ID used for routing in ES.
    :param base_doc: The base ES document fields.
    :return: Yields ES child documents for bulk indexing.
    """

    for child in child_docs.iterator():
        child_doc = child_es_document().prepare(child)
        child_params = {
            "_id": getattr(ES_CHILD_ID(child.pk), child_id_property),
            "_routing": f"{instance_id}",
        }
        child_doc.update(base_doc)
        child_doc.update(child_params)
        yield child_doc


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
    :param testing_mode: If True uses streaming_bulk in TestCase based tests,
    otherwise uses parallel_bulk in production.
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
        client = connections.get_connection()
        base_doc = {
            "_op_type": "index",
            "_index": parent_es_document._index._name,
        }

        failed_child_docs = []
        if testing_mode:
            # Use streaming_bulk in TestCase based tests. Since parallel_bulk
            # doesn't work on them.
            for success, info in streaming_bulk(
                client,
                bulk_indexing_generator(
                    child_docs,
                    child_es_document,
                    child_id_property,
                    instance_id,
                    base_doc,
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
                    child_docs,
                    child_es_document,
                    child_id_property,
                    instance_id,
                    base_doc,
                ),
                thread_count=settings.ELASTICSEARCH_PARALLEL_BULK_THREADS,
                chunk_size=settings.ELASTICSEARCH_BULK_BATCH_SIZE,
            ):
                if not success:
                    failed_child_docs.append(info["index"]["_id"])

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
    autoretry_for=(ConnectionError, ConflictError),
    max_retries=5,
    retry_backoff=1 * 60,
    retry_backoff_max=10 * 60,
    retry_jitter=True,
    ignore_result=True,
    queue=settings.CELERY_ETL_TASK_QUEUE,
)
def remove_document_from_es_index(
    self: Task, es_document_name: str, instance_id: int
) -> None:
    """Remove a document from an Elasticsearch index.

    :param self: The celery task
    :param es_document_name: The Elasticsearch document type name.
    :param instance_id: The ID of the instance to be removed from the
    Elasticsearch index.
    :return: None
    """

    es_document = getattr(es_document_module, es_document_name)
    if es_document is PositionDocument:
        doc_id = ES_CHILD_ID(instance_id).POSITION
    elif es_document is ESRECAPDocument:
        doc_id = ES_CHILD_ID(instance_id).RECAP
    else:
        doc_id = instance_id

    try:
        doc = es_document.get(id=doc_id)
        doc.delete(refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH)
    except NotFoundError:
        model_label = es_document.Django.model.__name__.capitalize()
        logger.error(
            f"The {model_label} with ID:{instance_id} can't be deleted from "
            f"the ES index, it doesn't exists."
        )
