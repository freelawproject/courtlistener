import json
import tempfile
import os
from unittest.mock import patch, MagicMock, mock_open as mock_open_function
from django.test import override_settings
from django.core.management import call_command
from django.core.files.base import ContentFile
from cl.search.models import OpinionCluster, Court, Docket
from cl.search.management.commands.import_harvard_pdfs import Command
from cl.tests.cases import TransactionTestCase


@override_settings(
    R2_ENDPOINT_URL="http://test-endpoint",
    R2_ACCESS_KEY_ID="test-access-key",
    R2_SECRET_ACCESS_KEY="test-secret-key",
    R2_BUCKET_NAME="test-bucket",
    AWS_STORAGE_BUCKET_NAME="test-cl-bucket",
    AWS_S3_CUSTOM_DOMAIN="test-cl-domain",
    AWS_DEFAULT_ACL="public-read",
    AWS_QUERYSTRING_AUTH=False,
    AWS_S3_MAX_MEMORY_SIZE=16 * 1024 * 1024,
)
class TestImportHarvardPDFs(TransactionTestCase):
    fixtures = ["court_data.json"]

    def setUp(self):
        super().setUp()
        self.court = Court.objects.get(pk="scotus")

        # Create test dockets and clusters
        self.dockets = []
        self.clusters = []
        for i in range(2):
            docket = Docket.objects.create(
                court=self.court,
                case_name=f"Test Case {i+1}",
                source=Docket.DEFAULT,
            )
            self.dockets.append(docket)

            cluster = OpinionCluster.objects.create(
                case_name=f"Test Case {i+1}",
                docket=docket,
                date_filed=f"2023-01-0{i+1}",
            )
            self.clusters.append(cluster)

        # Mock crosswalk data
        self.crosswalk_data = [
            {
                "cap_id": 8118004,
                "cl_id": self.clusters[0].id,
                "cap_path": "/a2d/100/cases/0036-01.json",
            },
            {
                "cap_id": 8118121,
                "cl_id": self.clusters[1].id,
                "cap_path": "/a2d/100/cases/0040-01.json",
            },
        ]

    @patch(
        "cl.search.management.commands.import_harvard_pdfs.HarvardPDFStorage"
    )
    @patch("cl.search.management.commands.import_harvard_pdfs.boto3.client")
    @patch(
        "cl.search.management.commands.import_harvard_pdfs.open",
        new_callable=mock_open_function,
    )
    @patch("cl.search.management.commands.import_harvard_pdfs.tempfile")
    def test_import_harvard_pdfs(
        self, mock_tempfile, mock_open, mock_boto3_client, mock_harvard_storage
    ):
        # Mock the R2 client
        mock_r2 = MagicMock()
        mock_boto3_client.return_value = mock_r2

        # Mock the temporary file
        mock_temp_file = MagicMock()
        mock_temp_file.name = "/tmp/mock_temp_file"
        mock_tempfile.NamedTemporaryFile.return_value.__enter__.return_value = (
            mock_temp_file
        )

        # Mock the file read operation
        mock_open.return_value.__enter__.return_value.read.return_value = (
            b"mock pdf content"
        )

        # Mock the crosswalk file
        crosswalk_mock = mock_open.return_value.__enter__.return_value
        crosswalk_mock.read.return_value = json.dumps(self.crosswalk_data)

        # Mock the HarvardPDFStorage
        mock_storage_instance = MagicMock()
        mock_harvard_storage.return_value = mock_storage_instance
        mock_storage_instance.save.side_effect = lambda name, content: name

        call_command("import_harvard_pdfs")

        # Print debug information
        print(
            f"R2 download_file call count: {mock_r2.download_file.call_count}"
        )
        print(
            f"R2 download_file call args: {mock_r2.download_file.call_args_list}"
        )
        print(
            f"HarvardPDFStorage save call count: {mock_storage_instance.save.call_count}"
        )
        print(
            f"HarvardPDFStorage save call args: {mock_storage_instance.save.call_args_list}"
        )

        # Check R2 interactions
        self.assertEqual(
            mock_r2.download_file.call_count,
            2,
            "R2 download_file should be called twice",
        )

        # Check that the filepath_pdf_harvard field was updated for each cluster
        for cluster in self.clusters:
            cluster.refresh_from_db()
            self.assertIsNotNone(
                cluster.filepath_pdf_harvard,
                f"filepath_pdf_harvard should not be None for cluster {cluster.id}",
            )
            self.assertTrue(
                str(cluster.filepath_pdf_harvard).startswith("harvard_pdf/"),
                f"filepath_pdf_harvard should start with 'harvard_pdf/' for cluster {cluster.id}",
            )

        # Assert that the storage save method was called correctly
        self.assertEqual(
            mock_storage_instance.save.call_count,
            2,
            "HarvardPDFStorage save should be called twice",
        )

        # Check that the correct filepaths were saved
        expected_filepaths = [
            f"harvard_pdf/{cluster.pk}.pdf" for cluster in self.clusters
        ]
        actual_filepaths = [
            call[0][0] for call in mock_storage_instance.save.call_args_list
        ]
        self.assertCountEqual(actual_filepaths, expected_filepaths)

    @patch("cl.search.management.commands.import_harvard_pdfs.boto3.client")
    @patch("cl.search.management.commands.import_harvard_pdfs.open")
    @patch(
        "cl.search.management.commands.import_harvard_pdfs.HarvardPDFStorage"
    )
    def test_import_harvard_pdfs_dry_run(
        self, mock_harvard_storage, mock_open, mock_boto3_client
    ):
        # Mock the R2 client
        mock_r2 = MagicMock()
        mock_boto3_client.return_value = mock_r2

        # Mock the crosswalk file
        mock_open.return_value.__enter__.return_value = MagicMock(
            read=lambda: json.dumps(self.crosswalk_data)
        )

        call_command("import_harvard_pdfs", dry_run=True)

        # Check that R2 was not accessed
        mock_r2.download_file.assert_not_called()
        # Check that the filepath_pdf_harvard field was not updated for any cluster
        for cluster in self.clusters:
            cluster.refresh_from_db()
            self.assertFalse(cluster.filepath_pdf_harvard)

        # Check that the storage was not used
        mock_harvard_storage.return_value.save.assert_not_called()
