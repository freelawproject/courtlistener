from django.db.models.signals import m2m_changed, post_delete, post_save
from elasticsearch_dsl import Document

from cl.lib.command_utils import logger
from cl.search.documents import ParentheticalGroupDocument
from cl.search.models import (
    Citation,
    Docket,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    Parenthetical,
    ParentheticalGroup,
)


def updated_fields(
    instance: Docket | Opinion | OpinionCluster | Parenthetical,
) -> list[str]:
    """Checks for changes in the tracked fields of an instance.
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


def get_fields_intersection(list_1, list_2):
    return [element for element in list_1 if element in list_2]


def document_mapping_fields(
    field_list: list[str], instance, fields_map
) -> dict:
    return {
        fields_map[field][0]: getattr(instance, f"get_{field}_display")()
        if fields_map[field][1] == "display"
        else getattr(instance, field)
        for field in field_list
    }


def save_document_in_es(instance):
    pa_doc = ParentheticalGroupDocument()
    doc = pa_doc.prepare(instance)
    ParentheticalGroupDocument(meta={"id": instance.pk}, **doc).save(
        skip_empty=False, return_doc_meta=True
    )


def remove_pa_from_es_index(instance=None):
    """Receiver function that gets called after a ParentheticalGroup instance
    is deleted.
    This function removes ParentheticalGroup from the ParentheticalGroup index.
    """

    if ParentheticalGroupDocument.exists(id=instance.pk):
        doc = ParentheticalGroupDocument.get(id=instance.pk)
        doc.delete()
    else:
        logger.error(
            f"The Audio with ID:{instance.pk} can't be deleted from "
            f"the ES index, it doesn't exists."
        )


def update_es_documents(main_model, instance, created, mapping_fields):
    if created:
        return
    changed_fields = updated_fields(instance)
    if changed_fields:
        for key, fields_map in mapping_fields.items():
            parenthetical_groups = main_model.objects.filter(**{key: instance})
            for pa in parenthetical_groups:
                pa_doc = ParentheticalGroupDocument.get(id=pa.pk)
                fields_to_update = get_fields_intersection(
                    changed_fields, list(fields_map.keys())
                )
                if fields_to_update:
                    Document.update(
                        pa_doc,
                        **document_mapping_fields(
                            fields_to_update, instance, fields_map
                        ),
                    )


def update_remove_m2m_documents(instance, mapping_fields, affected_field):
    for key, fields_map in mapping_fields.items():
        parenthetical_groups = ParentheticalGroup.objects.filter(
            **{key: instance}
        )
        for pa in parenthetical_groups:
            pa_doc = ParentheticalGroupDocument.get(id=pa.pk)
            get_m2m_value = getattr(pa_doc, "prepare_" + affected_field)(pa)
            Document.update(
                pa_doc,
                **{affected_field: get_m2m_value},
            )


def update_reverse_related_documents(
    instance, mapping_fields, affected_fields
):
    for key, fields_map in mapping_fields.items():
        parenthetical_groups = ParentheticalGroup.objects.filter(
            **{key: instance}
        )
        for pa in parenthetical_groups:
            pa_doc = ParentheticalGroupDocument.get(id=pa.pk)
            Document.update(
                pa_doc,
                **{
                    field: getattr(pa_doc, "prepare_" + field)(pa)
                    for field in affected_fields
                },
            )


class CustomSignalProcessor(object):
    def __init__(self, documents_model_dicts):
        self.main_model = documents_model_dicts[0]
        self.documents_model_mapping = documents_model_dicts[1]
        self.setup()

    def setup(self):
        models_save = list(self.documents_model_mapping[0].keys())
        models_delete = [ParentheticalGroup]
        models_m2m = [OpinionCluster.panel.through, OpinionsCited]
        models_reverse_foreign_key = [Citation]

        # Connect each signal to the respective handler

        for model in models_save:
            post_save.connect(
                self.handle_save,
                sender=model,
                dispatch_uid="update_related_es_documents_on_{}_save".format(
                    model.__name__.lower()
                ),
                weak=False,
            )
        for model in models_delete:
            post_delete.connect(
                self.handle_delete,
                sender=model,
                dispatch_uid="remove_{}_from_es_index".format(
                    model.__name__.lower()
                ),
            )
        for model in models_m2m:
            m2m_changed.connect(
                self.handle_m2m,
                sender=model,
                dispatch_uid="update_{}_m2m_changed_in_es_index".format(
                    model.__name__.lower()
                ),
            )
        for model in models_reverse_foreign_key:
            post_save.connect(
                self.handle_reverse_actions,
                sender=model,
                dispatch_uid="update_reverse_related_es_documents_on_{}_save".format(
                    model.__name__.lower()
                ),
            )
            post_delete.connect(
                self.handle_reverse_actions,
                sender=model,
                dispatch_uid="update_reverse_related_es_documents_on_{}_delete".format(
                    model.__name__.lower()
                ),
            )

    def handle_save(self, sender, instance=None, created=False, **kwargs):
        """Receiver function that gets called after a Docket instance is saved.
        This function updates the Elasticsearch index for all ParentheticalGroup
        objects related to the saved Docket instance.
        """

        mapping_fields = self.documents_model_mapping[0][sender]
        update_es_documents(self.main_model, instance, created, mapping_fields)
        if not mapping_fields:
            save_document_in_es(instance)

    @staticmethod
    def handle_delete(sender, instance, **kwargs):
        """Receiver function that gets called after a Docket instance is saved.
        This function updates the Elasticsearch index for all ParentheticalGroup
        objects related to the saved Docket instance.
        """

        if sender == ParentheticalGroup:
            remove_pa_from_es_index(instance)

    @staticmethod
    def handle_m2m(sender, instance=None, action=None, **kwargs):
        """Receiver function that gets called after a Docket instance is saved.
        This function updates the Elasticsearch index for all ParentheticalGroup
        objects related to the saved Docket instance.
        """
        if action == "post_add" or action == "post_remove":
            if sender == OpinionCluster.panel.through:
                mapping_fields = {
                    "opinion__cluster": {
                        "panel_ids": "panel_ids",
                    },
                }
                affected_field = "panel_ids"
                update_remove_m2m_documents(
                    instance, mapping_fields, affected_field
                )

            if sender == OpinionsCited:
                mapping_fields = {
                    "opinion": {
                        "cites": "cites",
                    },
                }
                affected_field = "cites"
                update_remove_m2m_documents(
                    instance, mapping_fields, affected_field
                )

    @staticmethod
    def handle_reverse_actions(sender, instance=None, **kwargs):
        """Receiver function that gets called after a Docket instance is saved.
        This function updates the Elasticsearch index for all ParentheticalGroup
        objects related to the saved Docket instance.
        """
        if sender == Citation:
            mapping_fields = {
                "opinion__cluster": {
                    "citation": "citation",
                },
            }
            if instance.type == Citation.NEUTRAL:
                affected_fields = ["neutralCite", "citation"]
            elif instance.type == Citation.LEXIS:
                affected_fields = ["lexisCite", "citation"]
            else:
                affected_fields = ["citation"]

            update_reverse_related_documents(
                instance.cluster, mapping_fields, affected_fields
            )
