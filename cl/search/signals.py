from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from elasticsearch_dsl import Document

from cl.alerts.send_alerts import send_or_schedule_alerts
from cl.audio.models import Audio
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import es_index_exists
from cl.people_db.models import (
    ABARating,
    Education,
    Person,
    PoliticalAffiliation,
    Position,
)
from cl.search.documents import (
    PEOPLE_DOCS_TYPE_ID,
    AudioDocument,
    PersonDocument,
    PositionDocument,
)
from cl.search.models import Docket


@receiver(
    post_save,
    sender=Docket,
    dispatch_uid="update_related_es_documents_on_docket_save",
)
def update_related_es_documents_on_docket_save(
    sender, instance=None, **kwargs
):
    """Receiver function that gets called after a Docket instance is saved.
    This function updates the Elasticsearch index for all Audio objects related
    to the saved Docket instance.

    We'll add here more ES documents that depend on Docket values.
    """
    related_audios = Audio.objects.filter(docket=instance)
    for audio in related_audios:
        # Update the index for each related Audio
        AudioDocument().update(audio)


@receiver(
    m2m_changed,
    sender=Audio.panel.through,
    dispatch_uid="audio_panel_changed_update_in_es",
)
def audio_panel_changed_update_in_es(
    sender, instance=None, action=None, **kwargs
):
    """Receiver function that gets called after a new panel object is added or
    removed to the Audio m2m relation.

    This function updates the Elasticsearch index for the related Audio instance
    """
    if action == "post_add" or action == "post_remove":
        audio_doc = AudioDocument()
        doc = audio_doc.prepare(instance)
        AudioDocument(meta={"id": instance.pk}, **doc).save(skip_empty=False)


@receiver(
    post_save,
    sender=Audio,
    dispatch_uid=" create_or_update_audio_in_es_index",
)
def create_or_update_audio_in_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Audio instance is saved.
    This method creates or updates an Audio object in the AudioDocument index.

    Also triggers search alerts for new documents added to the index.
    """

    audio_doc = AudioDocument()
    doc = audio_doc.prepare(instance)
    response = AudioDocument(meta={"id": instance.pk}, **doc).save(
        skip_empty=False, return_doc_meta=True
    )
    if response["_version"] == 1:
        send_or_schedule_alerts(response["_id"], "oral_arguments", doc)


@receiver(
    post_delete,
    sender=Audio,
    dispatch_uid="remove_audio_from_es_index",
)
def remove_audio_from_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Audio instance is deleted.
    This function removes Audio from the AudioPercolator index.
    """
    # Check if the document exists before deleting it
    if AudioDocument.exists(id=instance.pk):
        doc = AudioDocument.get(id=instance.pk)
        doc.delete()
    else:
        logger.error(
            f"The Audio with ID:{instance.pk} can't be deleted from "
            f"the ES index, it doesn't exists."
        )


@receiver(
    post_save,
    sender=Person,
    dispatch_uid="create_or_update_person_in_es_index",
)
def create_or_update_person_in_es_index(
    sender, instance=None, created=False, **kwargs
):
    """Receiver function that gets called after a Person instance is saved.
    This method creates or updates a Person object in the PersonDocument index.
    """

    if es_index_exists("people_db_index") and not created:
        person_doc = PersonDocument()
        doc = person_doc.prepare(instance)
        PersonDocument(meta={"id": instance.pk}, **doc).save(
            skip_empty=False, return_doc_meta=True
        )


@receiver(
    post_save,
    sender=Position,
    dispatch_uid="create_or_update_position_in_es_index",
)
def create_or_update_position_in_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after a Position instance is saved.
    This method creates or updates a Position object in the PositionDocument index.
    """
    parent_id = getattr(instance.person, "pk", None)
    if not es_index_exists("people_db_index") or not parent_id:
        return
    if PersonDocument.exists(id=parent_id) and instance.person.is_judge:
        position_doc = PositionDocument()
        doc = position_doc.prepare(instance)
        doc_id = PEOPLE_DOCS_TYPE_ID(instance.pk).POSITION
        PositionDocument(
            meta={"id": doc_id},
            _routing=parent_id,
            **doc,
        ).save(skip_empty=False)

    elif not PersonDocument.exists(id=parent_id) and instance.person.is_judge:
        # Add the Judge first.
        person_doc = PersonDocument()
        doc = person_doc.prepare(instance.person)
        PersonDocument(meta={"id": parent_id}, **doc).save(
            skip_empty=False, return_doc_meta=True
        )
        # Then add the position object.
        position_doc = PositionDocument()
        doc = position_doc.prepare(instance)
        doc_id = PEOPLE_DOCS_TYPE_ID(instance.pk).POSITION
        PositionDocument(
            meta={"id": doc_id},
            _routing=parent_id,
            **doc,
        ).save(skip_empty=False)


@receiver(
    post_save,
    sender=Education,
    dispatch_uid=" create_or_update_education_in_es_index",
)
def create_or_update_education_in_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Education instance is saved.
    This method creates or updates an Education object in the EducationDocument
    index.
    """

    parent_id = getattr(instance.person, "pk", None)
    if (
        es_index_exists("people_db_index")
        and parent_id
        and PersonDocument.exists(id=parent_id)
    ):
        person_doc = PersonDocument()
        doc = person_doc.prepare(instance.person)
        PersonDocument(meta={"id": instance.person.pk}, **doc).save(
            skip_empty=False, return_doc_meta=True
        )


