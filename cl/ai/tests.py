from unittest.mock import MagicMock, patch

import pytest

from cl.ai.llm_providers.google import (
    GoogleGenAIBatchWrapper,
    _ResponseValidator,
)
from cl.ai.models import (
    LLMProvider,
    LLMRequest,
    LLMTask,
    Prompt,
    PromptTypes,
    Task,
    TaskStatus,
)
from cl.search.factories import CourtFactory, DocketFactory
from cl.tests.cases import SimpleTestCase, TestCase


@pytest.mark.django_db
class AiModelsTest(TestCase):
    def setUp(self):
        self.court = CourtFactory()
        self.docket = DocketFactory(court=self.court)

    def test_create_llm_task(self):
        """Test that we can create an LLMTask and its related models."""
        prompt = Prompt.objects.create(
            name="Test System Prompt",
            prompt_type=PromptTypes.SYSTEM,
            text="You are a helpful assistant.",
        )
        self.assertEqual(Prompt.objects.count(), 1)

        llm_request = LLMRequest.objects.create(
            name="Test Batch Request",
            is_batch=True,
            provider=LLMProvider.GEMINI,
            api_model_name="gemini-2.5-pro",
            status=TaskStatus.UNPROCESSED,
        )
        llm_request.prompts.add(prompt)
        self.assertEqual(LLMRequest.objects.count(), 1)
        self.assertEqual(llm_request.prompts.count(), 1)

        llm_task = LLMTask.objects.create(
            request=llm_request,
            task=Task.CASENAME,
            content_object=self.docket,
            llm_key="test-key-1",
        )
        self.assertEqual(LLMTask.objects.count(), 1)
        self.assertEqual(llm_task.request, llm_request)
        self.assertEqual(llm_task.content_object, self.docket)
        self.assertEqual(llm_task.status, TaskStatus.UNPROCESSED)


