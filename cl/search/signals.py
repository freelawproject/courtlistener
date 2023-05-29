from django.db.models.signals import post_save
from django.dispatch import receiver

from cl.audio.models import Audio
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