@receiver(
    post_save,
    sender=PoliticalAffiliation,
    dispatch_uid=" create_or_update_political_affiliation_in_es_index",
)
def create_or_update_affiliation_in_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Education instance is saved.
    This method creates or updates an Education object in the EducationDocument
    index.
    """

    parent_id = getattr(instance.person, "pk", None)
    if (
        es_index_exists("people_db_index")
        and parent_id
        and PersonDocument.exists(id=parent_id)
    ):
        doc = PersonDocument.get(id=instance.person.pk)
        political_affiliation = getattr(doc, "prepare_political_affiliation")(
            instance.person
        )
        political_affiliation_id = getattr(
            doc, "prepare_political_affiliation_id"
        )(instance.person)

        Document.update(
            doc,
            **{
                "political_affiliation": political_affiliation,
                "political_affiliation_id": political_affiliation_id,
            },
        )


@receiver(
    post_delete,
    sender=Person,
    dispatch_uid="remove_person_from_es_index",
)
def remove_person_from_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after a Person instance is deleted.
    This function removes a Person document and their related child documents
    from the ES index.
    """
    # Check if the document exists before deleting it
    if PersonDocument.exists(id=instance.pk):
        doc = PersonDocument.get(id=instance.pk)
        doc.delete()

        position_objects = instance.positions.all()
        for position in position_objects:
            doc_id = PEOPLE_DOCS_TYPE_ID(position.pk).POSITION
            if PositionDocument.exists(id=doc_id):
                doc = PositionDocument.get(id=doc_id)
                doc.delete()

    else:
        logger.error(
            f"The Person with ID:{instance.pk} can't be deleted from "
            f"the ES index, it doesn't exists."
        )


@receiver(
    post_delete,
    sender=Position,
    dispatch_uid="remove_position_from_es_index",
)
def remove_position_from_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after a Position instance is deleted.
    This function removes a Position document from the ES index.
    """
    # Check if the document exists before deleting it

    doc_id = PEOPLE_DOCS_TYPE_ID(instance.pk).POSITION
    if PositionDocument.exists(id=doc_id):
        doc = PositionDocument.get(id=doc_id)
        doc.delete()

    else:
        logger.error(
            f"The Position instance with ID:{instance.pk} can't be deleted from "
            f"the ES index, it doesn't exists."
        )


@receiver(
    post_delete,
    sender=Education,
    dispatch_uid="remove_education_from_es_index",
)
def remove_education_from_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Education instance is deleted.
    This function removes an Education fields from the ES index.
    """
    parent_id = getattr(instance.person, "pk", None)
    if (
        es_index_exists("people_db_index")
        and parent_id
        and PersonDocument.exists(id=parent_id)
    ):
        person_doc = PersonDocument()
        doc = person_doc.prepare(instance.person)
        PersonDocument(meta={"id": instance.person.pk}, **doc).save(
            skip_empty=False, return_doc_meta=True
        )


@receiver(
    post_save,
    sender=ABARating,
    dispatch_uid="create_or_update_aba_ratings_in_es_index",
)
def create_or_update_aba_ratings_in_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an ABARating instance is saved.
    This method creates or updates an ABARating object in the PersonDocument
    index.
    """

    parent_id = getattr(instance.person, "pk", None)
    if (
        es_index_exists("people_db_index")
        and parent_id
        and PersonDocument.exists(id=parent_id)
    ):
        person_doc = PersonDocument()
        doc = person_doc.prepare(instance.person)
        PersonDocument(meta={"id": instance.person.pk}, **doc).save(
            skip_empty=False, return_doc_meta=True
        )

@receiver(
    post_delete,
    sender=ABARating,
    dispatch_uid="delete_aba_ratings_in_es_index",
)
def delete_aba_ratings_in_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an ABARating instance is deleted.
    This method removes ABARating fields in the PersonDocument
    index.
    """

    parent_id = getattr(instance.person, "pk", None)
    if (
        es_index_exists("people_db_index")
        and parent_id
        and PersonDocument.exists(id=parent_id)
    ):
        person_doc = PersonDocument()
        doc = person_doc.prepare(instance.person)
        PersonDocument(meta={"id": instance.person.pk}, **doc).save(
            skip_empty=False, return_doc_meta=True
        )
