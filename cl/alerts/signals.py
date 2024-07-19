from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from cl.alerts.models import Alert
from cl.alerts.tasks import es_save_alert_document
from cl.lib.command_utils import logger
from cl.search.documents import AudioPercolator, RECAPPercolator
from cl.search.models import SEARCH_TYPES
from cl.search.tasks import remove_document_from_es_index


@receiver(
    post_save,
    sender=Alert,
    dispatch_uid="create_or_update_alert_in_es_index",
)
def create_or_update_alert_in_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Alert instance is saved.
    This method creates or updates an Alert object in the Percolator index
    """

    if settings.ELASTICSEARCH_DISABLED:
        return

    match instance.alert_type:
        case SEARCH_TYPES.ORAL_ARGUMENT:
            es_save_alert_document.delay(instance.pk, AudioPercolator.__name__)
        case SEARCH_TYPES.RECAP if settings.PERCOLATOR_SEARCH_ALERTS_ENABLED:
            es_save_alert_document.delay(instance.pk, RECAPPercolator.__name__)


@receiver(
    post_delete,
    sender=Alert,
    dispatch_uid="remove_alert_from_es_index",
)
def remove_alert_from_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Alert instance is deleted.
    This function removes Alert from the Percolator index.
    """
    if settings.ELASTICSEARCH_DISABLED:
        return

    match instance.alert_type:
        case SEARCH_TYPES.ORAL_ARGUMENT:
            # Check if the document exists before deleting it
            remove_document_from_es_index.delay(
                AudioPercolator.__name__, instance.pk, None
            )
        case SEARCH_TYPES.RECAP:
            remove_document_from_es_index.delay(
                RECAPPercolator.__name__, instance.pk, None
            )
