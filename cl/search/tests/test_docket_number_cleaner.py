from dataclasses import dataclass
from unittest import mock

from django.utils import timezone
from pydantic import ValidationError

from cl.search.docket_number_cleaner import (
    call_models_and_compare_results,
    clean_docket_number_raw,
    create_llm_court_batches,
    extract_with_llm,
    get_docket,
    is_generic,
    llm_clean_docket_numbers,
    prelim_clean_F,
    process_llm_batches,
    regex_clean_F,
    update_docket_number,
)
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.llm_models import CleanDocketNumber
from cl.search.models import Docket
from cl.tests.cases import TestCase


@dataclass
class CleanDocketNumberTestCase:
    docket_id: str
    docket_number_raw: str
    court: str
    expected: tuple


class TestCleanDocketNumberRaw(TestCase):
    def test_is_generic(self):
        test_cases = [
            ("12-1234-ag", "F", True),
            ("12-1234P", "F", True),
            ("12A1234", "F", True),
            ("A-1234", "F", True),
            ("12-1234", "F", True),
            ("1234", "F", True),
            ("notadocket", "F", False),
            ("12-1234, 1234", "F", False),
            ("12-1234", "not_a_court", False),
        ]
        for input_str, court_map, expected in test_cases:
            assert is_generic(input_str, court_map) == expected, (
                f"Failed for input_str: {input_str}"
            )

    def test_prelim_clean_F(self):
        test_cases = [
            ("No. 12-1234-ag", "12-1234-ag"),
            ("Case No. 12 ‒ 1234", "12-1234"),
            ("Docket NO. 12-1234P", "12-1234P"),
            ("Case 12a1234", "12a1234"),
            (" 12——1234 ", "12-1234"),
            ("12-1234.", "12-1234"),
            ("12‐1234_1", "12-1234"),
            ("-12―1234-", "12-1234"),
            ("No.   12 -- 1234   ", "12-1234"),
            ("1234_1", "1234"),
        ]
        for input_str, expected in test_cases:
            assert prelim_clean_F(input_str) == expected, (
                f"Failed for input_str: {input_str}, {prelim_clean_F(input_str)}"
            )

    def test_regex_clean_F(self):
        test_cases = [
            ("12-1234-ag", "12-1234-AG"),
            ("12-1234P", "12-1234P"),
            ("12m1234", "12M1234"),
            ("a-1234", "A-1234"),
            ("12-1234", "12-1234"),
            ("1234", "1234"),
            ("No dockets here", ""),
        ]
        for input_str, expected in test_cases:
            assert regex_clean_F(input_str) == expected, (
                f"Failed for input_str: {input_str}"
            )

    def test_clean_docket_number_raw(self):
        test_cases: list[CleanDocketNumberTestCase] = [
            CleanDocketNumberTestCase(
                docket_id="d1",
                docket_number_raw="No. 12-1234-ag",
                court="ca1",
                expected=("12-1234-AG", None),
            ),
            CleanDocketNumberTestCase(
                docket_id="d2",
                docket_number_raw="Docket Nos. 12-1234-ag and 13-5678-pr",
                court="ca1",
                expected=("Docket Nos. 12-1234-ag and 13-5678-pr", "d2"),
            ),
            CleanDocketNumberTestCase(
                docket_id="d3",
                docket_number_raw="Docket No. 12-1234-ag",
                court="unknowncourt",
                expected=("Docket No. 12-1234-ag", None),
            ),
        ]

        for test_case in test_cases:
            with self.subTest(test_case=test_case):
                result = clean_docket_number_raw(
                    test_case.docket_id,
                    test_case.docket_number_raw,
                    test_case.court,
                )
                self.assertEqual(
                    result, test_case.expected, f"Failed for case: {test_case}"
                )


