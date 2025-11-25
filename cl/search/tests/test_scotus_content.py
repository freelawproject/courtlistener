from unittest import mock

from django.core.files.base import ContentFile
from django.test import TestCase

from cl.corpus_importer.tasks import download_qp_scotus_pdf
from cl.recap.mergers import merge_scotus_docket
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    ScotusDocketDataFactory,
)
from cl.search.models import Docket, ScotusDocketMetadata


class ScotusDocketMergeTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory(id="scotus", jurisdiction="F")
        cls.lower_court = CourtFactory(
            id="ca2",
            full_name="United States Court of Appeals for the Second Circuit",
            jurisdiction="A",
        )

    def test_merge_scotus_docket_creates_docket_and_metadata(self) -> None:
        """Confirm SCOTUS data is merged into Docket and metadata."""

        data = ScotusDocketDataFactory(
            docket_number="23-1434",
            capital_case=False,
            lower_court="United States Court of Appeals for the Second Circuit",
            lower_court_case_numbers=["22-16375", "22-16622"],
        )
        docket = merge_scotus_docket(data)
        docket.refresh_from_db()

        # Docket fields
        self.assertEqual(docket.court_id, self.court.pk)
        self.assertEqual(docket.source, Docket.SCRAPER)
        self.assertEqual(docket.docket_number, data["docket_number"])
        self.assertEqual(docket.case_name, data["case_name"])
        self.assertEqual(docket.date_filed, data["date_filed"])
        self.assertEqual(docket.appeal_from_str, data["lower_court"])

        self.assertEqual(docket.appeal_from_str, data["lower_court"])
        self.assertEqual(docket.appeal_from_id, self.lower_court.pk)

        # ScotusDocketMetadata fields
        metadata = docket.scotus_metadata
        self.assertFalse(metadata.capital_case)
        self.assertEqual(
            metadata.discretionary_court_decision,
            data["discretionary_court_decision"],
        )
        self.assertEqual(metadata.linked_with, data["links"])
        self.assertEqual(
            metadata.questions_presented_url, data["questions_presented"]
        )

        # OriginatingCourtInformation fields
        oci = docket.originating_court_information
        expected_numbers = "22-16375, 22-16622"
        self.assertEqual(oci.docket_number, expected_numbers)
        self.assertEqual(
            oci.date_judgment,
            data["lower_court_decision_date"],
        )
        self.assertEqual(
            oci.date_rehearing_denied,
            data["lower_court_rehearing_denied_date"],
        )

    def test_merge_scotus_docket_updates_existing_docket(self) -> None:
        """Confirm merging again updates an existing SCOTUS docket."""

        data = ScotusDocketDataFactory(
            docket_number="23A1434", case_name="Old Name", capital_case=False
        )
        docket = merge_scotus_docket(data)
        docket.refresh_from_db()

        dockets = Docket.objects.all()
        self.assertEqual(dockets.count(), 1)
        scotus_metadata = ScotusDocketMetadata.objects.all()
        self.assertEqual(scotus_metadata.count(), 1)

        # Updated data.
        data = ScotusDocketDataFactory(
            case_name="New SCOTUS Case Name",
            docket_number="23A1434",
            capital_case=True,
            linked_with="23-6433",
            lower_court_case_numbers=["23-6433"],
        )
        updated_docket = merge_scotus_docket(data)
        updated_docket.refresh_from_db()
        self.assertEqual(dockets.count(), 1)
        self.assertEqual(scotus_metadata.count(), 1)

        self.assertEqual(updated_docket.pk, docket.pk)
        self.assertEqual(updated_docket.source, Docket.SCRAPER)
        self.assertEqual(updated_docket.case_name, "New SCOTUS Case Name")
        self.assertEqual(updated_docket.date_filed, data["date_filed"])

        # ScotusDocketMetadata fields
        metadata = updated_docket.scotus_metadata
        self.assertTrue(metadata.capital_case)
        self.assertEqual(
            metadata.discretionary_court_decision,
            data["discretionary_court_decision"],
        )
        self.assertEqual(metadata.linked_with, data["links"])
        self.assertEqual(
            metadata.questions_presented_url, data["questions_presented"]
        )

    def test_merge_scotus_docket_missing_docket_number(self) -> None:
        """Confirm ValueError is raised when docket_number is missing."""

        data = ScotusDocketDataFactory(
            case_name="New SCOTUS Case Name", docket_number=None
        )

        with self.assertRaisesMessage(
            ValueError,
            "Docket number can't be missing in SCOTUS dockets.",
        ):
            merge_scotus_docket(data)

    @mock.patch("cl.corpus_importer.tasks.is_pdf", return_value=True)
    @mock.patch("cl.corpus_importer.tasks.requests.get")
    def test_download_qp_scotus_pdf_downloads_and_stores_file(
        self,
        mock_get,
        mock_is_pdf,
    ) -> None:
        """Confirm the SCOTUS QP PDF is downloaded and stored."""

        docket = DocketFactory.create(court=self.court)
        scotus_meta = ScotusDocketMetadata.objects.create(
            docket=docket,
            questions_presented_url="https://www.supremecourt.gov/qp.pdf",
        )
        self.assertFalse(scotus_meta.questions_presented_file)

        # Mock the response from requests.get
        mock_response = mock.Mock()
        mock_response.iter_content.return_value = [b"fake pdf content"]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        download_qp_scotus_pdf.delay(docket.id)

        mock_get.assert_called_once_with(
            scotus_meta.questions_presented_url,
            stream=True,
            timeout=60,
            headers={"User-Agent": "Free Law Project"},
        )

        scotus_meta.refresh_from_db()

        # Confirm the file was stored
        self.assertTrue(scotus_meta.questions_presented_file)
        self.assertTrue(
            scotus_meta.questions_presented_file.name.endswith("-qp.pdf")
        )

    @mock.patch("cl.corpus_importer.tasks.logger.info")
    @mock.patch("cl.corpus_importer.tasks.requests.get")
    def test_download_qp_scotus_pdf_skips_if_file_already_present(
        self,
        mock_get,
        mock_logger_info,
    ) -> None:
        """Confirm download is skipped when questions_presented_file exists."""

        docket = DocketFactory.create(court=self.court)
        scotus_meta = ScotusDocketMetadata.objects.create(
            docket=docket,
            questions_presented_url="https://www.supremecourt.gov/qp.pdf",
        )
        scotus_meta.questions_presented_file.save(
            "existing.pdf",
            ContentFile(b"existing content"),
            save=True,
        )

        download_qp_scotus_pdf.delay(docket.id)

        # No GET request should have been made
        mock_get.assert_not_called()

        mock_logger_info.assert_called_with(
            "SCOTUS PDF download: questions_presented_file already present "
            "for docket %s; skipping.",
            docket.id,
        )

    @mock.patch("cl.recap.mergers.logger")
    def test_logs_error_when_lower_court_not_found(self, mock_logger) -> None:
        """Confirm merge logs error when lower court is not found in courts-db."""
        data = ScotusDocketDataFactory(
            docket_number="23-1435",
            lower_court="Imaginary Court of The Dragons",
            lower_court_case_numbers=["10-1000"],
        )

        docket = merge_scotus_docket(data)
        docket.refresh_from_db()

        self.assertEqual(docket.appeal_from_str, data["lower_court"])
        self.assertIsNone(docket.appeal_from)

        mock_logger.error.assert_called_with(
            "Could not map lower court from name '%s' for SCOTUS docket.",
            "Imaginary Court of The Dragons",
        )

    @mock.patch("cl.recap.mergers.find_court")
    @mock.patch("cl.recap.mergers.logger")
    def test_logs_error_when_lower_court_ambiguous(
        self,
        mock_logger,
        mock_find_court,
    ) -> None:
        """Confirm merge logs error when lower courts-db lookup is ambiguous."""
        mock_find_court.return_value = ["mab", "mad"]

        data = ScotusDocketDataFactory(
            docket_number="23-1436",
            lower_court="District of Massachusetts",
            lower_court_case_numbers=["10-2000"],
        )

        docket = merge_scotus_docket(data)
        docket.refresh_from_db()

        self.assertEqual(docket.appeal_from_str, data["lower_court"])
        self.assertIsNone(docket.appeal_from)

        mock_logger.error.assert_called_with(
            "Ambiguous lower court name '%s' in courts-db: %s",
            "District of Massachusetts",
            ["mab", "mad"],
        )

    @mock.patch("cl.recap.mergers.find_court")
    @mock.patch("cl.recap.mergers.logger")
    def test_logs_error_when_lower_court_id_missing_in_db(
        self,
        mock_logger,
        mock_find_court,
    ) -> None:
        """Confirm merge logs error when lower court_id does not exist in DB."""
        mock_find_court.return_value = ["cadc123"]

        data = ScotusDocketDataFactory(
            docket_number="23-1437",
            lower_court="Non-existent Court",
            lower_court_case_numbers=["10-3000"],
        )

        docket = merge_scotus_docket(data)
        docket.refresh_from_db()

        self.assertEqual(docket.appeal_from_str, data["lower_court"])
        self.assertIsNone(docket.appeal_from)

        mock_logger.error.assert_called_with(
            "Court object does not exist in DB for id '%s' (name: '%s').",
            "cadc123",
            "Non-existent Court",
        )
