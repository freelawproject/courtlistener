from functools import partial

from celery.canvas import chain
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save

from cl.alerts.tasks import (
    process_percolator_response,
    send_or_schedule_alerts,
)
from cl.audio.models import Audio
from cl.lib.elasticsearch_utils import elasticsearch_enabled
from cl.people_db.models import (
    ABARating,
    Education,
    Person,
    PoliticalAffiliation,
    School,
)
from cl.search.documents import (
    ES_CHILD_ID,
    AudioDocument,
    DocketDocument,
    ESRECAPDocument,
    OpinionClusterDocument,
    OpinionDocument,
    ParentheticalGroupDocument,
    PersonDocument,
    PositionDocument,
)
from cl.search.models import (
    BankruptcyInformation,
    Citation,
    Docket,
    Opinion,
    OpinionCluster,
)
from cl.search.tasks import (
    es_save_document,
    remove_document_from_es_index,
    update_children_docs_by_query,
    update_es_document,
)
from cl.search.types import ESDocumentClassType, ESModelType


def compose_app_label(instance: ESModelType) -> str:
    """Compose the app label and model class name for an ES model instance.

    :param instance: The ES Model instance.
    :return: A string combining the app label and the Model class name.
    """
    return f"{instance._meta.app_label}.{instance.__class__.__name__}"


def updated_fields(
    instance: ESModelType, es_document: ESDocumentClassType
) -> list[str]:
    """Look for changes in the tracked fields of an instance.
    :param instance: The instance to check for changed fields.
    :param es_document: The Elasticsearch document type.
    :return: A list of the names of fields that have changed in the instance.
    """
    # Get the field names being tracked
    tracked_set = None
    if es_document is AudioDocument:
        tracked_set = getattr(instance, "es_oa_field_tracker", None)
    elif es_document is ParentheticalGroupDocument:
        tracked_set = getattr(instance, "es_pa_field_tracker", None)
    elif es_document is ESRECAPDocument or es_document is DocketDocument:
        tracked_set = getattr(instance, "es_rd_field_tracker", None)
    elif es_document is PositionDocument:
        tracked_set = getattr(instance, "es_p_field_tracker", None)
    elif (
        es_document is OpinionClusterDocument or es_document is OpinionDocument
    ):
        tracked_set = getattr(instance, "es_o_field_tracker", None)

    # Check the set before trying to get the fields
    if not tracked_set:
        return []

    # Check each tracked field to see if it has changed
    changed_fields = []
    for field in tracked_set.fields:
        current_value = getattr(instance, field)
        try:
            # If field is a ForeignKey relation, the current value is the
            # related object, while the previous value is the ID, get the id.
            # See https://django-model-utils.readthedocs.io/en/latest/utilities.html#field-tracker
            field_type = instance.__class__._meta.get_field(field)
            if (
                field_type.get_internal_type() == "ForeignKey"
                and current_value
                and not field.endswith("_id")
            ):
                current_value = current_value.pk
        except FieldDoesNotExist:
            # Support tracking for properties, only abort if it's not a model
            # property
            if not hasattr(instance, field) and not isinstance(
                getattr(instance.__class__, field, None), property
            ):
                continue

        if current_value != tracked_set.previous(field):
            changed_fields.append(field)
    return changed_fields


def get_fields_to_update(
    changed_fields: list[str], fields_map: dict[str, str]
) -> list[str]:
    """Generate a list of fields to be updated based on provided map and changed fields.

    :param changed_fields: A list of field names that have been changed.
    :param fields_map: A dict containing field names that can be updated.
    :return: A list with field names that need to be updated.
    """
    fields_to_update = []
    for field in changed_fields:
        if field in list(fields_map.keys()):
            fields_to_update.append(field)
        if f"get_{field}_display" in list(fields_map.keys()):
            fields_to_update.append(f"get_{field}_display")
    return fields_to_update