class TestLLMCleanDocketNumberRaw(TestCase):
    def test_get_docket_found(self):
        docket = DocketFactory()
        result = get_docket(docket.id)
        self.assertEqual(result, docket)

    def test_get_docket_not_found(self):
        result = get_docket(456)
        self.assertIsNone(result)

    def test_update_docket_number_updated(self):
        docket = DocketFactory(docket_number="Old-1234")
        start_timestamp = timezone.now()
        result = update_docket_number(docket.id, "New-5678", start_timestamp)
        self.assertEqual(result, docket.id)
        docket.refresh_from_db()
        self.assertEqual(docket.docket_number, "New-5678")

    def test_update_docket_number_not_updated_due_to_timestamp(self):
        docket = DocketFactory(docket_number="Old-1234")
        start_timestamp = timezone.now()
        # Simulate an update to the docket after the start timestamp
        docket.docket_number = "Intermediate-0000"
        docket.save()
        result = update_docket_number(docket.id, "New-5678", start_timestamp)
        self.assertIsNone(result)
        docket.refresh_from_db()
        self.assertEqual(docket.docket_number, "Intermediate-0000")

    def test_update_docket_number_docket_deleted(self):
        docket = DocketFactory(docket_number="Old-1234")
        start_timestamp = timezone.now()
        docket_id = docket.id
        # Delete the docket before calling update_docket_number
        docket.delete()
        result = update_docket_number(docket_id, "New-5678", start_timestamp)
        self.assertEqual(
            result, docket_id
        )  # Should return the docket_id to be removed from redis cache

    def test_create_llm_court_batches(self):
        court_canb = CourtFactory(id="canb", jurisdiction="FB")
        court_scotus = CourtFactory(id="scotus", jurisdiction="F")

        docket1 = DocketFactory(
            court=court_canb, docket_number_raw="12-1234-ag"
        )
        docket2 = DocketFactory(
            court=court_canb, docket_number_raw="Docket 12-1234-ag"
        )
        docket3 = DocketFactory(
            court=court_scotus, docket_number_raw="34-5678-pr"
        )
        docket4 = DocketFactory(
            court=court_scotus, docket_number_raw="Docket No. 34-5678-pr"
        )
        llm_batch = {docket1.id, docket2.id, docket3.id, docket4.id}
        batches = create_llm_court_batches(llm_batch)
        expected_batches = {
            None: [
                {docket1.id: docket1.docket_number_raw},
                {docket2.id: docket2.docket_number_raw},
            ],
            "F": [
                {docket3.id: docket3.docket_number_raw},
                {docket4.id: docket4.docket_number_raw},
            ],
        }
        self.assertEqual(batches, expected_batches)


class TestExtractWithLLM(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.court_scotus = CourtFactory(id="scotus", jurisdiction="F")
        cls.docket_1 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Docket numbers 12-1234-ag, 13-5678-pr, 14-9010",
            source=Docket.DEFAULT,
        )
        cls.docket_2 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Cases 512 to 514",
            source=Docket.DEFAULT,
        )
        cls.batch = [
            {cls.docket_1.id: cls.docket_1.docket_number_raw},
            {cls.docket_2.id: cls.docket_2.docket_number_raw},
        ]
        cls.system_prompt = "Extract and clean docket numbers."
        cls.model_id = "test-model"
        cls.llm_response = CleanDocketNumber(
            docket_numbers=[
                {
                    "unique_id": str(cls.docket_1.id),
                    "cleaned_nums": ["12-1234-AG", "13-5678-PR", "14-9010"],
                },
                {
                    "unique_id": str(cls.docket_2.id),
                    "cleaned_nums": ["512", "513", "514"],
                },
            ]
        )
        cls.expected = {
            cls.docket_1.id: "12-1234-AG; 13-5678-PR; 14-9010",
            cls.docket_2.id: "512; 513; 514",
        }

    @mock.patch("cl.search.docket_number_cleaner.call_llm")
    def test_extract_with_llm(self, mock_call_llm):
        """Verifies that the extract_with_llm function extracts and cleans the docket numbers correctly."""
        mock_call_llm.return_value = self.llm_response

        result = extract_with_llm(
            self.batch, self.system_prompt, self.model_id
        )
        self.assertEqual(result, self.expected)

    @mock.patch("cl.search.docket_number_cleaner.call_llm")
    @mock.patch("cl.search.docket_number_cleaner.logger")
    def test_extract_with_llm_handles_validation_error(
        self, mock_logger, mock_call_llm
    ):
        """Test that extract_with_llm catches Pydantic ValidationError from call_llm and handles it correctly
        by logging and returning without an exception
        """

        mock_call_llm.side_effect = ValidationError.from_exception_data(
            "Invalid data", line_errors=[]
        )

        result = extract_with_llm(
            self.batch, self.system_prompt, self.model_id
        )

        self.assertIsNone(result)

        # Logger.error should have been called at least once with validation error message
        mock_logger.error.assert_called()
        called_messages = [
            args[0] for args, _ in mock_logger.error.call_args_list
        ]
        self.assertTrue(
            any(
                "validation error" in message.lower()
                for message in called_messages
            )
        )


