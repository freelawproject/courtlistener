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
        with cls.captureOnCommitCallbacks(execute=True) as callbacks:
            cls.opinion_cluster_2 = OpinionClusterFactory(
                docket=DocketFactory(
                    court=cls.court,
                    docket_number="1:21-cv-1235",
                    source=Docket.HARVARD,
                ),
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
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
        with self.captureOnCommitCallbacks(execute=True):
            opinion_2 = OpinionFactory(
                cluster=self.opinion_cluster_2,
                html_columbia=("<p>Sed ut perspiciatis</p>"),
            )
            opinion_3 = OpinionFactory(
                cluster=self.opinion_cluster_2,
                html_columbia=("<p>Sed ut perspiciatis</p>"),
            )

        for opinion in (opinion_2, opinion_3):
            self.assertEqual(
                OpinionDocument.get(
                    id=ES_CHILD_ID(opinion.pk).OPINION
                ).embeddings,
                [],
            )

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

        for opinion in (opinion_2, opinion_3):
            self.assertTrue(
                OpinionDocument.get(
                    id=ES_CHILD_ID(opinion.pk).OPINION
                ).embeddings
            )

    def test_cl_index_embeddings_from_inventory(self):
        """Test cl_index_embeddings command using an S3 inventory file."""
        with self.captureOnCommitCallbacks(execute=True):
            opinion_4 = OpinionFactory(
                cluster=self.opinion_cluster_2,
                html_columbia=("<p>Sed ut perspiciatis</p>"),
            )
            opinion_5 = OpinionFactory(
                cluster=self.opinion_cluster_2,
                html_columbia=("<p>Sed ut perspiciatis</p>"),
            )
        for opinion in (opinion_4, opinion_5):
            self.assertEqual(
                OpinionDocument.get(
                    id=ES_CHILD_ID(opinion.pk).OPINION
                ).embeddings,
                [],
            )

        csv_lines = [
            f'"com-courtlistener-storage","embeddings/opinions/freelawproject/'
            f'modernbert-embed-base_finetune_512/{opinion_4.pk}.json","2025-06-24T00:00:00.000Z"',
            f'"com-courtlistener-storage","embeddings/opinions/freelawproject/'
            f'modernbert-embed-base_finetune_512/{opinion_5.pk}.json","2025-06-24T00:00:00.000Z"',
        ]
        mock_csv_content = "\n".join(csv_lines) + "\n"
        with (
            mock.patch(
                "cl.search.tasks.AWSMediaStorage.open",
                side_effect=mock_read_from_s3,
            ),
            mock.patch("pathlib.Path.exists", return_value=True),
            mock.patch(
                "pathlib.Path.open", mock.mock_open(read_data=mock_csv_content)
            ),
        ):
            call_command(
                "cl_index_embeddings",
                batch_size=2,
                inventory_file="test_inventory.csv",
                inventory_rows=len(csv_lines),
            )

        # Confirm embeddings are indexed.
        for opinion in (opinion_4, opinion_5):
            self.assertTrue(
                OpinionDocument.get(
                    id=ES_CHILD_ID(opinion.pk).OPINION
                ).embeddings
            )
