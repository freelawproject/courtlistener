from django.test import TestCase

from cl.recap.mergers import merge_scotus_docket
from cl.search.factories import (
    CourtFactory,
    ScotusDocketDataFactory,
)
from cl.search.models import Docket, ScotusDocketMetadata


class ScotusDocketMergeTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory(id="scotus", jurisdiction="F")

    def test_merge_scotus_docket_creates_docket_and_metadata(self) -> None:
        """Confirm SCOTUS data is merged into Docket and metadata."""

        data = ScotusDocketDataFactory(
            docket_number="23-1434", capital_case=False
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
