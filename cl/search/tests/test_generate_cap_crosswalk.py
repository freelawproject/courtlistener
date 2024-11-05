import json
import os
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import MagicMock, patch

import pytz
from django.core.management import call_command
from django.test import override_settings

from cl.tests.cases import SimpleTestCase


@override_settings(
    CAP_R2_ENDPOINT_URL="http://test-endpoint",
    CAP_R2_ACCESS_KEY_ID="test-access-key",
    CAP_R2_SECRET_ACCESS_KEY="test-secret-key",
    CAP_R2_BUCKET_NAME="test-bucket",
)
class TestGenerateCapCrosswalk(SimpleTestCase):
    @patch(
        "cl.search.management.commands.generate_cap_crosswalk.Command.fetch_reporters_metadata"
    )
    @patch(
        "cl.search.management.commands.generate_cap_crosswalk.Command.fetch_volumes_for_reporter"
    )
    @patch(
        "cl.search.management.commands.generate_cap_crosswalk.Command.fetch_cases_metadata"
    )
    @patch(
        "cl.search.management.commands.generate_cap_crosswalk.Command.find_matching_case"
    )
    def test_generate_cap_crosswalk_creates_file(
        self,
        mock_find_matching_case,
        mock_fetch_cases_metadata,
        mock_fetch_volumes,
        mock_fetch_reporters,
    ):
        # Mock fetch_reporters_metadata
        mock_fetch_reporters.return_value = [
            {"slug": "U.S.", "short_name": "U.S."}
        ]

        # Mock fetch_volumes_for_reporter
        mock_fetch_volumes.return_value = ["1"]

        # Mock fetch_cases_metadata
        mock_fetch_cases_metadata.return_value = [
            {
                "id": 1,
                "name_abbreviation": "Test Case",
                "decision_date": "2023-01-01",
                "citations": [{"cite": "1 U.S. 1"}],
                "file_name": "test_case",
            }
        ]

        # Mock find_matching_case
        mock_opinion_cluster = MagicMock()
        mock_opinion_cluster.id = 100
        mock_find_matching_case.return_value = mock_opinion_cluster

        # Call the command
        call_command(
            "generate_cap_crosswalk",
            output_dir="/opt/courtlistener/cl/search/crosswalks",
        )

        # Check if crosswalk file was created
        expected_file_path = (
            "/opt/courtlistener/cl/search/crosswalks/U_S_.json"
        )
        self.assertTrue(
            os.path.exists(expected_file_path),
            f"Crosswalk file not found at {expected_file_path}",
        )

        # Check the content of the file
        with open(expected_file_path, "r") as f:
            crosswalk_data = json.load(f)
            self.assertEqual(len(crosswalk_data), 1)
            self.assertEqual(crosswalk_data[0]["cap_case_id"], 1)
            self.assertEqual(crosswalk_data[0]["cl_cluster_id"], 100)
            self.assertEqual(
                crosswalk_data[0]["cap_path"], "/U.S./1/cases/test_case.json"
            )

        # Clean up the created file
        os.remove(expected_file_path)

        # Verify that our mocked methods were called
        mock_fetch_reporters.assert_called_once()
        mock_fetch_volumes.assert_called_once_with("U.S.")
        mock_fetch_cases_metadata.assert_called_once_with("U.S.", "1")
        mock_find_matching_case.assert_called_once()

    @patch(
        "cl.search.management.commands.generate_cap_crosswalk.Command.fetch_reporters_metadata"
    )
    @patch(
        "cl.search.management.commands.generate_cap_crosswalk.Command.fetch_volumes_for_reporter"
    )
    @patch(
        "cl.search.management.commands.generate_cap_crosswalk.Command.fetch_cases_metadata"
    )
    @patch(
        "cl.search.management.commands.generate_cap_crosswalk.Command.find_matching_case"
    )
    def test_generate_cap_crosswalk_with_updated_after(
        self,
        mock_find_matching_case,
        mock_fetch_cases_metadata,
        mock_fetch_volumes,
        mock_fetch_reporters,
    ):
        mock_fetch_reporters.return_value = [
            {"slug": "U.S.", "short_name": "U.S."}
        ]

        mock_fetch_volumes.return_value = ["1"]

        test_cases = [
            {
                "id": 1,
                "name_abbreviation": "Old Case",
                "decision_date": "2023-01-01",
                "citations": [{"cite": "1 U.S. 1"}],
                "file_name": "old_case",
                "last_updated": "2024-03-18T00:00:00+00:00",
            },
            {
                "id": 2,
                "name_abbreviation": "New Case",
                "decision_date": "2023-01-02",
                "citations": [{"cite": "1 U.S. 2"}],
                "file_name": "new_case",
                "last_updated": "2024-03-20T00:00:00+00:00",
            },
        ]

        # Set up mock to return filtered cases based on date
        def mock_fetch_cases(reporter_slug, volume):
            cutoff_date = datetime.fromisoformat("2024-03-19T00:00:00+00:00")
            return [
                case
                for case in test_cases
                if datetime.fromisoformat(case["last_updated"]) > cutoff_date
            ]

        mock_fetch_cases_metadata.side_effect = mock_fetch_cases

        mock_opinion_cluster = MagicMock()
        mock_opinion_cluster.id = 100
        mock_find_matching_case.return_value = mock_opinion_cluster

        # Call the command with updated_after param set return only newer case
        output_dir = "/opt/courtlistener/cl/search/crosswalks"
        call_command(
            "generate_cap_crosswalk",
            output_dir=output_dir,
            updated_after="2024-03-19T00:00:00+00:00",
        )

        # Check if crosswalk file was created
        expected_file_path = f"{output_dir}/U_S_.json"
        self.assertTrue(os.path.exists(expected_file_path))

        with open(expected_file_path, "r") as f:
            crosswalk_data = json.load(f)
            # Verify only one case is present
            self.assertEqual(len(crosswalk_data), 1)

            # Verify it's the newer case
            self.assertEqual(crosswalk_data[0]["cap_case_id"], 2)
            self.assertEqual(
                crosswalk_data[0]["cap_path"], "/U.S./1/cases/new_case.json"
            )

            # Verify the old case is not present
            old_case_entries = [
                entry
                for entry in crosswalk_data
                if entry["cap_case_id"] == 1
                or entry["cap_path"] == "/U.S./1/cases/old_case.json"
            ]
            self.assertEqual(
                len(old_case_entries),
                0,
                "Found old case in crosswalk when it should have been filtered out",
            )

        os.remove(expected_file_path)

        mock_fetch_reporters.assert_called_once()
        mock_fetch_volumes.assert_called_once_with("U.S.")
        mock_fetch_cases_metadata.assert_called_once_with("U.S.", "1")
        self.assertEqual(mock_find_matching_case.call_count, 1)

    @patch(
        "cl.search.management.commands.generate_cap_crosswalk.Command.fetch_reporters_metadata"
    )
    @patch(
        "cl.search.management.commands.generate_cap_crosswalk.Command.fetch_volumes_for_reporter"
    )
    @patch(
        "cl.search.management.commands.generate_cap_crosswalk.Command.fetch_cases_metadata"
    )
    @patch(
        "cl.search.management.commands.generate_cap_crosswalk.Command.find_matching_case"
    )
    def test_generate_cap_crosswalk_with_short_date_format(
        self,
        mock_find_matching_case,
        mock_fetch_cases_metadata,
        mock_fetch_volumes,
        mock_fetch_reporters,
    ):
        mock_fetch_reporters.return_value = [
            {"slug": "U.S.", "short_name": "U.S."}
        ]

        mock_fetch_volumes.return_value = ["1"]

        test_cases = [
            {
                "id": 1,
                "name_abbreviation": "Old Case",
                "decision_date": "2023-01-01",
                "citations": [{"cite": "1 U.S. 1"}],
                "file_name": "old_case",
                "last_updated": "2024-03-18T00:00:00+00:00",
            },
            {
                "id": 2,
                "name_abbreviation": "New Case",
                "decision_date": "2023-01-02",
                "citations": [{"cite": "1 U.S. 2"}],
                "file_name": "new_case",
                "last_updated": "2024-03-20T00:00:00+00:00",
            },
        ]

        def mock_fetch_cases(reporter_slug, volume):
            # Note: Command will convert YYYY-MM-DD to midnight UTC
            cutoff_date = datetime(2024, 3, 19, tzinfo=pytz.UTC)
            return [
                case
                for case in test_cases
                if datetime.fromisoformat(case["last_updated"]) > cutoff_date
            ]

        mock_fetch_cases_metadata.side_effect = mock_fetch_cases

        mock_opinion_cluster = MagicMock()
        mock_opinion_cluster.id = 100
        mock_find_matching_case.return_value = mock_opinion_cluster

        # Call the command with short date format
        output_dir = "/opt/courtlistener/cl/search/crosswalks"
        call_command(
            "generate_cap_crosswalk",
            output_dir=output_dir,
            updated_after="2024-03-19",  # Using YYYY-MM-DD format
        )

        # Check if crosswalk file was created
        expected_file_path = f"{output_dir}/U_S_.json"
        self.assertTrue(os.path.exists(expected_file_path))

        with open(expected_file_path, "r") as f:
            crosswalk_data = json.load(f)
            self.assertEqual(len(crosswalk_data), 1)

            # Verify it's the newer case
            self.assertEqual(crosswalk_data[0]["cap_case_id"], 2)
            self.assertEqual(
                crosswalk_data[0]["cap_path"], "/U.S./1/cases/new_case.json"
            )

            # Verify the old case is not present
            old_case_entries = [
                entry
                for entry in crosswalk_data
                if entry["cap_case_id"] == 1
                or entry["cap_path"] == "/U.S./1/cases/old_case.json"
            ]
            self.assertEqual(
                len(old_case_entries),
                0,
                "Found old case in crosswalk when it should have been filtered out",
            )

        os.remove(expected_file_path)

        mock_fetch_reporters.assert_called_once()
        mock_fetch_volumes.assert_called_once_with("U.S.")
        mock_fetch_cases_metadata.assert_called_once_with("U.S.", "1")
        self.assertEqual(mock_find_matching_case.call_count, 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