def exists_or_create_doc(
    es_document: ESDocumentClassType,
    instance: ESModelType,
    avoid_creation: bool = False,
) -> bool:
    """Get or create a document in Elasticsearch.
    :param es_document: The Elasticsearch document type.
    :param instance: The instance of the document to get or create.
    :param avoid_creation: Whether the document shouldn't be created if it doesn't
    exist.
    :return: True if the ES document exists, False otherwise.
    """

    # Get doc_id for parent-child documents.
    if es_document is PositionDocument:
        doc_id = ES_CHILD_ID(instance.pk).POSITION
    elif es_document is ESRECAPDocument:
        doc_id = ES_CHILD_ID(instance.pk).RECAP
    elif es_document is OpinionDocument:
        doc_id = ES_CHILD_ID(instance.pk).OPINION
    else:
        doc_id = instance.pk

    if es_document.exists(id=doc_id):
        return True

    if not avoid_creation:
        transaction.on_commit(
            partial(
                es_save_document.delay,
                instance.pk,
                compose_app_label(instance),
                es_document.__name__,
            )
        )
        return False
    return False


def update_es_documents(
    main_model: ESModelType,
    es_document: ESDocumentClassType,
    instance: ESModelType,
    created: bool,
    mapping_fields: dict,
) -> None:
    """Update documents in Elasticsearch if there are changes in the tracked
     fields of an instance.
    :param main_model: The main model to fetch objects from.
    :param es_document: The Elasticsearch document type.
    :param instance: The instance whose changes should be tracked and updated.
    :param created: A boolean indicating whether the instance is newly created.
    :param mapping_fields: A dict containing the query to use and the fields_map
    :return: None
    """
    if created:
        return

    changed_fields = updated_fields(instance, es_document)
    if not changed_fields:
        return

    for query, fields_map in mapping_fields.items():
        fields_to_update = get_fields_to_update(changed_fields, fields_map)
        match instance:
            case OpinionCluster() if es_document is OpinionDocument:  # type: ignore
                main_doc = exists_or_create_doc(
                    OpinionClusterDocument, instance, avoid_creation=True
                )
                if not main_doc:
                    # Abort bulk update for a non-existing parent document in ES.
                    return
                transaction.on_commit(
                    partial(
                        update_children_docs_by_query.delay,
                        es_document.__name__,
                        instance.pk,
                        fields_to_update,
                        fields_map,
                    )
                )
            case Docket() if es_document is OpinionDocument:  # type: ignore
                related_record = OpinionCluster.objects.filter(
                    **{query: instance}
                )
                for cluster in related_record:
                    main_doc = exists_or_create_doc(
                        OpinionClusterDocument, cluster, avoid_creation=True
                    )
                    if not main_doc:
                        # Abort bulk update for a non-existing parent document in ES.
                        return
                    transaction.on_commit(
                        partial(
                            update_children_docs_by_query.delay,
                            es_document.__name__,
                            cluster.pk,
                            fields_to_update,
                            fields_map,
                        )
                    )
            case Person() if es_document is PositionDocument and query == "person":  # type: ignore
                """
                This case handles the update of one or more fields that belongs to
                the parent model(The person model).
                """
                main_doc = exists_or_create_doc(
                    PersonDocument, instance, avoid_creation=True
                )
                if not main_doc:
                    # Abort bulk update for a non-existing parent document in ES.
                    return
                transaction.on_commit(
                    partial(
                        update_children_docs_by_query.delay,
                        es_document.__name__,
                        instance.pk,
                        fields_to_update,
                        fields_map,
                    )
                )
            case ABARating() | PoliticalAffiliation() | School() if es_document is PositionDocument:  # type: ignore
                """
                This code handles the update of fields that belongs to records associated with
                the parent document using ForeignKeys.

                First, we get the list of all the Person objects related to the instance object
                and then we use the update_children_docs_by_query method to update their positions.
                """
                related_record = Person.objects.filter(**{query: instance})
                for person in related_record:
                    main_doc = exists_or_create_doc(
                        PersonDocument, person, avoid_creation=True
                    )
                    if not main_doc:
                        # Abort bulk update for a non-existing parent document in ES.
                        return
                    transaction.on_commit(
                        partial(
                            update_children_docs_by_query.delay,
                            es_document.__name__,
                            person.pk,
                            fields_to_update,
                            fields_map,
                        )
                    )
            case Docket() if es_document is ESRECAPDocument:  # type: ignore
                main_doc = exists_or_create_doc(
                    DocketDocument, instance, avoid_creation=True
                )
                if not main_doc:
                    # Abort bulk update for a non-existing parent document in ES.
                    return
                transaction.on_commit(
                    partial(
                        update_children_docs_by_query.delay,
                        es_document.__name__,
                        instance.pk,
                        fields_to_update,
                        fields_map,
                    )
                )
            case Person() if es_document is ESRECAPDocument:  # type: ignore
                related_dockets = Docket.objects.filter(**{query: instance})
                for rel_docket in related_dockets:
                    main_doc = exists_or_create_doc(
                        DocketDocument, rel_docket, avoid_creation=True
                    )
                    if not main_doc:
                        # Abort bulk update for a non-existing parent document in ES.
                        return
                    transaction.on_commit(
                        partial(
                            update_children_docs_by_query.delay,
                            es_document.__name__,
                            rel_docket.pk,
                            fields_to_update,
                            fields_map,
                        )
                    )
            case _:
                main_objects = main_model.objects.filter(**{query: instance})
                for main_object in main_objects:
                    main_doc = exists_or_create_doc(es_document, main_object)
                    if not main_doc:
                        continue
                    if fields_to_update:
                        # Update main document in ES, including fields to be
                        # extracted from a related instance.
                        transaction.on_commit(
                            partial(
                                update_es_document.delay,
                                es_document.__name__,
                                fields_to_update,
                                (
                                    compose_app_label(main_object),
                                    main_object.pk,
                                ),
                                (compose_app_label(instance), instance.pk),
                                fields_map,
                            )
                        )