class TestProcessLLMBatches(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.court_scotus = CourtFactory(id="scotus", jurisdiction="F")
        cls.docket_1 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Docket numbers 12-1234-ag, 13-5678-pr, 14-9010",
            source=Docket.DEFAULT,
        )
        cls.docket_2 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Cases 512 to 514",
            source=Docket.DEFAULT,
        )
        cls.docket_3 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Cases 12-1234 to 12-1236",
            source=Docket.DEFAULT,
        )
        cls.docket_4 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Docket Nos. 567-569",
            source=Docket.DEFAULT,
        )
        cls.llm_batches = [
            {cls.docket_1.id: cls.docket_1.docket_number_raw},
            {cls.docket_2.id: cls.docket_2.docket_number_raw},
            {cls.docket_3.id: cls.docket_3.docket_number_raw},
            {cls.docket_4.id: cls.docket_4.docket_number_raw},
        ]
        cls.system_prompt = "Extract and clean docket numbers."
        cls.model_id = "test-model"
        cls.retry = 0
        cls.max_retries = 2
        cls.batch_size = 2
        cls.all_cleaned = []
        cls.extract_response_1 = {
            cls.docket_1.id: "12-1234-AG; 13-5678-PR; 14-9010",
            cls.docket_2.id: "512; 513; 514",
            cls.docket_3.id: "12-1234; 12-1235; 12-1236",
            cls.docket_4.id: "567; 568; 569",
        }
        cls.extract_response_2 = {
            cls.docket_1.id: "12-1234-AG; 13-5678-PR; 14-9010",
            cls.docket_2.id: "512; 513; 514",
        }
        cls.extract_response_3 = {cls.docket_3.id: "12-1234; 12-1235; 12-1236"}
        cls.extract_response_4 = {cls.docket_4.id: "567; 568; 569"}

        cls.expected_all = {
            cls.docket_1.id: "12-1234-AG; 13-5678-PR; 14-9010",
            cls.docket_2.id: "512; 513; 514",
            cls.docket_3.id: "12-1234; 12-1235; 12-1236",
            cls.docket_4.id: "567; 568; 569",
        }
        cls.expected_after_max_retry = {
            cls.docket_1.id: "12-1234-AG; 13-5678-PR; 14-9010",
            cls.docket_2.id: "512; 513; 514",
            cls.docket_3.id: "12-1234; 12-1235; 12-1236",
            cls.docket_4.id: cls.docket_4.docket_number_raw,  # Raw value assigned after max retries
        }

    @mock.patch("cl.search.docket_number_cleaner.extract_with_llm")
    def test_process_llm_batches_no_recursion(self, mock_extract_with_llm):
        """Test process_llm_batches when all batches succeed (no recursion)."""
        # Simulate extract_with_llm returning results for each batch
        mock_extract_with_llm.return_value = self.extract_response_1
        result = process_llm_batches(
            self.llm_batches,
            self.system_prompt,
            self.model_id,
            self.retry,
            self.max_retries,
            self.batch_size,
            dict(),
        )
        self.assertEqual(result, self.expected_all)

    @mock.patch("cl.search.docket_number_cleaner.extract_with_llm")
    def test_process_llm_batches_with_recursion(self, mock_extract_with_llm):
        """Test process_llm_batches when recursion is needed."""

        # Simulate that extract_with_llm returns partial results on first try and full results on retry
        def side_effect(batch, system_prompt, model_id):
            if batch == self.llm_batches[0:2]:
                return (
                    self.extract_response_2
                )  # Simulate results for first batch
            elif batch == self.llm_batches[2:4]:
                return (
                    self.extract_response_3
                )  # Simulate partial results for second batch
            elif batch == [self.llm_batches[3]]:
                return (
                    self.extract_response_4
                )  # Simulate results for retry on failed record
            return dict()

        mock_extract_with_llm.side_effect = side_effect

        # Start with retry=0
        result = process_llm_batches(
            self.llm_batches,
            self.system_prompt,
            self.model_id,
            0,
            self.max_retries,
            self.batch_size,
            dict(),
        )
        self.assertEqual(result, self.expected_all)

    @mock.patch("cl.search.docket_number_cleaner.extract_with_llm")
    def test_process_llm_batches_with_recursion_after_max_retry(
        self, mock_extract_with_llm
    ):
        """Test process_llm_batches when recursion is needed and raw values are assigned after max retries."""

        # Simulate that extract_with_llm returns partial results on first try and no results on retry
        def side_effect(batch, system_prompt, model_id):
            if batch == self.llm_batches[0:2]:
                return (
                    self.extract_response_2
                )  # Simulate results for first batch
            elif batch == self.llm_batches[2:4]:
                return (
                    self.extract_response_3
                )  # Simulate partial results for second batch
            elif batch == [self.llm_batches[3]]:
                return dict()  # Simulate no results for retry on failed record
            return dict()

        mock_extract_with_llm.side_effect = side_effect

        # Start with retry=1 (next retry will be max_retries=2)
        result = process_llm_batches(
            self.llm_batches,
            self.system_prompt,
            self.model_id,
            1,
            self.max_retries,
            self.batch_size,
            dict(),
        )
        self.assertEqual(result, self.expected_after_max_retry)


