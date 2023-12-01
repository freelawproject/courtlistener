from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from cl.alerts.models import Alert
from cl.alerts.tasks import es_save_alert_document
from cl.lib.command_utils import logger
from cl.search.documents import AudioPercolator
from cl.search.models import SEARCH_TYPES


@receiver(
    post_save,
    sender=Alert,
    dispatch_uid="create_or_update_alert_in_es_index",
)
def create_or_update_alert_in_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Alert instance is saved.
    This method creates or updates an Alert object in the AudioPercolator index
    """
    if settings.ELASTICSEARCH_DISABLED:
        return

    if f"type={SEARCH_TYPES.ORAL_ARGUMENT}" in instance.query:
        es_save_alert_document.delay(instance.pk, AudioPercolator.__name__)


@receiver(
    post_delete,
    sender=Alert,
    dispatch_uid="remove_alert_from_es_index",
)
def remove_alert_from_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Alert instance is deleted.
    This function removes Alert from the AudioPercolator index.
    """
    if settings.ELASTICSEARCH_DISABLED:
        return

    # Check if the document exists before deleting it
    if AudioPercolator.exists(id=instance.pk):
        doc = AudioPercolator.get(id=instance.pk)
        doc.delete(refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH)
    else:
        logger.warning(f"Error deleting Alert with ID:{instance.pk} from ES")
