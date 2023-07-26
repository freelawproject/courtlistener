from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from elasticsearch_dsl import Document

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
                **pa_doc.document_mapping_fields(changed_fields, instance)
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
                **pa_doc.document_mapping_fields(changed_fields, instance)
            )


@receiver(
    post_save,
    sender=OpinionCluster,
    dispatch_uid="update_related_es_documents_on_opinion_cluster_save",
)
def update_related_es_documents_on_opinion_cluster_save(
    sender, instance=None, created=False, **kwargs
):
    """Receiver function that gets called after a OpinionCluster instance is saved.
    This function updates the Elasticsearch index for all ParentheticalGroup
    objects related to the saved OpinionCluster instance.
    """
    if created:
        return
    changed_fields = updated_fields(instance)
    if changed_fields:
        parenthetical_groups = ParentheticalGroup.objects.filter(
            opinion__cluster=instance
        )
        for pa in parenthetical_groups:
            pa_doc = ParentheticalGroupDocument.get(id=pa.pk)
            Document.update(
                pa_doc,
                **pa_doc.document_mapping_fields(changed_fields, instance)
            )
