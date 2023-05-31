from django.dispatch import receiver
from django_elasticsearch_dsl.signals import post_index

from cl.alerts.send_alerts import percolate_document, send_rt_alerts
from cl.search.documents import AudioDocument


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