class GoogleGenAIBatchWrapperTest(SimpleTestCase):
    """Tests for the GoogleGenAIBatchWrapper class."""

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_init_with_api_key(self, mock_client_class):
        """Test wrapper initialization with an API key."""
        wrapper = GoogleGenAIBatchWrapper(api_key="test-api-key-123")
        mock_client_class.assert_called_once_with(api_key="test-api-key-123")
        self.assertIsNotNone(wrapper.client)

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_init_without_api_key_raises_error(self, mock_client_class):
        """Test that initialization fails without an API key."""
        with self.assertRaises(ValueError) as context:
            GoogleGenAIBatchWrapper(api_key="")
        self.assertIn("API key is required", str(context.exception))

        # Also test with None
        with self.assertRaises(ValueError) as context:
            GoogleGenAIBatchWrapper(api_key=None)
        self.assertIn("API key is required", str(context.exception))

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_get_or_create_cache_finds_existing(self, mock_client_class):
        """Test finding an existing cache by display name."""
        # Create mock cache object
        mock_cache = MagicMock()
        mock_cache.display_name = "test-cache"
        mock_cache.name = (
            "cachedContents/zhe7p9mio4wc6fj8s8x5y6rcobsasgnl8rzw0kc3"
        )

        # Setup client mock
        mock_client_instance = MagicMock()
        mock_client_instance.caches.list.return_value = [mock_cache]
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")
        cache_name = wrapper.get_or_create_cache(
            system_prompt="Test prompt",
            model_name="gemini-3-pro-preview",
            cache_display_name="test-cache",
        )

        self.assertEqual(
            cache_name,
            "cachedContents/zhe7p9mio4wc6fj8s8x5y6rcobsasgnl8rzw0kc3",
        )
        mock_client_instance.caches.create.assert_not_called()

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_get_or_create_cache_creates_new(self, mock_client_class):
        """Test creating a new cache when none exists."""
        # Setup client mock with no existing caches
        mock_client_instance = MagicMock()
        mock_client_instance.caches.list.return_value = []

        # Setup cache creation response
        mock_created_cache = MagicMock()
        mock_created_cache.name = (
            "cachedContents/a2b5c8d1e3f6g9h0i4j7k2m5n8p1q4r7s0t3u6v9"
        )
        mock_client_instance.caches.create.return_value = mock_created_cache

        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")
        cache_name = wrapper.get_or_create_cache(
            system_prompt="New system prompt",
            model_name="gemini-3-pro-preview",
            cache_display_name="new-cache",
        )

        self.assertEqual(
            cache_name,
            "cachedContents/a2b5c8d1e3f6g9h0i4j7k2m5n8p1q4r7s0t3u6v9",
        )
        mock_client_instance.caches.create.assert_called_once()

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_prepare_batch_requests_with_file(self, mock_client_class):
        """Test preparing batch requests with file uploads."""
        # Setup mock uploaded file
        mock_uploaded_file = MagicMock()
        mock_uploaded_file.uri = "https://generativelanguage.googleapis.com/v1beta/files/test-file-123"

        # Setup client mock
        mock_client_instance = MagicMock()
        mock_client_instance.files.upload.return_value = mock_uploaded_file
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")
        tasks_data = [
            {
                "llm_key": "task-1",
                "input_file_path": "/fake/path/test.pdf",
            }
        ]

        result = wrapper.prepare_batch_requests(
            tasks_data=tasks_data, user_prompt="Extract text from this PDF"
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "task-1")
        self.assertIn("request", result[0])
        self.assertIn("contents", result[0]["request"])

        # Verify file was uploaded
        mock_client_instance.files.upload.assert_called_once()

        # Check the request structure
        contents = result[0]["request"]["contents"]
        self.assertEqual(len(contents), 1)
        self.assertEqual(contents[0]["role"], "user")

        parts = contents[0]["parts"]
        # Should have: file_data + user_prompt
        self.assertEqual(len(parts), 2)
        self.assertIn("file_data", parts[0])
        self.assertEqual(parts[1]["text"], "Extract text from this PDF")

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_prepare_batch_requests_with_text_only(self, mock_client_class):
        """Test preparing batch requests with text input only."""
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")
        tasks_data = [
            {
                "llm_key": "task-2",
                "input_text": "This is a sample document text.",
            }
        ]

        result = wrapper.prepare_batch_requests(
            tasks_data=tasks_data, user_prompt="Summarize this text"
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "task-2")

        # Check parts structure
        parts = result[0]["request"]["contents"][0]["parts"]
        # Should have: input_text + user_prompt
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]["text"], "This is a sample document text.")
        self.assertEqual(parts[1]["text"], "Summarize this text")

        # No file upload should occur
        mock_client_instance.files.upload.assert_not_called()

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_prepare_batch_requests_skips_missing_key(self, mock_client_class):
        """Test that requests without llm_key are skipped."""
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")
        tasks_data = [
            {"input_text": "No key provided"},
            {"llm_key": "task-3", "input_text": "Has key"},
        ]

        result = wrapper.prepare_batch_requests(
            tasks_data=tasks_data, user_prompt="Process this"
        )

        # Only one request should be created
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "task-3")

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_execute_batch_without_cache(self, mock_client_class):
        """Test executing a batch without system prompt caching."""
        # Setup mock batch job response
        mock_job = MagicMock()
        mock_job.name = "batches/d06qupto0eg36yg4fy49d3trshhus1it5xox"

        # Setup mock file upload
        mock_jsonl_file = MagicMock()
        mock_jsonl_file.name = "files/batch-requests.jsonl"

        # Setup client mock
        mock_client_instance = MagicMock()
        mock_client_instance.files.upload.return_value = mock_jsonl_file
        mock_client_instance.batches.create.return_value = mock_job
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")
        requests = [
            {
                "key": "req-1",
                "request": {
                    "contents": [
                        {"parts": [{"text": "Test request"}], "role": "user"}
                    ]
                },
            }
        ]

        batch_id = wrapper.execute_batch(
            model_name="gemini-3-pro-preview",
            requests=requests,
            system_prompt=None,
        )

        self.assertEqual(
            batch_id, "batches/d06qupto0eg36yg4fy49d3trshhus1it5xox"
        )
        mock_client_instance.files.upload.assert_called_once()
        mock_client_instance.batches.create.assert_called_once()

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_execute_batch_with_cache(self, mock_client_class):
        """Test executing a batch with system prompt caching."""
        # Setup mock cache
        mock_cache = MagicMock()
        mock_cache.display_name = "test-cache"
        mock_cache.name = (
            "cachedContents/x9y2z5a8b1c4d7e0f3g6h9i2j5k8m1n4p7q0r3s6"
        )

        # Setup mock batch job
        mock_job = MagicMock()
        mock_job.name = "batches/k8m2p5q9r3s6t0u4v7w1x5y8z2a6b9c3d7e1f4g8"

        # Setup mock file upload
        mock_jsonl_file = MagicMock()
        mock_jsonl_file.name = "files/batch-requests-with-cache.jsonl"

        # Setup client mock
        mock_client_instance = MagicMock()
        mock_client_instance.caches.list.return_value = [mock_cache]
        mock_client_instance.files.upload.return_value = mock_jsonl_file
        mock_client_instance.batches.create.return_value = mock_job
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")
        requests = [
            {
                "key": "req-2",
                "request": {
                    "contents": [
                        {"parts": [{"text": "Test request"}], "role": "user"}
                    ]
                },
            }
        ]

        batch_id = wrapper.execute_batch(
            model_name="gemini-3-pro-preview",
            requests=requests,
            system_prompt="You are a helpful assistant.",
            cache_display_name="test-cache",
        )

        self.assertEqual(
            batch_id, "batches/k8m2p5q9r3s6t0u4v7w1x5y8z2a6b9c3d7e1f4g8"
        )
        # Verify cache was applied to requests
        self.assertEqual(
            requests[0]["request"]["cached_content"],
            "cachedContents/x9y2z5a8b1c4d7e0f3g6h9i2j5k8m1n4p7q0r3s6",
        )

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_get_job(self, mock_client_class):
        """Test retrieving a batch job by ID."""
        # Setup mock job
        mock_job = MagicMock()
        mock_job.name = "batches/h3j6k9m2n5p8q1r4s7t0u3v6w9x2y5z8a1b4c7d0"
        mock_job.state.name = "JOB_STATE_RUNNING"

        # Setup client mock
        mock_client_instance = MagicMock()
        mock_client_instance.batches.get.return_value = mock_job
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")
        result = wrapper.get_job(
            "batches/h3j6k9m2n5p8q1r4s7t0u3v6w9x2y5z8a1b4c7d0"
        )

        self.assertEqual(
            result.name, "batches/h3j6k9m2n5p8q1r4s7t0u3v6w9x2y5z8a1b4c7d0"
        )
        self.assertEqual(result.state.name, "JOB_STATE_RUNNING")
        mock_client_instance.batches.get.assert_called_once_with(
            name="batches/h3j6k9m2n5p8q1r4s7t0u3v6w9x2y5z8a1b4c7d0"
        )

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_download_results_success(self, mock_client_class):
        """Test downloading results from a succeeded job."""
        # Setup mock job
        mock_job = MagicMock()
        mock_job.state = "JOB_STATE_SUCCEEDED"
        mock_job.dest.file_name = "files/results-123.jsonl"

        # Setup client mock
        mock_client_instance = MagicMock()
        mock_client_instance.files.download.return_value = (
            b'{"key": "task-1", "response": {}}'
        )
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")
        result = wrapper.download_results(mock_job)

        self.assertEqual(result, '{"key": "task-1", "response": {}}')
        mock_client_instance.files.download.assert_called_once_with(
            file="files/results-123.jsonl"
        )

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_download_results_not_succeeded_raises_error(
        self, mock_client_class
    ):
        """Test that downloading results fails for non-succeeded jobs."""
        # Setup mock job that's still running
        mock_job = MagicMock()
        mock_job.state = "JOB_STATE_RUNNING"

        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")

        with self.assertRaises(ValueError) as context:
            wrapper.download_results(mock_job)

        self.assertIn("has not succeeded", str(context.exception))
        mock_client_instance.files.download.assert_not_called()

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_process_results_success(self, mock_client_class):
        """Test processing successful batch results."""
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")

        # Mock JSONL content with Gemini API response format
        # Each line is a separate JSON object (JSONL format)
        jsonl_content = (
            '{"key": "task-1", "response": {"candidates": [{"content": {"parts": [{"text": "Extracted text from the document."}], "role": "model"}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20, "totalTokenCount": 120}}}\n'
            '{"key": "task-2", "response": {"candidates": [{"content": {"parts": [{"text": "Another successful extraction."}], "role": "model"}, "finishReason": "STOP"}]}}'
        )

        results = wrapper.process_results(jsonl_content)

        self.assertEqual(len(results), 2)

        # Check first result
        self.assertEqual(results[0]["key"], "task-1")
        self.assertEqual(results[0]["status"], "SUCCEEDED")
        self.assertEqual(
            results[0]["content"], "Extracted text from the document."
        )
        self.assertIsNone(results[0]["error_message"])

        # Check second result
        self.assertEqual(results[1]["key"], "task-2")
        self.assertEqual(results[1]["status"], "SUCCEEDED")
        self.assertEqual(
            results[1]["content"], "Another successful extraction."
        )
        self.assertIsNone(results[1]["error_message"])

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_process_results_with_errors(self, mock_client_class):
        """Test processing batch results containing errors."""
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")

        # Mock JSONL with error response
        jsonl_content = '{"key": "task-error", "error": {"code": 400, "message": "Invalid request parameters", "status": "INVALID_ARGUMENT"}}'

        results = wrapper.process_results(jsonl_content)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["key"], "task-error")
        self.assertEqual(results[0]["status"], "FAILED")
        self.assertIsNone(results[0]["content"])
        self.assertIn("Code 400", results[0]["error_message"])
        self.assertIn(
            "Invalid request parameters", results[0]["error_message"]
        )

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_process_results_with_malformed_response(self, mock_client_class):
        """Test processing results with malformed response structure."""
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")

        # Response missing expected structure
        jsonl_content = (
            '{"key": "task-malformed", "response": {"candidates": []}}'
        )

        results = wrapper.process_results(jsonl_content)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["key"], "task-malformed")
        self.assertEqual(results[0]["status"], "FAILED")
        self.assertIsNone(results[0]["content"])
        self.assertIn(
            "Invalid response structure", results[0]["error_message"]
        )

    @patch("cl.ai.llm_providers.google.genai.Client")
    def test_process_results_mixed_success_and_failure(
        self, mock_client_class
    ):
        """Test processing results with both successful and failed tasks."""
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")

        # Mock JSONL with mixed success and failure results
        jsonl_content = (
            '{"key": "task-success", "response": {"candidates": [{"content": {"parts": [{"text": "Success"}], "role": "model"}}]}}\n'
            '{"key": "task-fail", "error": {"code": 500, "message": "Internal server error"}}\n'
            '{"key": "task-empty", "response": {}}'
        )

        results = wrapper.process_results(jsonl_content)

        self.assertEqual(len(results), 3)

        # Verify mixed results
        success_results = [r for r in results if r["status"] == "SUCCEEDED"]
        failed_results = [r for r in results if r["status"] == "FAILED"]

        self.assertEqual(len(success_results), 1)
        self.assertEqual(len(failed_results), 2)
        self.assertEqual(success_results[0]["key"], "task-success")