class TestCallModelsCompareResults(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.court_scotus = CourtFactory(id="scotus", jurisdiction="F")
        cls.docket_1 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Docket numbers 12-1234-ag, 13-5678-pr, 14-9010",
            source=Docket.DEFAULT,
        )
        cls.docket_2 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Cases 512 to 514",
            source=Docket.DEFAULT,
        )
        cls.docket_3 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Cases 12-1234 to 12-1236",
            source=Docket.DEFAULT,
        )
        cls.docket_4 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Docket Nos. 567-569",
            source=Docket.DEFAULT,
        )
        cls.court_batch = [
            {cls.docket_1.id: cls.docket_1.docket_number_raw},
            {cls.docket_2.id: cls.docket_2.docket_number_raw},
            {cls.docket_3.id: cls.docket_3.docket_number_raw},
            {cls.docket_4.id: cls.docket_4.docket_number_raw},
        ]
        cls.court_mapping = cls.court_scotus.jurisdiction
        cls.model_one = "model-one"
        cls.model_two = "model-two"
        cls.start_timestamp = timezone.now()

        cls.model_response_agrees = {
            cls.docket_1.id: "12-1234-AG; 13-5678-PR; 14-9010",
            cls.docket_2.id: "512; 513; 514",
            cls.docket_3.id: "12-1234; 12-1235; 12-1236",
            cls.docket_4.id: "567; 568; 569",
        }
        cls.model_one_response = {
            cls.docket_1.id: "12-1234-AG; 13-5678-PR; 14-9010",
            cls.docket_2.id: "512; 513; 514",
            cls.docket_3.id: "12-1234; 12-1235; 12-1236",
            cls.docket_4.id: "567; 568; 569",
        }
        cls.model_two_response = {
            cls.docket_1.id: "12-1234-AG; 13-5678-PR; 14-9010",
            cls.docket_2.id: "512; 513; 514",
            cls.docket_3.id: "12-1234; 12-1235; 12-1236",
            cls.docket_4.id: "567 - 569",
        }

        cls.expected_agree = (
            [],
            [
                cls.docket_1.id,
                cls.docket_2.id,
                cls.docket_3.id,
                cls.docket_4.id,
            ],
        )
        cls.expected_disagree = (
            [{cls.docket_4.id: cls.docket_4.docket_number_raw}],
            [cls.docket_1.id, cls.docket_2.id, cls.docket_3.id],
        )

    @mock.patch("cl.search.docket_number_cleaner.process_llm_batches")
    def test_call_models_and_compare_results_agree(
        self, mock_process_llm_batches
    ):
        """Test call_models_and_compare_results when both models agree on all records."""
        mock_process_llm_batches.side_effect = [
            self.model_response_agrees,
            self.model_response_agrees,
        ]

        result = call_models_and_compare_results(
            self.court_batch,
            self.court_mapping,
            self.model_one,
            self.model_two,
            self.start_timestamp,
        )
        self.assertEqual(result, self.expected_agree)

    @mock.patch("cl.search.docket_number_cleaner.process_llm_batches")
    def test_call_models_and_compare_results_disagree(
        self, mock_process_llm_batches
    ):
        """Test call_models_and_compare_results when models disagree on some records."""
        mock_process_llm_batches.side_effect = [
            self.model_one_response,
            self.model_two_response,
        ]

        result = call_models_and_compare_results(
            self.court_batch,
            self.court_mapping,
            self.model_one,
            self.model_two,
            self.start_timestamp,
        )
        self.assertEqual(result, self.expected_disagree)