def update_remove_m2m_documents(
    main_model: ESModelType,
    es_document: ESDocumentClassType,
    instance: ESModelType,
    mapping_fields: dict,
    affected_field: str,
) -> None:
    """Update many-to-many related documents in Elasticsearch.
    :param main_model: The main model to fetch objects from.
    :param es_document: The Elasticsearch document type.
    :param instance: The instance whose many-to-many relationships are to be updated.
    :param mapping_fields: A dict containing the query to use and the fields_map
    :param affected_field: The name of the field that has many-to-many
    relationships with the instance.
    :return: None
    """
    for key, fields_map in mapping_fields.items():
        if main_model.__name__.lower() != key:  # type: ignore
            # The m2m relationship is not defined in the main model but
            # we use the relationship to add data to the ES documents.
            main_objects = main_model.objects.filter(**{key: instance})
            for main_object in main_objects:
                update_m2m_field_in_es_document(
                    main_object, es_document, affected_field
                )
        else:
            update_m2m_field_in_es_document(
                instance, es_document, affected_field
            )


def update_m2m_field_in_es_document(
    instance: ESModelType,
    es_document: ESDocumentClassType,
    affected_field: str,
) -> None:
    """Update a single field created using a many-to-many relationship.
    :param instance: The instance of the document to update.
    :param es_document: The Elasticsearch document type.
    :param affected_field: The name of the field that has many-to-many
    relationships with the instance.
    :return: None
    """
    document = exists_or_create_doc(es_document, instance)
    if not document:
        return
    transaction.on_commit(
        partial(
            update_es_document.delay,
            es_document.__name__,
            [
                affected_field,
            ],
            (compose_app_label(instance), instance.pk),
            None,
            None,
        )
    )

    if es_document is OpinionClusterDocument and isinstance(
        instance, OpinionCluster
    ):
        transaction.on_commit(
            partial(
                update_children_docs_by_query.delay,
                es_document.__name__,
                instance.pk,
                [
                    affected_field,
                ],
            )
        )


