import traceback

from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.http import QueryDict
from django_elasticsearch_dsl.signals import post_index
from elasticsearch.exceptions import RequestError, TransportError

from cl.alerts.models import Alert
from cl.alerts.send_alerts import percolate_document, send_rt_alerts
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import build_es_main_query
from cl.search.documents import AudioDocument, AudioPercolator
from cl.search.forms import SearchForm
from cl.search.models import SEARCH_TYPES


@receiver(
    post_index,
    sender=AudioDocument,
    dispatch_uid="post_index_audio",
)
def post_index_audio(sender, **kwargs):
    """After the document has been indexed, percolate it to see if it triggers
    a query and send search alerts.
    """
    document = kwargs["instance"]
    instance_data = getattr(document, "_instance_data", None)
    if instance_data is not None:
        response = percolate_document(instance_data)
        send_rt_alerts(response, instance_data)


@receiver(
    post_save,
    sender=Alert,
    dispatch_uid="create_or_update_alert_in_es_index",
)
def create_or_update_alert_in_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Alert instance is saved.
    This function updates the Elasticsearch the AudioPercolator with the Alert.
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
        try:
            percolator_query = AudioPercolator(
                meta={"id": instance.pk},
                rate=instance.rate,
                percolator_query=query_dict,
            )
            percolator_query.save()
        except (TransportError, ConnectionError, RequestError) as e:
            logger.warning(
                f"Error storing the query in percolator: {query_dict}"
            )
            logger.warning(f"Error was: {e}")
            if settings.DEBUG is True:
                traceback.print_exc()


@receiver(
    post_delete,
    sender=Alert,
    dispatch_uid="remove_alert_from_es_index",
)
def remove_alert_from_es_index(sender, instance=None, **kwargs):
    """Receiver function that gets called after an Alert instance is deleted.
    This function removes Alert from the AudioPercolator index.
    """
    try:
        # Check if the document exists before deleting it
        if AudioPercolator.exists(id=instance.pk):
            doc = AudioPercolator.get(id=instance.pk)
            doc.delete()
    except (TransportError, ConnectionError, RequestError) as e:
        logger.warning(f"Error deleting Alert with ID:{instance.pk} from ES")
        logger.warning(f"Error was: {e}")
        if settings.DEBUG is True:
            traceback.print_exc()
