import time
from collections.abc import Callable

from django.db.models import QuerySet

from cl import settings
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.documents import OpinionClusterDocument, OpinionDocument
from cl.search.models import Opinion, OpinionCluster
from cl.search.tasks import (
    build_bulk_cites_doc,
    build_cite_count_update,
    index_documents_in_bulk,
)


class Command(VerboseCommand):
    help = """Update OpinionClusterDocument.citeCount and OpinionDocument.cites

    Useful to re index these fields after Elastic got unsynced from the DB when
    running `find_citations` with the flag --disable-citation-count
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--reindex-target",
            choices=["citeCount", "cites"],
            help="What ElasticSearch Document field to update",
        )
        parser.add_argument(
            "--start-id",
            type=int,
            default=None,
            help="An OpinionCluster.id or Opinion.id to start the batch reindex from",
        )
        parser.add_argument(
            "--end-id",
            type=int,
            default=None,
            help="An OpinionCluster.id or or Opinion.id where the batch updates end",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Size of the ids batch to send in a single Elastic bulk update",
        )

    def handle(self, *args, **options):
        reindex_target = options["reindex_target"]
        start_id = options["start_id"]
        end_id = options["end_id"]

        if not (start_id and end_id):
            raise ValueError("`start_id` and `end_id` should have values")

        if reindex_target == "citeCount":
            update_fn = self.update_cite_count
            # re index clusters that have citation_count greater than 0
            qs = (
                OpinionCluster.objects.filter(id__gte=start_id, id__lt=end_id)
                .exclude(citation_count=0)
                .order_by("id")
            )
        elif reindex_target == "cites":
            update_fn = self.update_cites
            # re index opinions that actually cite other opinions
            qs = (
                Opinion.objects.filter(id__gte=start_id, id__lt=end_id)
                .exclude(opinions_cited__isnull=True)
                .order_by("id")
            )

        self.update_es_in_batches(qs, update_fn, options["batch_size"])

    def update_es_in_batches(
        self, queryset: QuerySet, update_fn: Callable, batch_size: int
    ) -> None:
        """Batch a queryset and call the updater function over batches

        :param queryset: the queryset to iterate over
        :param update_fn: a function that takes a list of ids as input
        :param batch_size: the size of each batch
        """
        model_name = queryset.model.__name__
        batch = []

        for index, cluster_id in enumerate(
            queryset.only("id").values_list("id", flat=True)
        ):
            batch.append(cluster_id)

            if index % batch_size == 0:
                logger.info(
                    "Starting batch update: %s from %s to %s",
                    model_name,
                    batch[0],
                    batch[-1],
                )
                start_time = time.perf_counter()
                update_fn(batch)
                logger.info(
                    "Finished in %.2f seconds",
                    time.perf_counter() - start_time,
                )
                batch = []

        # catch the last incomplete batch
        update_fn(batch)

    @staticmethod
    def update_cite_count(cluster_ids_to_update: list[int]) -> None:
        """Updates OpinionClusterDocument.citeCount

        :param cluster_ids_to_update: cluster ids
        """
        documents_to_update = build_cite_count_update(cluster_ids_to_update)
        index_documents_in_bulk(documents_to_update)

        if settings.ELASTICSEARCH_DSL_AUTO_REFRESH:
            # Set auto-refresh, used for testing.
            OpinionClusterDocument._index.refresh()

    @staticmethod
    def update_cites(opinion_ids: list[int]) -> None:
        """Updates OpinionDocument.cites

        :param opinion_ids: the opinion ids
        """
        base_doc = {
            "_op_type": "update",
            "_index": OpinionClusterDocument._index._name,
        }

        documents_to_update = []
        for child_id in opinion_ids:
            cites_doc_to_update, _ = build_bulk_cites_doc(
                OpinionDocument, child_id, Opinion
            )
            cites_doc_to_update.update(base_doc)
            documents_to_update.append(cites_doc_to_update)

        index_documents_in_bulk(documents_to_update)

        if settings.ELASTICSEARCH_DSL_AUTO_REFRESH:
            # Set auto-refresh, used for testing.
            OpinionClusterDocument._index.refresh()