class TestLLMCleanDocketNumbers(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.court_scotus = CourtFactory(id="scotus", jurisdiction="F")
        cls.court_canb = CourtFactory(id="canb", jurisdiction="FB")
        cls.docket_1 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Docket numbers 12-1234-ag, 13-5678-pr, 14-9010",
            source=Docket.DEFAULT,
        )
        cls.docket_2 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Cases 512 to 514",
            source=Docket.DEFAULT,
        )
        cls.docket_3 = DocketFactory(
            court=cls.court_scotus,
            docket_number_raw="Cases 12-1234 to 12-1236",
            source=Docket.DEFAULT,
        )
        cls.docket_4 = DocketFactory(
            court=cls.court_canb,
            docket_number_raw="Docket Nos. 567-569",
            source=Docket.DEFAULT,
        )
        cls.llm_batch = [
            cls.docket_1.id,
            cls.docket_2.id,
            cls.docket_3.id,
            cls.docket_4.id,
        ]

        cls.court_batches = {
            cls.court_scotus.jurisdiction: [
                {cls.docket_1.id: cls.docket_1.docket_number_raw},
                {cls.docket_2.id: cls.docket_2.docket_number_raw},
                {cls.docket_3.id: cls.docket_3.docket_number_raw},
            ],
            cls.court_canb.jurisdiction: [
                {cls.docket_4.id: cls.docket_4.docket_number_raw},
            ],
        }

        cls.mini_response_agrees = [
            (
                [],
                [cls.docket_1.id, cls.docket_2.id, cls.docket_3.id],
            ),  # All agree for scotus
            ([], [cls.docket_4.id]),  # All agree for canb
        ]
        cls.mini_response_disagrees_full_response_agrees = [
            (
                [{cls.docket_3.id: cls.docket_3.docket_number_raw}],
                [cls.docket_1.id, cls.docket_2.id],
            ),  # Disagree for scotus with mini
            ([], [cls.docket_3.id]),  # All agree for scotus with full
            ([], [cls.docket_4.id]),  # All agree for canb with mini
        ]
        cls.mini_response_disagrees_full_response_disagrees = [
            (
                [{cls.docket_3.id: cls.docket_3.docket_number_raw}],
                [cls.docket_1.id, cls.docket_2.id],
            ),  # Disagree for scotus with mini
            (
                [{cls.docket_3.id: cls.docket_3.docket_number_raw}],
                [],
            ),  # Disagree for scotus with full
            ([], [cls.docket_4.id]),  # All agree for canb with mini
        ]
        cls.tie_breaker_response = {
            cls.docket_3.id: "12-1234; 12-1235; 12-1236"
        }

        cls.expected_agree = [
            cls.docket_1.id,
            cls.docket_2.id,
            cls.docket_3.id,
            cls.docket_4.id,
        ]

    @mock.patch("cl.search.docket_number_cleaner.create_llm_court_batches")
    @mock.patch(
        "cl.search.docket_number_cleaner.call_models_and_compare_results"
    )
    @mock.patch("cl.search.docket_number_cleaner.process_llm_batches")
    def test_llm_clean_docket_numbers_mini_agrees(
        self,
        mock_process_llm_batches,
        mock_call_models_and_compare_results,
        mock_create_llm_court_batches,
    ):
        """Test the end-to-end LLM cleaning process for docket numbers."""
        mock_create_llm_court_batches.return_value = self.court_batches

        # Simulate that both mini models agree on all records for all courts
        mock_call_models_and_compare_results.side_effect = (
            self.mini_response_agrees
        )

        result = llm_clean_docket_numbers(self.llm_batch)
        self.assertEqual(result, self.expected_agree)

    @mock.patch("cl.search.docket_number_cleaner.create_llm_court_batches")
    @mock.patch(
        "cl.search.docket_number_cleaner.call_models_and_compare_results"
    )
    @mock.patch("cl.search.docket_number_cleaner.process_llm_batches")
    def test_llm_clean_docket_numbers_full_agrees(
        self,
        mock_process_llm_batches,
        mock_call_models_and_compare_results,
        mock_create_llm_court_batches,
    ):
        """Test the end-to-end LLM cleaning process for docket numbers."""
        mock_create_llm_court_batches.return_value = self.court_batches

        # Simulate that mini models agree but full models agree
        mock_call_models_and_compare_results.side_effect = (
            self.mini_response_disagrees_full_response_agrees
        )

        result = llm_clean_docket_numbers(self.llm_batch)
        self.assertEqual(sorted(result), self.expected_agree)

    @mock.patch("cl.search.docket_number_cleaner.create_llm_court_batches")
    @mock.patch(
        "cl.search.docket_number_cleaner.call_models_and_compare_results"
    )
    @mock.patch("cl.search.docket_number_cleaner.process_llm_batches")
    def test_llm_clean_docket_numbers_tie_breaker(
        self,
        mock_process_llm_batches,
        mock_call_models_and_compare_results,
        mock_create_llm_court_batches,
    ):
        """Test the end-to-end LLM cleaning process for docket numbers."""
        mock_create_llm_court_batches.return_value = self.court_batches

        # Simulate that mini and full models disagree and tie breaker resolves
        mock_call_models_and_compare_results.side_effect = (
            self.mini_response_disagrees_full_response_disagrees
        )
        mock_process_llm_batches.return_value = self.tie_breaker_response

        result = llm_clean_docket_numbers(self.llm_batch)
        self.assertEqual(sorted(result), self.expected_agree)
