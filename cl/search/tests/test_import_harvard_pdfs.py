import json
import logging
import tempfile
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import override_settings

from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    OpinionClusterFactory,
)
from cl.tests.cases import TestCase

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

    class MockFuture(Future):
        def __init__(self):
            super().__init__()
            self._result = None
            self._done = False
            self._condition = MagicMock()  # Create a mock for _condition

        def set_result(self, result):
            self._result = result
            self._done = True

        def result(self, timeout=None):
            if not self._done:
                raise Exception("Future is not done")
            return self._result

        def done(self):
            return self._done

    @patch("cl.search.management.commands.import_harvard_pdfs.as_completed")
    @patch(
        "cl.search.management.commands.import_harvard_pdfs.ThreadPoolExecutor"
    )
    @patch(
        "cl.search.management.commands.import_harvard_pdfs.OpinionCluster.objects.get"
    )
    @patch(
        "cl.search.management.commands.import_harvard_pdfs.HarvardPDFStorage"
    )
    @patch("cl.search.management.commands.import_harvard_pdfs.boto3.client")
    def test_import_harvard_pdfs(
        self,
        mock_boto3_client,
        mock_harvard_storage,
        mock_opinion_cluster_get,
        mock_executor,
        mock_as_completed,
    ):
        # Mock S3 client; "downloading" writes the PDF bytes to the
        # destination path it's given.
        mock_s3 = MagicMock()
        mock_s3.download_file.side_effect = lambda bucket, key, destination: (
            Path(destination).write_bytes(b"%PDF-1.4")
        )
        mock_boto3_client.return_value = mock_s3

        # Mock storage and its save method
        mock_storage = MagicMock()
        mock_storage.save.return_value = "mocked_saved_path.pdf"
        mock_harvard_storage.return_value = mock_storage

        # Mock OpinionCluster.objects.get to return test cluster
        mock_opinion_cluster_get.return_value = self.cluster

        crosswalk_data = [
            {
                "cap_case_id": 1,
                "cl_cluster_id": self.cluster.id,
                "cap_path": "/test/path.json",
            }
        ]

        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        crosswalk_dir = Path(temp_dir.name)
        (crosswalk_dir / "test_crosswalk.json").write_text(
            json.dumps(crosswalk_data)
        )

        # Mock the ThreadPoolExecutor to call process_entry directly
        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.__enter__.return_value = mock_executor_instance

        # Create a mock Future object
        mock_future = self.MockFuture()
        mock_future.set_result(1)  # Simulating that 1 file has been downloaded

        # Directly override the behavior of executor.submit to return the mock Future
        future_to_entry = {}

        def submit_side_effect(func, entry):
            # Call the process_entry function directly with the entry
            result = func(entry)  # Call the function passed to submit
            future_to_entry[mock_future] = entry  # Map the future to the entry
            mock_future.set_result(result)  # Set the result on the mock future
            return mock_future  # Return the mock Future object

        mock_executor_instance.submit.side_effect = submit_side_effect

        # Mock as_completed to return an iterable of mock futures
        mock_as_completed.return_value = [
            mock_future
        ]  # Simulate that it's completed

        call_command("import_harvard_pdfs", crosswalk_dir=str(crosswalk_dir))

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
        self.assertEqual(
            self.cluster.filepath_pdf_harvard, "mocked_saved_path.pdf"
        )
