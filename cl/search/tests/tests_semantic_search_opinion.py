import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from elasticsearch_dsl import Document

from cl.search.documents import ES_CHILD_ID, OpinionDocument
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    OpinionClusterFactory,
    OpinionFactory,
)
from cl.search.models import PRECEDENTIAL_STATUS, SEARCH_TYPES, Docket
from cl.tests.cases import ESIndexTestCase, TestCase


class OpinionEmbeddingIndexingTests(ESIndexTestCase, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("search.OpinionCluster")
        court = CourtFactory(
            id="canb",
            jurisdiction="FB",
        )
        cls.opinion_cluster_1 = OpinionClusterFactory(
            docket=DocketFactory(
                court=court,
                docket_number="1:21-cv-1234",
                source=Docket.HARVARD,
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
        )
        cls.opinion_1 = OpinionFactory(
            cluster=cls.opinion_cluster_1,
            html_columbia=(
                "<p>Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
                "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa "
                "quae ab illo inventore veritatis et quasi architecto beatae vitae dicta "
                "sunt explicabo. Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
                "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa unde omnis iste</p>"
            ),
        )
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    def test_opinion_embeddings_field(self) -> None:
        """Test index embeddings into an opinion document."""

        es_opinion_1 = OpinionDocument.get(
            id=ES_CHILD_ID(self.opinion_1.pk).OPINION
        )
        self.assertEqual(es_opinion_1.embeddings, [])

        test_dir = (
            Path(settings.INSTALL_ROOT) / "cl" / "search" / "test_assets"
        )
        with open(
            test_dir / "opinion_1_embeddings.json",
            encoding="utf-8",
        ) as embeddings_file:
            opinion_1_embeddings = json.load(embeddings_file)
            Document.update(
                es_opinion_1,
                **{"embeddings": opinion_1_embeddings["embeddings"]},
                refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
            )

        # Opinion embedding should be now indexed into the document.
        self.assertEqual(
            es_opinion_1.embeddings, opinion_1_embeddings["embeddings"]
        )