class ResponseValidatorTest(SimpleTestCase):
    """Tests for the _ResponseValidator helper class."""

    def test_normalize_response_batch_format(self):
        """Test normalizing a batch API response (with wrapper)."""
        batch_response = {
            "key": "task-1",
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Test output"}],
                            "role": "model",
                        }
                    }
                ]
            },
        }

        normalized = _ResponseValidator.normalize_response(batch_response)

        self.assertIn("candidates", normalized)
        self.assertNotIn("key", normalized)
        self.assertEqual(
            normalized["candidates"][0]["content"]["parts"][0]["text"],
            "Test output",
        )

    def test_normalize_response_single_format(self):
        """Test normalizing a single API call response (no wrapper)."""
        single_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Direct output"}],
                        "role": "model",
                    }
                }
            ],
            "usageMetadata": {"promptTokenCount": 10},
        }

        normalized = _ResponseValidator.normalize_response(single_response)

        # Should return as-is (already normlized)
        self.assertEqual(normalized, single_response)
        self.assertIn("candidates", normalized)
        self.assertIn("usageMetadata", normalized)

    def test_get_text_from_batch_response(self):
        """Test extracting text from a batch response."""
        batch_response = {
            "key": "task-batch",
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Batch extracted text"}],
                            "role": "model",
                        }
                    }
                ]
            },
        }

        text = _ResponseValidator.get_text(batch_response)
        self.assertEqual(text, "Batch extracted text")

    def test_get_text_from_single_response(self):
        """Test extracting text from a single API call response."""
        single_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Single call extracted text"}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 5,
                "candidatesTokenCount": 8,
            },
        }

        text = _ResponseValidator.get_text(single_response)
        self.assertEqual(text, "Single call extracted text")

    def test_get_text_returns_none_for_invalid(self):
        """Test that get_text returns None for invalid structure."""
        invalid_responses = [
            {"candidates": []},  # No candidates
            {"candidates": [{"content": {}}]},  # Missing parts
            {"response": {"candidates": []}},  # Batch with empty candidates
            {},  # Empty dict
        ]

        for invalid in invalid_responses:
            with self.subTest(invalid=invalid):
                text = _ResponseValidator.get_text(invalid)
                self.assertIsNone(text)

    def test_get_error_from_batch_response(self):
        """Test extracting error from a batch response."""
        batch_error = {
            "key": "task-error",
            "error": {"code": 400, "message": "Bad request"},
        }

        error_msg = _ResponseValidator.get_error(batch_error)
        self.assertIn("Code 400", error_msg)
        self.assertIn("Bad request", error_msg)

    def test_get_error_from_single_response(self):
        """Test extracting error from a single API call response."""
        single_error = {
            "error": {
                "code": 500,
                "message": "Internal server error",
                "status": "INTERNAL",
            }
        }

        error_msg = _ResponseValidator.get_error(single_error)
        self.assertIn("Code 500", error_msg)
        self.assertIn("Internal server error", error_msg)

    def test_get_error_returns_default_for_missing_error(self):
        """Test that get_error returns default message when no error present."""
        success_response = {
            "candidates": [{"content": {"parts": [{"text": "Success"}]}}]
        }

        error_msg = _ResponseValidator.get_error(success_response)
        self.assertEqual(
            error_msg, "Invalid response structure or empty content"
        )
