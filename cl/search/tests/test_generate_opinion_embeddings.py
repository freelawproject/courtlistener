import datetime
import json
import os
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command

from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    OpinionClusterFactory,
    OpinionFactory,
)
from cl.search.models import PRECEDENTIAL_STATUS, Docket, Opinion
from cl.tests.cases import TestCase


class FakeS3IntelligentTieringStorage:
    """A fake storage class that simulates saving files to S3 by storing them
    locally.
    """

    def __init__(self):
        self.saved_files = {}

    def save(self, file_path, content):
        file_data = content.read()
        if isinstance(file_data, bytes):
            file_data = file_data.decode("utf-8")
        self.saved_files[file_path] = file_data


def inception_batch_request_mock(opinions_to_vectorize):
    documents = opinions_to_vectorize["documents"]
    return [
        {
            "id": opinion_data["id"],
            "embeddings": [
                {
                    "chunk_number": 1,
                    "chunk": f"search_document: {opinion_data["text"]}",
                    "embedding": [0.03163226321339607],
                },
            ],
        }
        for opinion_data in documents
    ]


@patch(
    "cl.search.tasks.embeddings_cache_key",
    return_value="test_embeddings:",
)
class GenerateOpinionEmbeddingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
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
            date_filed=datetime.date(2020, 8, 15),
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
            ),  # roughly ~104 tokens
        )
        cls.opinion_ignored_min_size = OpinionFactory(
            cluster=cls.opinion_cluster_1,
            html_columbia=(
                "<p>Sed ut perspiciatis unde omnis iste natus error sit voluptatem</p>"
            ),  # roughly ~18 tokens
        )

        cls.opinion_cluster_2 = OpinionClusterFactory(
            date_filed=datetime.date(2020, 8, 15),
            docket=DocketFactory(
                court=court,
                docket_number="123456",
                source=Docket.HARVARD,
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
        )
        cls.opinion_2 = OpinionFactory(
            cluster=cls.opinion_cluster_2,
            plain_text="Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
            "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa "
            "quae ab illo inventore veritatis et quasi architecto beatae vitae dicta "
            "sunt explicabo. Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
            "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa  ",
        )  # roughly ~100 tokens
        cls.opinion_cluster_3 = OpinionClusterFactory(
            date_filed=datetime.date(2020, 8, 15),
            docket=DocketFactory(
                court=court,
                docket_number="123457",
                source=Docket.HARVARD,
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
        )
        cls.opinion_3 = OpinionFactory(
            cluster=cls.opinion_cluster_3,
            plain_text="Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
            "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa "
            "quae ab illo inventore veritatis et quasi architecto beatae vitae dicta "
            "sunt explicabo. Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
            "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa ",
        )  # roughly ~100 tokens

        cls.opinion_cluster_4 = OpinionClusterFactory(
            date_filed=datetime.date(2020, 8, 15),
            docket=DocketFactory(
                court=court,
                docket_number="123458",
                source=Docket.HARVARD,
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
        )
        cls.opinion_4 = OpinionFactory(
            cluster=cls.opinion_cluster_4,
            plain_text="Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
            "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa "
            "quae ab illo inventore veritatis et quasi architecto beatae vitae dicta "
            "sunt explicabo. Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
            "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa "
            "Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
            "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa "
            "quae ab illo inventore veritatis et quasi architecto beatae vitae dicta "
            "sunt explicabo. Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
            "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa "
            "Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
            "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa "
            "quae ab illo inventore veritatis et quasi architecto beatae vitae dicta "
            "sunt explicabo. Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
            "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa ",
        )  # roughly ~296 tokens

    @staticmethod
    def _get_opinions_to_vectorize(batch):
        opinions = Opinion.objects.filter(id__in=batch).with_best_text()
        opinions_to_vectorize = [
            {"id": opinion.pk, "text": opinion.clean_text}
            for opinion in opinions
        ]
        return {"documents": opinions_to_vectorize}

    @patch("cl.search.tasks.S3IntelligentTieringStorage")
    @patch(
        "cl.search.tasks.inception_batch_request",
        side_effect=inception_batch_request_mock,
    )
    def test_embed_opinions(
        self,
        mock_inception_batch_request,
        mock_aws_media_storage,
        mock_embeddings_cache_key,
    ):
        """Test that the generate_opinion_embeddings command:

        - Calls the inception service to get text embeddings.
        - Saves each embedding record to S3 (using mock).
        """
        # Create an instance of fake S3IntelligentTieringStorage.
        fake_storage = FakeS3IntelligentTieringStorage()
        mock_aws_media_storage.return_value = fake_storage
        call_command(
            "generate_opinion_embeddings",
            token_count=10000,
            start_id=0,
            count=3,
        )

        # Verify that inception_batch_request was called once.
        mock_inception_batch_request.assert_called_once()

        # For each embedding record, verify that a file was saved with the expected content.
        documents_embedded_count = len(fake_storage.saved_files)
        # Only two opinions should be requested: opinion_1 and opinion_2,
        # since the count is set to 2.
        expected_embeddings = inception_batch_request_mock(
            self._get_opinions_to_vectorize(
                [self.opinion_1.pk, self.opinion_2.pk]
            )
        )

        self.assertEqual(
            documents_embedded_count,
            len(expected_embeddings),
            "Wrong number of documents.",
        )
        for path, embedding in fake_storage.saved_files.items():
            with self.subTest(embedding):
                embedding_dict = json.loads(embedding)
                record_id = embedding_dict["id"]
                expected_path = os.path.join(
                    "embeddings",
                    "opinions",
                    settings.NLP_EMBEDDING_MODEL,
                    f"{record_id}.json",
                )
                self.assertEqual(expected_path, path)
                self.assertIn(embedding_dict, expected_embeddings)

    @patch("cl.search.tasks.S3IntelligentTieringStorage")
    def test_limit_batch_size(
        self, mock_aws_media_storage, mock_embeddings_cache_key
    ):
        """Test generate_opinion_embeddings limit the batch size properly."""

        # Create an instance of fake S3IntelligentTieringStorage.
        fake_storage = FakeS3IntelligentTieringStorage()
        mock_aws_media_storage.return_value = fake_storage

        with patch(
            "cl.search.tasks.inception_batch_request",
            side_effect=inception_batch_request_mock,
        ) as mock_inception_batch_request:
            call_command(
                "generate_opinion_embeddings",
                token_count=250,
                start_id=0,
                count=4,
            )
            # The embedding generation should be split into two inception
            # requests due to the specified batch size.
            # Verify that inception_batch_request was called twice.
            self.assertEqual(mock_inception_batch_request.call_count, 2)

        # For each embedding record, verify that a file was saved with the expected content.
        documents_embedded_count = len(fake_storage.saved_files)
        expected_embeddings_1 = inception_batch_request_mock(
            self._get_opinions_to_vectorize(
                [self.opinion_1.pk, self.opinion_2.pk]
            )
        )
        expected_embeddings_2 = inception_batch_request_mock(
            self._get_opinions_to_vectorize([self.opinion_3.pk])
        )

        expected_embeddings = expected_embeddings_1 + expected_embeddings_2
        self.assertEqual(documents_embedded_count, len(expected_embeddings))
        for path, embedding in fake_storage.saved_files.items():
            with self.subTest(embedding):
                embedding_dict = json.loads(embedding)
                record_id = embedding_dict["id"]
                expected_path = os.path.join(
                    "embeddings",
                    "opinions",
                    settings.NLP_EMBEDDING_MODEL,
                    f"{record_id}.json",
                )
                self.assertEqual(expected_path, path)
                self.assertIn(embedding_dict, expected_embeddings)

    @patch("cl.search.tasks.S3IntelligentTieringStorage")
    @patch("cl.search.management.commands.generate_opinion_embeddings.logger")
    def test_log_long_documents(
        self, mock_logger, mock_aws_media_storage, mock_embeddings_cache_key
    ):
        """Test log documents that individually exceed the batch size."""

        # Create an instance of fake S3IntelligentTieringStorage.
        fake_storage = FakeS3IntelligentTieringStorage()
        mock_aws_media_storage.return_value = fake_storage

        with patch(
            "cl.search.tasks.inception_batch_request",
            side_effect=inception_batch_request_mock,
        ) as mock_inception_batch_request:
            call_command(
                "generate_opinion_embeddings",
                token_count=250,
                start_id=0,
            )
            # The embedding generation should be split into two inception
            # requests due to the specified batch size.
            # Verify that inception_batch_request was called twice.
            self.assertEqual(mock_inception_batch_request.call_count, 2)

        mock_logger.error.assert_called_with(
            "The opinion ID:%s exceeds the batch size limit.",
            self.opinion_4.pk,
        )
