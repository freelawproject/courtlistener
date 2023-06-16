from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.http import QueryDict

from cl.alerts.models import Alert
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import build_es_main_query
from cl.search.documents import AudioDocument, AudioPercolator
from cl.search.forms import SearchForm
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

    if f"type={SEARCH_TYPES.ORAL_ARGUMENT}" in instance.query:
        # Make a dict from the query string.
        qd = QueryDict(instance.query.encode(), mutable=True)
        cd = {}
        search_form = SearchForm(qd)
        if search_form.is_valid():
            cd = search_form.cleaned_data
        search_query = AudioDocument.search()
        (
            query,
            total_query_results,
            top_hits_limit,
        ) = build_es_main_query(search_query, cd)
        query_dict = query.to_dict()["query"]
        percolator_query = AudioPercolator(
            meta={"id": instance.pk},
            rate=instance.rate,
            percolator_query=query_dict,
        )
        percolator_query.save()


@receiver(
    post_delete,
    sender=Alert,
    dispatch_uid="remove_alert_from_es_index",
)
def remove_alert_from_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Alert instance is deleted.
    This function removes Alert from the AudioPercolator index.
    """
    # Check if the document exists before deleting it
    if AudioPercolator.exists(id=instance.pk):
        doc = AudioPercolator.get(id=instance.pk)
        doc.delete()
    else:
        logger.warning(f"Error deleting Alert with ID:{instance.pk} from ES")