def update_reverse_related_documents(
    main_model: ESModelType,
    es_document: ESDocumentClassType,
    instance: ESModelType,
    query_string: str,
    affected_fields: list[str],
) -> None:
    """Update reverse related documents in Elasticsearch.
    :param main_model: The main model to fetch objects from.
    :param es_document: The Elasticsearch document type.
    :param instance: The instance for which the reverse related documents are
    to be updated.
    :param query_string: The query string to filter the main model objects.
    :param affected_fields: The list of field names that are reverse related to
    the instance.
    :return: None
    """

    # Update parent instance
    main_objects = main_model.objects.filter(**{query_string: instance})
    for main_object in main_objects:
        main_doc = exists_or_create_doc(
            es_document, main_object, avoid_creation=True
        )
        if not main_doc:
            # Abort update if the parent document doesn't exist in the index.
            continue
        transaction.on_commit(
            partial(
                update_es_document.delay,
                es_document.__name__,
                affected_fields,
                (compose_app_label(main_object), main_object.pk),
                None,
                None,
            )
        )

    match instance:
        case ABARating() | PoliticalAffiliation() | Education() if es_document is PersonDocument:  # type: ignore
            # bulk update position documents when a reverse related record is created/updated.
            related_record = Person.objects.filter(**{query_string: instance})
            for person in related_record:
                main_doc = exists_or_create_doc(
                    es_document, person, avoid_creation=True
                )
                if not main_doc:
                    # Abort bulk update for a non-existing parent document in ES.
                    return
                transaction.on_commit(
                    partial(
                        update_children_docs_by_query.delay,
                        PositionDocument.__name__,
                        person.pk,
                        affected_fields,
                    )
                )
        case Citation() | Opinion() if es_document is OpinionClusterDocument:  # type: ignore
            main_doc = exists_or_create_doc(
                es_document, instance.cluster, avoid_creation=True
            )
            if not main_doc:
                # Abort bulk update for a non-existing parent document in ES.
                return
            transaction.on_commit(
                partial(
                    update_children_docs_by_query.delay,
                    OpinionDocument.__name__,
                    instance.cluster.pk,
                    affected_fields,
                )
            )
        case BankruptcyInformation() if es_document is DocketDocument:  # type: ignore
            # bulk update RECAP documents when a reverse related record is created/updated.
            main_doc = exists_or_create_doc(
                es_document, instance.docket, avoid_creation=True
            )
            if not main_doc:
                # Abort bulk update for a non-existing parent document in ES.
                return
            transaction.on_commit(
                partial(
                    update_children_docs_by_query.delay,
                    ESRECAPDocument.__name__,
                    instance.docket.pk,
                    affected_fields,
                )
            )


def delete_reverse_related_documents(
    main_model: ESModelType,
    es_document: ESDocumentClassType,
    instance: ESModelType,
    query_string: str,
    affected_fields: list[str],
) -> None:
    """Update reverse related document fields in Elasticsearch when the reverse
    instance is removed.
    :param main_model: The main model to fetch objects from.
    :param es_document: The Elasticsearch document type.
    :param instance: The instance for which the reverse related documents are
    to be updated.
    :param query_string: The query string to filter the main model objects.
    :param affected_fields: The list of field names that are reverse related to
    the instance.
    :return: None
    """

    match instance:
        case Person() if es_document is PersonDocument:  # type: ignore
            # Update the Person document after the reverse instanced is deleted
            main_doc = exists_or_create_doc(
                es_document, instance, avoid_creation=True
            )
            if main_doc:
                # Update parent document in ES.
                transaction.on_commit(
                    partial(
                        update_es_document.delay,
                        es_document.__name__,
                        affected_fields,
                        (compose_app_label(instance), instance.pk),
                        None,
                        None,
                    )
                )
                # Then update all their child documents (Positions)
                transaction.on_commit(
                    partial(
                        update_children_docs_by_query.delay,
                        PositionDocument.__name__,
                        instance.pk,
                        affected_fields,
                    )
                )
        case Docket() if es_document is DocketDocument:  # type: ignore
            # Update the Docket document after the reverse instanced is deleted
            main_doc = exists_or_create_doc(
                es_document, instance, avoid_creation=True
            )
            if main_doc:
                # Update parent document in ES.
                transaction.on_commit(
                    partial(
                        update_es_document.delay,
                        es_document.__name__,
                        affected_fields,
                        (compose_app_label(instance), instance.pk),
                        None,
                        None,
                    )
                )
                # Then update all their child documents (RECAPDocuments)
                transaction.on_commit(
                    partial(
                        update_children_docs_by_query.delay,
                        ESRECAPDocument.__name__,
                        instance.pk,
                        affected_fields,
                    )
                )
        case OpinionCluster() if es_document is OpinionClusterDocument:  # type: ignore
            main_doc = exists_or_create_doc(
                es_document, instance, avoid_creation=True
            )
            if main_doc:
                # Update parent document in ES.
                transaction.on_commit(
                    partial(
                        update_es_document.delay,
                        es_document.__name__,
                        affected_fields,
                        (compose_app_label(instance), instance.pk),
                        None,
                        None,
                    )
                )
                # Then update all their child documents (Positions)
                transaction.on_commit(
                    partial(
                        update_children_docs_by_query.delay,
                        OpinionDocument.__name__,
                        instance.pk,
                        affected_fields,
                    )
                )
        case _:
            main_objects = main_model.objects.filter(
                **{query_string: instance}
            )
            for main_object in main_objects:
                main_doc = exists_or_create_doc(
                    es_document, main_object, avoid_creation=True
                )
                if main_doc:
                    # Update main document in ES.
                    transaction.on_commit(
                        partial(
                            update_es_document.delay,
                            es_document.__name__,
                            affected_fields,
                            (compose_app_label(main_object), main_object.pk),
                            None,
                            None,
                        )
                    )


