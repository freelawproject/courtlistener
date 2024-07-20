from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.http import QueryDict

from cl.alerts.models import Alert
from cl.alerts.tasks import es_save_alert_document
from cl.alerts.utils import avoid_indexing_auxiliary_alert
from cl.search.documents import (
    AudioPercolator,
    DocketDocumentPercolator,
    RECAPDocumentPercolator,
    RECAPPercolator,
)
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
            qd = QueryDict(instance.query.encode(), mutable=True)
            if not avoid_indexing_auxiliary_alert(
                RECAPDocumentPercolator.__name__, qd
            ):
                es_save_alert_document.delay(
                    instance.pk, RECAPDocumentPercolator.__name__
                )
            if not avoid_indexing_auxiliary_alert(
                DocketDocumentPercolator.__name__, qd
            ):
                es_save_alert_document.delay(
                    instance.pk, DocketDocumentPercolator.__name__
                )


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
            remove_document_from_es_index.delay(
                RECAPDocumentPercolator.__name__, instance.pk, None
            )
            remove_document_from_es_index.delay(
                DocketDocumentPercolator.__name__, instance.pk, None
            )
