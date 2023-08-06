from typing import Callable, Union

from django.conf import settings
from django.db.models.signals import m2m_changed, post_delete, post_save
from elasticsearch.exceptions import NotFoundError
from elasticsearch_dsl import Document

from cl.lib.command_utils import logger
from cl.search.documents import ParentheticalGroupDocument
from cl.search.models import (
    Citation,
    Docket,
    Opinion,
    OpinionCluster,
    Parenthetical,
    ParentheticalGroup,
)

instance_typing = Union[
    Citation,
    Docket,
    Opinion,
    OpinionCluster,
    Parenthetical,
    ParentheticalGroup,
]
es_document_typing = Union[ParentheticalGroupDocument]


def updated_fields(
    instance: instance_typing,
) -> list[str]:
    """Look for changes in the tracked fields of an instance.
    :param instance: The instance to check for changed fields.
    :return: A list of the names of fields that have changed in the instance.
    """
    # Get the field names being tracked
    tracked_fields = instance.es_pa_field_tracker.fields
    # Check each tracked field to see if it has changed
    changed_fields = [
        field
        for field in tracked_fields
        if getattr(instance, field)
        != instance.es_pa_field_tracker.previous(field)
    ]
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


def document_fields_to_update(
    field_list: list[str], instance: instance_typing, fields_map: dict
) -> dict:
    """Generate a dictionary of fields and values to update based on a
     provided map and an instance.

    :param field_list: A list of field names that need to be updated.
    :param instance: The instance from which field values are to be extracted.
    :param fields_map: A map from which ES field names are to be extracted.
    :return: A dictionary with fields and values to update.
    """

    return {
        fields_map[field]: getattr(instance, field)()
        if field.startswith("get_") and field.endswith("_display")
        else getattr(instance, field)
        for field in field_list
    }


def save_document_in_es(
    instance: instance_typing, es_document: Callable
) -> None:
    """Save a document in Elasticsearch using a provided callable.
    :param instance: The instance of the document to save.
    :param es_document: A Elasticsearch DSL document.
    :return: None
    """
    es_doc = es_document()
    doc = es_doc.prepare(instance)
    es_document(meta={"id": instance.pk}, **doc).save(
        skip_empty=False,
        return_doc_meta=True,
        refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
    )


def get_or_create_doc(
    es_document: es_document_typing, instance: instance_typing
) -> es_document_typing | None:
    """Get or create a document in Elasticsearch.
    :param es_document: The Elasticsearch document type.
    :param instance: The instance of the document to get or create.
    :return: An Elasticsearch document if found, otherwise None.
    """
    try:
        main_doc = es_document.get(id=instance.pk)
    except NotFoundError:
        save_document_in_es(instance, es_document)
        return None
    return main_doc


def remove_doc_from_es_index(
    es_document: es_document_typing, instance_id: int
) -> None:
    """Remove a document from an Elasticsearch index.

    :param es_document: The Elasticsearch document type.
    :param instance_id: The ID of the instance to be removed from the
    Elasticsearch index.
    :return: None
    """
    try:
        doc = es_document.get(id=instance_id)
        doc.delete(refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH)
    except NotFoundError:
        logger.error(
            f"The Audio with ID:{instance_id} can't be deleted from "
            f"the ES index, it doesn't exists."
        )


def update_es_documents(
    main_model: instance_typing,
    es_document: es_document_typing,
    instance: instance_typing,
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
    changed_fields = updated_fields(instance)
    if changed_fields:
        for query, fields_map in mapping_fields.items():
            main_objects = main_model.objects.filter(**{query: instance})
            for main_object in main_objects:
                main_doc = get_or_create_doc(es_document, main_object)
                if not main_doc:
                    return
                fields_to_update = get_fields_to_update(
                    changed_fields, fields_map
                )
                if fields_to_update:
                    Document.update(
                        main_doc,
                        **document_fields_to_update(
                            fields_to_update, instance, fields_map
                        ),
                        refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
                    )


def update_remove_m2m_documents(
    main_model: instance_typing,
    es_document: es_document_typing,
    instance: instance_typing,
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
        main_objects = main_model.objects.filter(**{key: instance})
        for main_object in main_objects:
            main_doc = get_or_create_doc(es_document, main_object)
            if not main_doc:
                return
            get_m2m_value = getattr(main_doc, f"prepare_{affected_field}")(
                main_object
            )
            Document.update(
                main_doc,
                **{affected_field: get_m2m_value},
                refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
            )


def update_reverse_related_documents(
    main_model: instance_typing,
    es_document: es_document_typing,
    instance: instance_typing,
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
    main_objects = main_model.objects.filter(**{query_string: instance})
    for main_object in main_objects:
        main_doc = get_or_create_doc(es_document, main_object)
        if not main_doc:
            return
        Document.update(
            main_doc,
            **{
                field: getattr(main_doc, f"prepare_{field}")(main_object)
                for field in affected_fields
            },
            refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
        )


class ESSignalProcessor(object):
    """Custom signal processor for Elasticsearch documents. It is responsible
    for managing the Elasticsearch index after certain events happen, such as
    saving, deleting, or modifying instances of related models.
    """

    def __init__(self, main_model, es_document, documents_model_mapping):
        self.main_model = main_model
        self.es_document = es_document
        self.documents_model_mapping = documents_model_mapping

        if not settings.ELASTICSEARCH_DISABLED:
            self.setup()

    def setup(self):
        models_save = list(self.documents_model_mapping["save"].keys())
        models_delete = list(self.documents_model_mapping["delete"].keys())
        models_m2m = list(self.documents_model_mapping["m2m"].keys())
        models_reverse_foreign_key = list(
            self.documents_model_mapping["reverse"].keys()
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
        # Connect signals for save and delete on models with reverse foreign keys
        self.connect_signals(
            models_reverse_foreign_key,
            self.handle_reverse_actions,
            {
                post_save: f"update_reverse_related_{main_model}_on_save",
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

    def handle_save(self, sender, instance=None, created=False, **kwargs):
        """Receiver function that gets called after an object instance is saved"""
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
            save_document_in_es(instance, self.es_document)

    def handle_delete(self, sender, instance, **kwargs):
        """Receiver function that gets called after an object instance is deleted"""
        remove_doc_from_es_index(self.es_document, instance.pk)

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

    def handle_reverse_actions(self, sender, instance=None, **kwargs):
        """Receiver function that gets called after a reverse relation is
        created, updated or removed.
        """
        mapping_fields = self.documents_model_mapping["reverse"][sender]
        for query_string, fields_map in mapping_fields.items():
            try:
                affected_fields = fields_map[instance.type]
            except KeyError:
                affected_fields = fields_map["all"]
            instance_field = query_string.split("__")[-1]
            update_reverse_related_documents(
                self.main_model,
                self.es_document,
                getattr(instance, instance_field),
                query_string,
                affected_fields,
            )