def avoid_es_audio_indexing(
    instance: ESModelType,
    es_document: ESDocumentClassType,
    update_fields: list[str] | None,
):
    """Check conditions to abort Elasticsearch indexing for Audio instances.
    Avoid indexing for Audio instances which their mp3 file has not been
    processed yet by process_audio_file.

    :param instance: The Audio instance to evaluate for Elasticsearch indexing.
    :param es_document: The Elasticsearch document class.
    :param update_fields: List of fields being updated, or None.
    :return: True if indexing should be avoided, False otherwise.
    """

    if (
        type(instance) == Audio
        and not es_document.exists(instance.pk)
        and (
            not update_fields
            or (update_fields and "processing_complete" not in update_fields)
        )
    ):
        # Avoid indexing Audio instances that haven't been previously indexed
        # in ES and for which 'processing_complete' is not present in update_fields.
        return True
    return False


class ESSignalProcessor(object):
    """Custom signal processor for Elasticsearch documents. It is responsible
    for managing the Elasticsearch index after certain events happen, such as
    saving, deleting, or modifying instances of related models.
    """

    def __init__(self, main_model, es_document, documents_model_mapping):
        self.main_model = main_model
        self.es_document = es_document
        self.documents_model_mapping = documents_model_mapping

        self.setup()

    def setup(self):
        models_save = list(self.documents_model_mapping["save"].keys())
        models_delete = list(self.documents_model_mapping["delete"].keys())
        models_m2m = list(self.documents_model_mapping["m2m"].keys())
        models_reverse_foreign_key = list(
            self.documents_model_mapping["reverse"].keys()
        )
        models_reverse_foreign_key_delete = list(
            self.documents_model_mapping["reverse-delete"].keys()
        )
        main_model = self.main_model.__name__.lower()

        # Connect signals for save
        self.connect_signals(
            models_save,
            self.handle_save,
            {post_save: f"update_related_{main_model}_documents_in_es_index"},
        )
        # Connect signals for deletion
        self.connect_signals(
            models_delete,
            self.handle_delete,
            {post_delete: f"remove_{main_model}_from_es_index"},
        )
        # Connect signals for many-to-many changes
        self.connect_signals(
            models_m2m,
            self.handle_m2m,
            {m2m_changed: f"update_{main_model}_m2m_in_es_index"},
        )
        # Connect signals for save on models with reverse foreign keys
        self.connect_signals(
            models_reverse_foreign_key,
            self.handle_reverse_actions,
            {
                post_save: f"update_reverse_related_{main_model}_on_save",
            },
        )
        # Connect signals for delete on models with reverse-delete foreign keys
        self.connect_signals(
            models_reverse_foreign_key_delete,
            self.handle_reverse_actions_delete,
            {
                post_delete: f"update_reverse_related_{main_model}_on_delete",
            },
        )

    @staticmethod
    def connect_signals(models, handler, signal_to_uid_mapping, weak=False):
        """Helper method to connect signals to a handler for multiple models."""
        for model in models:
            model_name = model.__name__.lower()
            for signal, uid_base in signal_to_uid_mapping.items():
                signal.connect(
                    handler,
                    sender=model,
                    dispatch_uid=f"{uid_base}_{model_name}",
                    weak=weak,
                )

    @elasticsearch_enabled
    def handle_save(
        self,
        sender,
        instance=None,
        created=False,
        update_fields=None,
        **kwargs,
    ):
        """Receiver function that gets called after an object instance is saved"""

        if update_fields and "view_count" in update_fields:
            # If the save includes 'view_count' in the update fields, abort
            # the operation.This indicates that a user view is incrementing
            # the 'view_count' for dockets and opinions.
            return None

        mapping_fields = self.documents_model_mapping["save"][sender]
        if not created:
            update_es_documents(
                self.main_model,
                self.es_document,
                instance,
                created,
                mapping_fields,
            )
        if not mapping_fields:
            if avoid_es_audio_indexing(
                instance, self.es_document, update_fields
            ):
                # This check is required to avoid indexing and triggering
                # search alerts for Audio instances whose MP3 files have not
                # yet been processed by process_audio_file.
                return None

            transaction.on_commit(
                lambda: chain(
                    es_save_document.si(
                        instance.pk,
                        compose_app_label(instance),
                        self.es_document.__name__,
                    ),
                    send_or_schedule_alerts.s(self.es_document._index._name),
                    process_percolator_response.s(),
                ).apply_async()
            )

    @elasticsearch_enabled
    def handle_delete(self, sender, instance, **kwargs):
        """Receiver function that gets called after an object instance is deleted"""
        remove_document_from_es_index.delay(
            self.es_document.__name__, instance.pk
        )

    @elasticsearch_enabled
    def handle_m2m(self, sender, instance=None, action=None, **kwargs):
        """Receiver function that gets called after a m2m relation is modified"""
        if action == "post_add" or action == "post_remove":
            mapping_fields = self.documents_model_mapping["m2m"][sender]
            for key, fields_map in mapping_fields.items():
                affected_field = list(fields_map.keys())[0]
                update_remove_m2m_documents(
                    self.main_model,
                    self.es_document,
                    instance,
                    mapping_fields,
                    affected_field,
                )

    @elasticsearch_enabled
    def handle_reverse_actions(self, sender, instance=None, **kwargs):
        """Receiver function that gets called after a reverse relation is
        created, updated or removed.
        """
        mapping_fields = self.documents_model_mapping["reverse"][sender]
        for query_string, fields_map in mapping_fields.items():
            match instance:
                case BankruptcyInformation() if self.es_document is DocketDocument:  # type: ignore
                    # BankruptcyInformation is a one-to-one relation that can
                    # be re-saved many times without changes. It's better to
                    # check if the indexed fields have changed before
                    # triggering an update.
                    changed_fields = updated_fields(instance, self.es_document)
                    affected_fields = get_fields_to_update(
                        changed_fields, fields_map
                    )
                    if not affected_fields:
                        return None
                case _:
                    try:
                        affected_fields = fields_map[instance.type]
                    except (KeyError, AttributeError):
                        affected_fields = fields_map["all"]

            instance_field = query_string.split("__")[-1]
            update_reverse_related_documents(
                self.main_model,
                self.es_document,
                getattr(instance, instance_field, instance),
                query_string,
                affected_fields,
            )

    @elasticsearch_enabled
    def handle_reverse_actions_delete(self, sender, instance=None, **kwargs):
        """Receiver function that gets called after a reverse relation is
        removed.
        """
        mapping_fields = self.documents_model_mapping["reverse-delete"][sender]
        for query_string, fields_map in mapping_fields.items():
            try:
                affected_fields = fields_map[instance.type]
            except (KeyError, AttributeError):
                affected_fields = fields_map["all"]

            instance_field = query_string.split("__")[-1]
            try:
                instance = getattr(instance, instance_field, instance)
            except ObjectDoesNotExist:
                # The related objects has already been removed, abort.
                return

            delete_reverse_related_documents(
                self.main_model,
                self.es_document,
                instance,
                query_string,
                affected_fields,
            )
