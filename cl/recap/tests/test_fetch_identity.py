from unittest.mock import Mock

from juriscraper.lib.exceptions import ParsingException

from cl.recap.mergers import merge_pacer_docket_into_cl_docket
from cl.search.models import Docket
from cl.tests.cases import SimpleTestCase


class FetchDocketIdentityTest(SimpleTestCase):
    """Reject unrelated fetched data before any docket mutation."""

    def test_mismatches_do_not_mutate_destination(self) -> None:
        """Check court, retrieval ID, report ID, and missing-ID fallbacks."""
        for changes, requested_id, destination_id in (
            ({"court_id": "nysd"}, "123", "123"),
            ({}, "456", "123"),
            ({"pacer_case_id": "456"}, "123", "123"),
            ({"docket_number": "99-99999"}, "123", "123"),
            ({"docket_number": "99-99999"}, "123", None),
            ({"docket_number": ""}, "123", None),
            ({"court_id": ""}, "123", "123"),
        ):
            with self.subTest(changes=changes, destination_id=destination_id):
                docket = Mock(spec=Docket)
                docket.court_id = "cacd"
                docket.pacer_case_id = destination_id
                docket.docket_number_raw = "2:20-cv-00123"
                data = {
                    "court_id": "cacd",
                    "docket_number": "2:20-cv-00123",
                    **changes,
                }
                with self.assertRaises(ParsingException):
                    merge_pacer_docket_into_cl_docket(
                        docket, requested_id, data, Mock()
                    )
                docket.add_recap_source.assert_not_called()
                docket.save.assert_not_called()
                self.assertEqual(docket.pacer_case_id, destination_id)

    def test_matching_identity_reaches_merge(self) -> None:
        """Reports without case IDs still merge when court and number match."""
        for case_id, appellate in (
            ("123", False),
            (None, False),
            ("123", True),
        ):
            with self.subTest(case_id=case_id, appellate=appellate):
                docket = Mock(spec=Docket)
                docket.court_id = "cacd"
                docket.pacer_case_id = case_id
                docket.docket_number_raw = "2:20-cv-00123"
                docket.add_recap_source.side_effect = RuntimeError(
                    "merge reached"
                )
                with self.assertRaisesMessage(RuntimeError, "merge reached"):
                    merge_pacer_docket_into_cl_docket(
                        docket,
                        "2:20-cv-00123" if appellate else "123",
                        {"court_id": "cacd", "docket_number": "2:20-cv-00123"},
                        Mock(),
                        appellate=appellate,
                    )
