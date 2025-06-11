import json
from io import BytesIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from elasticsearch_dsl import Document

from cl.search.documents import ES_CHILD_ID, OpinionDocument
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    EmbeddingsDataFactory,
    OpinionClusterFactory,
    OpinionFactory,
)
from cl.search.models import PRECEDENTIAL_STATUS, Docket
from cl.tests.cases import ESIndexTestCase, TestCase


def mock_read_from_s3(file_path, r):
    """Mock bucket.open() to return fake embeddings JSON content for
    a given opinion ID."""
    opinion_id_str = Path(file_path).stem.split("_")[-1]
    opinion_id = int(opinion_id_str)
    fake_embedding_data = EmbeddingsDataFactory.build(id=opinion_id)
    fake_json = json.dumps(fake_embedding_data).encode("utf-8")
    return BytesIO(fake_json)


class OpinionEmbeddingIndexingTests(ESIndexTestCase, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("search.OpinionCluster")
        cls.court = CourtFactory(
            id="canb",
            jurisdiction="FB",
        )

    def test_opinion_embeddings_field(self) -> None:
        """Test index embeddings into an opinion document."""
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            opinion_cluster_1 = OpinionClusterFactory(
                docket=DocketFactory(
                    court=self.court,
                    docket_number="1:21-cv-1234",
                    source=Docket.HARVARD,
                ),
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            )
            opinion_1 = OpinionFactory(
                cluster=opinion_cluster_1,
                html_columbia=(
                    "<p>Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
                    "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa "
                    "quae ab illo inventore veritatis et quasi architecto beatae vitae dicta "
                    "sunt explicabo. Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
                    "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa unde omnis iste</p>"
                ),
            )

        es_opinion_1 = OpinionDocument.get(
            id=ES_CHILD_ID(opinion_1.pk).OPINION
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
        es_opinion_1 = OpinionDocument.get(
            id=ES_CHILD_ID(opinion_1.pk).OPINION
        )
        self.assertEqual(
            es_opinion_1.embeddings, opinion_1_embeddings["embeddings"]
        )

    def test_cl_index_embeddings(self) -> None:
        """Test cl_index_embeddings command"""

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            opinion_cluster_2 = OpinionClusterFactory(
                docket=DocketFactory(
                    court=self.court,
                    docket_number="1:21-cv-1235",
                    source=Docket.HARVARD,
                ),
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            )
            opinion_2 = OpinionFactory(
                cluster=opinion_cluster_2,
                html_columbia=("<p>Sed ut perspiciatis</p>"),
            )
            opinion_3 = OpinionFactory(
                cluster=opinion_cluster_2,
                html_columbia=("<p>Sed ut perspiciatis</p>"),
            )

        es_opinion_2 = OpinionDocument.get(
            id=ES_CHILD_ID(opinion_2.pk).OPINION
        )
        self.assertEqual(es_opinion_2.embeddings, [])

        es_opinion_3 = OpinionDocument.get(
            id=ES_CHILD_ID(opinion_3.pk).OPINION
        )
        self.assertEqual(es_opinion_3.embeddings, [])

        with mock.patch(
            "cl.search.tasks.AWSMediaStorage.open",
            side_effect=mock_read_from_s3,
        ):
            call_command(
                "cl_index_embeddings",
                batch_size=2,
                indexing_queue="celery",
                start_id=0,
            )

        es_opinion_2 = OpinionDocument.get(
            id=ES_CHILD_ID(opinion_2.pk).OPINION
        )
        # Opinion embedding should be now indexed into the document.
        self.assertTrue(es_opinion_2.embeddings)
        es_opinion_3 = OpinionDocument.get(
            id=ES_CHILD_ID(opinion_3.pk).OPINION
        )
        # Opinion embedding should be now indexed into the document.
        self.assertTrue(es_opinion_3.embeddings)
