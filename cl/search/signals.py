from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from cl.alerts.send_alerts import percolate_document, send_rt_alerts
from cl.audio.models import Audio
from cl.lib.command_utils import logger
from cl.search.documents import AudioDocument
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
        response = percolate_document(response["_id"], "oral_arguments")
        send_rt_alerts(response, doc)


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
