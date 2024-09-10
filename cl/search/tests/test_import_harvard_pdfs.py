import json
from unittest.mock import patch, MagicMock
from django.test import override_settings
from django.core.management import call_command
from django.core.files.base import ContentFile
from cl.search.models import OpinionCluster, Court, Docket
from cl.lib.storage import IncrementingAWSMediaStorage
from cl.tests.cases import TransactionTestCase


@override_settings(
    R2_ENDPOINT_URL="http://test-endpoint",
    R2_ACCESS_KEY_ID="test-access-key",
    R2_SECRET_ACCESS_KEY="test-secret-key",
    R2_BUCKET_NAME="test-bucket",
)
class TestImportHarvardPDFs(TransactionTestCase):
    fixtures = ["court_data.json"]

    def setUp(self):
        super().setUp()
        # Use an existing court from the fixture
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

    @patch("cl.search.management.commands.import_harvard_pdfs.boto3.client")
    @patch("cl.search.management.commands.import_harvard_pdfs.open")
    @patch(
        "cl.search.management.commands.import_harvard_pdfs.IncrementingAWSMediaStorage"
    )
    def test_import_harvard_pdfs(
        self, mock_storage, mock_open, mock_boto3_client
    ):
        # Mock the S3 client
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"mock pdf content")
        }

        mock_open.return_value.__enter__.return_value = MagicMock(
            read=lambda: json.dumps(self.crosswalk_data)
        )

        # Mock the storage
        mock_storage.return_value.save.side_effect = lambda name, content: name

        call_command("import_harvard_pdfs")

        self.assertEqual(mock_s3.get_object.call_count, 2)

        # Check that the filepath_pdf_harvard field was updated for each cluster
        updated_filepaths = []
        for cluster in self.clusters:
            cluster.refresh_from_db()
            self.assertIsNotNone(cluster.filepath_pdf_harvard)
            self.assertTrue(
                str(cluster.filepath_pdf_harvard).startswith("harvard_pdf/")
            )
            updated_filepaths.append(str(cluster.filepath_pdf_harvard))

        # Assert that the storage save method was called correctly
        mock_storage.return_value.save.assert_called()
        self.assertEqual(mock_storage.return_value.save.call_count, 2)

        # Check that the correct filepaths were saved
        expected_filepaths = [
            f"harvard_pdf/{cluster.pk}.pdf" for cluster in self.clusters
        ]
        self.assertCountEqual(updated_filepaths, expected_filepaths)

    @patch("cl.search.management.commands.import_harvard_pdfs.boto3.client")
    @patch("cl.search.management.commands.import_harvard_pdfs.open")
    @patch(
        "cl.search.management.commands.import_harvard_pdfs.IncrementingAWSMediaStorage"
    )
    def test_import_harvard_pdfs_dry_run(
        self, mock_storage, mock_open, mock_boto3_client
    ):
        # Mock the S3 client
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        mock_open.return_value.__enter__.return_value = MagicMock(
            read=lambda: json.dumps(self.crosswalk_data)
        )

        call_command("import_harvard_pdfs", dry_run=True)
        mock_s3.get_object.assert_not_called()

        # Check that the filepath_pdf_harvard field was not updated for any cluster
        for cluster in self.clusters:
            cluster.refresh_from_db()
            self.assertFalse(cluster.filepath_pdf_harvard)

        mock_storage.return_value.save.assert_not_called()
