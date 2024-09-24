import json
import logging
from unittest.mock import MagicMock, patch, mock_open

from django.core.management import call_command
from django.test import override_settings
from cl.tests.cases import TestCase

from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    OpinionClusterFactory,
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@override_settings(
    CAP_R2_ENDPOINT_URL="http://test-endpoint",
    CAP_R2_ACCESS_KEY_ID="test-access-key",
    CAP_R2_SECRET_ACCESS_KEY="test-secret-key",
    CAP_R2_BUCKET_NAME="test-bucket",
    AWS_STORAGE_BUCKET_NAME="test-cl-bucket",
    AWS_S3_CUSTOM_DOMAIN="test-cl-domain",
    AWS_DEFAULT_ACL="public-read",
    AWS_QUERYSTRING_AUTH=False,
    AWS_S3_MAX_MEMORY_SIZE=16 * 1024 * 1024,
)
class TestImportHarvardPDFs(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="test")
        cls.docket = DocketFactory(court=cls.court)
        cls.cluster = OpinionClusterFactory(docket=cls.docket)

    @patch("cl.search.management.commands.import_harvard_pdfs.tqdm")
    @patch(
        "cl.search.management.commands.import_harvard_pdfs.OpinionCluster.objects.get"
    )
    @patch(
        "cl.search.management.commands.import_harvard_pdfs.HarvardPDFStorage"
    )
    @patch("cl.search.management.commands.import_harvard_pdfs.boto3.client")
    @patch("cl.search.management.commands.import_harvard_pdfs.os.listdir")
    def test_import_harvard_pdfs(
        self,
        mock_listdir,
        mock_boto3_client,
        mock_harvard_storage,
        mock_opinion_cluster_get,
        mock_tqdm,
    ):
        # Setup mocks
        mock_listdir.return_value = ["test_crosswalk.json"]
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        mock_storage = MagicMock()
        mock_harvard_storage.return_value = mock_storage
        mock_opinion_cluster_get.return_value = self.cluster
        mock_tqdm.side_effect = (
            lambda x, *args, **kwargs: x
        )  # Make tqdm a pass-through function

        crosswalk_data = [
            {
                "cap_case_id": 1,
                "cl_cluster_id": self.cluster.id,
                "cap_path": "/test/path.json",
            }
        ]

        # Mock file operations
        m = mock_open(read_data=json.dumps(crosswalk_data))
        with patch("builtins.open", m):
            call_command("import_harvard_pdfs")

        # Assert expected behavior
        # 1. Downloading the PDF from CAP
        # 2. Retrieving the OpinionCluster
        # 3. Saving the PDF to storage
        self.assertEqual(
            mock_s3.download_file.call_count,
            1,
            "download_file should be called once",
        )
        self.assertEqual(
            mock_opinion_cluster_get.call_count,
            1,
            "OpinionCluster.objects.get should be called once",
        )
        self.assertEqual(
            mock_storage.save.call_count,
            1,
            "save should be called once",
        )

        # Verify that the cluster's filepath_pdf_harvard field was updated
        self.cluster.refresh_from_db()
        self.assertIsNotNone(self.cluster.filepath_pdf_harvard)
