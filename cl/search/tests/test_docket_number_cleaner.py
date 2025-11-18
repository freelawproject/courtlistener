from dataclasses import dataclass
from unittest import mock

from django.utils import timezone
from pydantic import ValidationError

from cl.lib.redis_utils import get_redis_interface
from cl.search.docket_number_cleaner import (
    call_models_and_compare_results,
    clean_docket_number_raw,
    create_llm_court_batches,
    extract_with_llm,
    is_generic,
    prelim_clean_F,
    process_llm_batches,
    regex_clean_F,
    update_docket_number,
)
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.llm_models import CleanDocketNumber, DocketItem
from cl.search.models import Docket
from cl.search.tasks import clean_docket_number_by_court
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
                expected=("12-1234-AG", None),  # cleaned, no LLM needed
            ),
            CleanDocketNumberTestCase(
                docket_id="d2",
                docket_number_raw="Docket Nos. 12-1234-ag and 13-5678-pr",
                court="ca1",
                expected=(None, "d2"),  # no cleaning done, LLM needed
            ),
            CleanDocketNumberTestCase(
                docket_id="d3",
                docket_number_raw="Docket No. 12-1234-ag",
                court="unknowncourt",
                expected=None,  # unsupported court
            ),
            CleanDocketNumberTestCase(
                docket_id="d4",
                docket_number_raw="",
                court="scotus",
                expected=None,  # empty docket_number_raw
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


@mock.patch(
    "cl.search.docket_number_cleaner.get_redis_key_prefix",
    return_value="docket_number_cleaning_test1",
)
class TestLLMCleanDocketNumberRaw(TestCase):
    def setUp(self):
        self.court_canb = CourtFactory(id="canb", jurisdiction="FB")
        self.court_scotus = CourtFactory(id="scotus", jurisdiction="F")
        self.docket_number = "Old-1234"
        self.new_docket_number = "New-5678"

        self.r = get_redis_interface("CACHE")
        self.key_to_clean = "docket_number_cleaning_test1:llm_batch"
        if self.key_to_clean:
            self.r.delete(self.key_to_clean)

        super().setUp()

    def test_update_docket_number_updated(self, mock_get_redis_key_prefix):
        """Tests that the docket number is updated if the docket was not modified after the start timestamp."""
        docket = DocketFactory(docket_number=self.docket_number)
        self.r.sadd(self.key_to_clean, docket.id)
        start_timestamp = timezone.now()
        with self.captureOnCommitCallbacks(execute=True):
            update_docket_number(
                docket.id, self.new_docket_number, start_timestamp, self.r
            )
        docket.refresh_from_db()
        self.assertEqual(
            docket.docket_number,
            self.new_docket_number,
            "Docket number not updated",
        )
        self.assertEqual(
            self.r.scard(self.key_to_clean),
            0,
            "Redis cache count doesn't match",
        )
        self.assertEqual(
            self.r.smembers(self.key_to_clean),
            set(),
            "Redis cache set doesn't match",
        )

    def test_update_docket_number_not_updated_due_to_timestamp(
        self, mock_get_redis_key_prefix
    ):
        """Tests that if the docket was modified after the start timestamp, it is not updated."""
        docket = DocketFactory(docket_number=self.docket_number)
        self.r.sadd(self.key_to_clean, docket.id)
        start_timestamp = timezone.now()
        # Simulate an update to the docket after the start timestamp
        docket.docket_number = "Intermediate-0000"
        docket.save(update_fields=["docket_number", "date_modified"])
        update_docket_number(
            docket.id, self.new_docket_number, start_timestamp, self.r
        )
        docket.refresh_from_db()
        self.assertEqual(
            docket.docket_number,
            "Intermediate-0000",
            "Docket number should not have changed",
        )
        self.assertEqual(
            self.r.scard(self.key_to_clean),
            1,
            "Redis cache count doesn't match",
        )
        self.assertEqual(
            self.r.smembers(self.key_to_clean),
            {str(docket.id)},
            "Redis cache set doesn't match",
        )

    def test_update_docket_number_docket_deleted(
        self, mock_get_redis_key_prefix
    ):
        """Tests that if the docket is deleted, the Redis set remains unchanged."""
        docket = DocketFactory(docket_number=self.docket_number)
        docket_id = docket.id
        self.r.sadd(self.key_to_clean, docket.id)
        start_timestamp = timezone.now()
        # Simulate deleting the docket before calling update_docket_number
        docket.delete()
        update_docket_number(
            docket_id, self.new_docket_number, start_timestamp, self.r
        )
        self.assertEqual(
            self.r.scard(self.key_to_clean),
            0,
            "Redis cache count doesn't match",
        )

    def test_create_llm_court_batches(self, mock_get_redis_key_prefix):
        """Tests the creation of LLM court batches from a set of docket IDs."""
        docket1 = DocketFactory(
            court=self.court_canb, docket_number_raw="12-1234-ag"
        )
        docket2 = DocketFactory(
            court=self.court_canb, docket_number_raw="Docket 12-1234-ag"
        )
        docket3 = DocketFactory(
            court=self.court_scotus, docket_number_raw="34-5678-pr"
        )
        docket4 = DocketFactory(
            court=self.court_scotus, docket_number_raw="Docket No. 34-5678-pr"
        )
        docket5 = DocketFactory(
            court=self.court_scotus, docket_number_raw="12-3456"
        )
        llm_batch = {
            docket1.id,
            docket2.id,
            docket3.id,
            docket4.id,
            docket5.id,
        }
        self.r.sadd(
            self.key_to_clean, *map(str, [docket3.id, docket4.id, docket5.id])
        )

        # Simulate deleting docket5 to test proper removal from redis set
        docket5.delete()

        batches = create_llm_court_batches(llm_batch, self.r)
        expected_batches = {
            "F": [
                {docket3.id: docket3.docket_number_raw},
                {docket4.id: docket4.docket_number_raw},
            ],
        }
        # Compare batches and expected_batches by checking keys and comparing lists as sets of dicts
        self.assertEqual(set(batches.keys()), set(expected_batches.keys()))
        for key in expected_batches:
            self.assertEqual(
                {frozenset(d.items()) for d in batches[key]},
                {frozenset(d.items()) for d in expected_batches[key]},
                f"Mismatch in batch for key {key}",
            )

        self.assertEqual(
            self.r.scard(self.key_to_clean),
            2,
            "Redis cache count doesn't match",
        )


@mock.patch.dict(
    "os.environ", {"DOCKET_NUMBER_CLEANING_API_KEY": "123"}, clear=True
)
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
                DocketItem(
                    unique_id=str(cls.docket_1.id),
                    cleaned_nums=["12-1234-AG", "13-5678-PR", "14-9010"],
                ),
                DocketItem(
                    unique_id=str(cls.docket_2.id),
                    cleaned_nums=["512", "513", "514"],
                ),
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

    @mock.patch("cl.search.docket_number_cleaner.call_llm")
    @mock.patch("cl.search.docket_number_cleaner.capture_exception")
    def test_extract_with_llm_handles_general_exception(
        self, mock_capture_exception, mock_call_llm
    ):
        """Test that extract_with_llm catches general Exception from call_llm, calls capture_exception, and returns None."""
        mock_call_llm.side_effect = Exception("Some LLM error")

        result = extract_with_llm(
            self.batch, self.system_prompt, self.model_id
        )

        self.assertIsNone(result)
        mock_capture_exception.assert_called()


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

        cls.expected_none = {
            cls.docket_1.id: cls.docket_1.docket_number_raw,
            cls.docket_2.id: cls.docket_2.docket_number_raw,
            cls.docket_3.id: cls.docket_3.docket_number_raw,
            cls.docket_4.id: cls.docket_4.docket_number_raw,
        }
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
    def test_process_llm_batches_handles_none(self, mock_extract_with_llm):
        """Test process_llm_batches when batches return None."""
        # Simulate extract_with_llm returning results for each batch
        mock_extract_with_llm.return_value = None
        result = process_llm_batches(
            self.llm_batches,
            self.system_prompt,
            self.model_id,
            self.retry,
            self.max_retries,
            self.batch_size,
            dict(),
        )
        self.assertEqual(result, self.expected_none)

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


@mock.patch(
    "cl.search.docket_number_cleaner.get_redis_key_prefix",
    return_value="docket_number_cleaning_test2",
)
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

        cls.expected_agree = []
        cls.expected_disagree = [
            {cls.docket_4.id: cls.docket_4.docket_number_raw}
        ]

    def setUp(self):
        self.r = get_redis_interface("CACHE")
        self.key_to_clean = "docket_number_cleaning_test2:llm_batch"
        if self.key_to_clean:
            self.r.delete(self.key_to_clean)

    @mock.patch("cl.search.docket_number_cleaner.process_llm_batches")
    def test_call_models_and_compare_results_agree(
        self, mock_process_llm_batches, mock_get_redis_key_prefix
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
            self.r,
        )
        self.assertEqual(result, self.expected_agree)

    @mock.patch("cl.search.docket_number_cleaner.process_llm_batches")
    def test_call_models_and_compare_results_disagree(
        self, mock_process_llm_batches, mock_get_redis_key_prefix
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
            self.r,
        )
        self.assertEqual(result, self.expected_disagree)


@mock.patch(
    "cl.search.docket_number_cleaner.get_redis_key_prefix",
    return_value="docket_number_cleaning_test3",
)
class TestLLMCleanDocketNumberByCourt(TestCase):
    def setUp(self):
        self.court_scotus = CourtFactory(id="scotus", jurisdiction="F")
        self.docket_1 = DocketFactory(
            court=self.court_scotus,
            docket_number_raw="Docket numbers 12-1234-ag, 13-5678-pr, 14-9010",
            source=Docket.DEFAULT,
        )
        self.docket_2 = DocketFactory(
            court=self.court_scotus,
            docket_number_raw="Cases 512 to 514",
            source=Docket.DEFAULT,
        )
        self.docket_3 = DocketFactory(
            court=self.court_scotus,
            docket_number_raw="Cases 12-1234 to 12-1236",
            source=Docket.DEFAULT,
        )
        self.court_batch = [
            {self.docket_1.id: self.docket_1.docket_number_raw},
            {self.docket_2.id: self.docket_2.docket_number_raw},
            {self.docket_3.id: self.docket_3.docket_number_raw},
        ]
        self.court_mapping = self.court_scotus.jurisdiction

        self.expected = {
            self.docket_1.id: "12-1234-AG; 13-5678-PR; 14-9010",
            self.docket_2.id: "512; 513; 514",
            self.docket_3.id: "12-1234; 12-1235; 12-1236",
        }

        self.r = get_redis_interface("CACHE")
        self.key_to_clean = "docket_number_cleaning_test3:llm_batch"
        if self.key_to_clean:
            self.r.delete(self.key_to_clean)
            self.r.sadd(self.key_to_clean, self.docket_1.id)
            self.r.sadd(self.key_to_clean, self.docket_2.id)
            self.r.sadd(self.key_to_clean, self.docket_3.id)

        super().setUp()

    @mock.patch("cl.search.docket_number_cleaner.process_llm_batches")
    def test_llm_clean_docket_numbers_mini_agrees(
        self, mock_process_llm_batches, mock_get_redis_key_prefix
    ):
        """Test the clean_docket_number_by_court celery task where two mini models agree."""
        # Simulate that both mini models agree on all records for all courts
        mock_process_llm_batches.side_effect = [
            self.expected,  # First mini model results
            self.expected,  # Second mini model results
        ]
        with self.captureOnCommitCallbacks(execute=True):
            clean_docket_number_by_court(
                self.court_batch, self.court_mapping, timezone.now(), self.r
            )

        # Verify that docket numbers were updated correctly
        for docket in [self.docket_1, self.docket_2, self.docket_3]:
            docket.refresh_from_db()
            self.assertEqual(
                docket.docket_number,
                self.expected[docket.id],
                "docket number mismatch",
            )

        # Verify that Redis set is empty after processing
        self.assertEqual(
            self.r.scard(self.key_to_clean),
            0,
            "Redis cache count should be 0 after processing",
        )

    @mock.patch("cl.search.docket_number_cleaner.process_llm_batches")
    def test_llm_clean_docket_numbers_full_agrees(
        self, mock_process_llm_batches, mock_get_redis_key_prefix
    ):
        """Test the clean_docket_number_by_court celery task where two full models agree."""
        # Simulate that both full models agree on all records for all courts
        mock_process_llm_batches.side_effect = [
            {
                self.docket_1.id: self.expected[self.docket_1.id],
                self.docket_2.id: self.expected[self.docket_2.id],
                self.docket_3.id: self.docket_3.docket_number_raw,
            },  # First mini model results
            self.expected,  # Second mini model results
            {
                self.docket_3.id: self.expected[self.docket_3.id]
            },  # First full model results
            {
                self.docket_3.id: self.expected[self.docket_3.id]
            },  # Second full model results
        ]
        with self.captureOnCommitCallbacks(execute=True):
            clean_docket_number_by_court(
                self.court_batch, self.court_mapping, timezone.now(), self.r
            )

        # Verify that docket numbers were updated correctly
        for docket in [self.docket_1, self.docket_2, self.docket_3]:
            docket.refresh_from_db()
            self.assertEqual(
                docket.docket_number,
                self.expected[docket.id],
                "docket number mismatch",
            )

        # Verify that Redis set is empty after processing
        self.assertEqual(
            self.r.scard(self.key_to_clean),
            0,
            "Redis cache count should be 0 after processing",
        )

    @mock.patch("cl.search.tasks.process_llm_batches")
    @mock.patch("cl.search.docket_number_cleaner.process_llm_batches")
    def test_llm_clean_docket_numbers_tie_breaker(
        self,
        mock_process_llm_batches,
        mock_process_llm_batches_tasks,
        mock_get_redis_key_prefix,
    ):
        """Test the clean_docket_number_by_court celery task where the tie-breaker model is called."""
        # Simulate that both full models agree on all records for all courts
        mock_process_llm_batches.side_effect = [
            {
                self.docket_1.id: self.expected[self.docket_1.id],
                self.docket_2.id: self.expected[self.docket_2.id],
                self.docket_3.id: self.docket_3.docket_number_raw,
            },  # First mini model results
            self.expected,  # Second mini model results
            {
                self.docket_3.id: self.docket_3.docket_number_raw
            },  # First full model results
            {
                self.docket_3.id: self.expected[self.docket_3.id]
            },  # Second full model results
        ]
        mock_process_llm_batches_tasks.return_value = {
            self.docket_3.id: self.expected[self.docket_3.id]
        }  # Tie breaker model results
        with self.captureOnCommitCallbacks(execute=True):
            clean_docket_number_by_court(
                self.court_batch, self.court_mapping, timezone.now(), self.r
            )

        # Verify that docket numbers were updated correctly
        for docket in [self.docket_1, self.docket_2, self.docket_3]:
            docket.refresh_from_db()
            self.assertEqual(
                docket.docket_number,
                self.expected[docket.id],
                "docket number mismatch",
            )

        # Verify that Redis set is empty after processing
        self.assertEqual(
            self.r.scard(self.key_to_clean),
            0,
            "Redis cache count should be 0 after processing",
        )
