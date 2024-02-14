from django.apps import AppConfig
from django.conf import settings
from django.core.management import call_command
from django.db.models.signals import post_migrate
from elasticsearch.exceptions import ConnectionError, ConnectionTimeout
from elasticsearch_dsl import connections

from cl.lib.command_utils import logger
from cl.lib.decorators import retry


class SearchConfig(AppConfig):
    name = "cl.search"

    def ready(self):
        # Implicitly connect a signal handlers decorated with @receiver.
        from cl.search import signals

        if settings.DEVELOPMENT and not settings.TESTING:
            # Only for DEVELOPMENT and not in TESTING:
            # Execute create_search_index after the post_migrate signal
            # is triggered in the search app.
            post_migrate.connect(create_search_index, sender=self)


@retry((ConnectionError, ConnectionTimeout), tries=5, delay=5)
def check_and_create_es_index(es_document) -> None:
    """Check Elasticsearch cluster availability and create the index if it
    doesn't exist.

    :param es_document: The Elasticsearch document type.
    :return: None
    """
    model_label = f"{es_document.django.model._meta.app_label}.{es_document.django.model.__name__}"
    es = connections.get_connection()
    health = es.cluster.health(wait_for_status="green", timeout="10s")
    logger.info("Cluster status is now: %s", health["status"])
    index_exists = es.indices.exists(index=es_document._index._name)
    if not index_exists:
        call_command(
            "search_index", "--create", "--models", model_label, verbosity=0
        )


def create_search_index(sender, **kwargs):
    """Runs the Elasticsearch index creation process for a predefined set of
    document models. Iterates through a list of Elasticsearch document models,
    and for each, it checks if the corresponding index exists in the ES cluster.
    If an index does not exist, it attempts to create it.

    :return: None
    """
    from cl.search.documents import (
        AudioDocument,
        AudioPercolator,
        DocketDocument,
        OpinionClusterDocument,
        ParentheticalGroupDocument,
        PersonDocument,
    )

    es_document_models = [
        DocketDocument,
        PersonDocument,
        AudioDocument,
        OpinionClusterDocument,
        ParentheticalGroupDocument,
        AudioPercolator,
    ]
    for es_document in es_document_models:
        check_and_create_es_index(es_document)
