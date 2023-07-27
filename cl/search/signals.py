from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from elasticsearch_dsl import Document

from cl.lib.command_utils import logger
from cl.search.documents import ParentheticalGroupDocument
from cl.search.models import (
    Docket,
    Opinion,
    OpinionCluster,
    ParentheticalGroup,
)


def updated_fields(instance: Docket | Opinion | OpinionCluster) -> list[str]:
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


@receiver(
    post_save,
    sender=Docket,
    dispatch_uid="update_related_es_documents_on_docket_save",
)
def update_related_es_documents_on_docket_save(
    sender, instance=None, created=False, **kwargs
):
    """Receiver function that gets called after a Docket instance is saved.
    This function updates the Elasticsearch index for all ParentheticalGroup
    objects related to the saved Docket instance.
    """
    if created:
        return

    changed_fields = updated_fields(instance)
    if changed_fields:
        parenthetical_groups = ParentheticalGroup.objects.filter(
            opinion__cluster__docket=instance
        )
        for pa in parenthetical_groups:
            pa_doc = ParentheticalGroupDocument.get(id=pa.pk)
            Document.update(
                pa_doc,
                **pa_doc.document_mapping_fields(changed_fields, instance),
            )


@receiver(
    post_save,
    sender=Opinion,
    dispatch_uid="update_related_es_documents_on_opinion_save",
)
def update_related_es_documents_on_opinion_save(
    sender, instance=None, created=False, **kwargs
):
    """Receiver function that gets called after a Opinion instance is saved.
    This function updates the Elasticsearch index for all ParentheticalGroup
    objects related to the saved Opinion instance.
    """
    if created:
        return
    changed_fields = updated_fields(instance)
    if changed_fields:
        parenthetical_groups = ParentheticalGroup.objects.filter(
            opinion=instance
        )
        for pa in parenthetical_groups:
            pa_doc = ParentheticalGroupDocument.get(id=pa.pk)
            Document.update(
                pa_doc,
                **pa_doc.document_mapping_fields(changed_fields, instance),
            )


def get_fields_intersection(list_1, list_2):
    return [element for element in list_1 if element in list_2]


def document_mapping_fields(
    field_list: list[str], instance, fields_map
) -> dict:
    return {
        fields_map[field]: getattr(instance, field) for field in field_list
    }


@receiver(
    post_save,
    sender=OpinionCluster,
    dispatch_uid="update_related_es_documents_on_opinion_cluster_save",
)
def update_related_es_documents_on_opinion_cluster_save(
    sender, instance=None, created=False, **kwargs
):
    """Receiver function that gets called after an OpinionCluster instance is saved.
    This function updates the Elasticsearch index for all ParentheticalGroup
    objects related to the saved OpinionCluster instance.
    """
    if created:
        return

    changed_fields = updated_fields(instance)
    mapping_fields = {
        "representative__describing_opinion__cluster": {
            "slug": "describing_opinion_cluster_slug"
        },
        "opinion__cluster": {
            "case_name": "caseName",
            "citation_count": "citeCount",
            "date_filed": "dateFiled",
            "slug": "opinion_cluster_slug",
            "docket_id": "docket_id",
            "judges": "judge",
            "nature_of_suit": "suitNature",
        },
    }

    if changed_fields:
        for key, fields_map in mapping_fields.items():
            parenthetical_groups = ParentheticalGroup.objects.filter(
                **{key: instance}
            )
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


@receiver(
    post_delete,
    sender=ParentheticalGroup,
    dispatch_uid="remove_pa_from_es_index",
)
def remove_pa_from_es_index(sender, instance=None, **kwargs):
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


@receiver(
    post_save,
    sender=ParentheticalGroup,
    dispatch_uid="create_or_update_pa_in_es_index",
)
def create_or_update_pa_in_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after a ParentheticalGroup instance
    is saved.
    This function adds a ParentheticalGroup to the ParentheticalGroup index.
    """

    pa_doc = ParentheticalGroupDocument()
    doc = pa_doc.prepare(instance)
    ParentheticalGroupDocument(meta={"id": instance.pk}, **doc).save(
        skip_empty=False, return_doc_meta=True
    )
