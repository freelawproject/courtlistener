import os
from unittest.mock import MagicMock, patch

import pytest

from cl.ai.llm_providers.google import (
    GoogleGenAIBatchWrapper,
    _ResponseValidator,
)
from cl.ai.models import (
    LLMProvider,
    LLMRequest,
    LLMRequestStatusChoices,
    LLMTask,
    LLMTaskChoices,
    LLMTaskStatusChoices,
    Prompt,
    PromptTypes,
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
            status=LLMRequestStatusChoices.UNPROCESSED,
        )
        llm_request.prompts.add(prompt)
        self.assertEqual(LLMRequest.objects.count(), 1)
        self.assertEqual(llm_request.prompts.count(), 1)

        llm_task = LLMTask.objects.create(
            request=llm_request,
            task_type=LLMTaskChoices.CASENAME,
            content_object=self.docket,
            llm_key="test-key-1",
        )
        self.assertEqual(LLMTask.objects.count(), 1)
        self.assertEqual(llm_task.request, llm_request)
        self.assertEqual(llm_task.content_object, self.docket)
        self.assertEqual(llm_task.status, LLMTaskStatusChoices.UNPROCESSED)


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
        """Test that initialization fails without valid API key."""
        test_cases = ["", None]
        for api_key in test_cases:
            with self.subTest(api_key=api_key):
                with self.assertRaises(ValueError) as context:
                    GoogleGenAIBatchWrapper(api_key=api_key)
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
    @patch("cl.ai.llm_providers.google.types.JobState")
    def test_download_results_success(self, mock_job_state, mock_client_class):
        """Test downloading results from a succeeded job."""
        # Setup mock job
        mock_job = MagicMock()
        mock_job.state = mock_job_state.JOB_STATE_SUCCEEDED
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
        mock_state = MagicMock()
        mock_state.name = "JOB_STATE_RUNNING"
        mock_job.state = mock_state

        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        wrapper = GoogleGenAIBatchWrapper(api_key="test-key")

        with self.assertRaises(ValueError) as context:
            wrapper.download_results(mock_job)

        self.assertIn(
            "Cannot download results for job in state", str(context.exception)
        )
        self.assertIn("JOB_STATE_RUNNING", str(context.exception))
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


class SendGeminiBatchesTest(TestCase):
    """Tests for the send_gemini_batches management command."""

    def setUp(self):
        """Set up test data for each test."""
        self.system_prompt = Prompt.objects.create(
            name="Test System Prompt",
            prompt_type=PromptTypes.SYSTEM,
            text="You are a helpful assistant that extracts text from PDFs.",
        )
        self.user_prompt = Prompt.objects.create(
            name="Test User Prompt",
            prompt_type=PromptTypes.USER,
            text="Extract all text from this document.",
        )

    def _mock_s3_with_files(self, mock_boto3_client, num_files=3):
        """Helper to set up S3 mock with PDF files."""
        mock_s3_client = MagicMock()
        mock_boto3_client.return_value = mock_s3_client

        # Mock paginator
        mock_paginator = MagicMock()
        mock_s3_client.get_paginator.return_value = mock_paginator

        # Create mock file list
        contents = [
            {
                "Key": f"llm-inputs/test-batch/file{i}.pdf",
                "Size": 1024 * (i + 1),
            }
            for i in range(num_files)
        ]
        mock_paginator.paginate.return_value = [{"Contents": contents}]

        # Mock download - return different content for each file
        def mock_get_object(Bucket, Key):
            return {"Body": MagicMock(read=lambda: b"mock PDF content")}

        mock_s3_client.get_object.side_effect = mock_get_object

        return mock_s3_client

    @patch("cl.ai.management.commands.send_gemini_batches.os.remove")
    @patch(
        "cl.ai.management.commands.send_gemini_batches.tempfile.NamedTemporaryFile"
    )
    @patch(
        "cl.ai.management.commands.send_gemini_batches.GoogleGenAIBatchWrapper"
    )
    @patch("cl.ai.management.commands.send_gemini_batches.boto3.client")
    @patch.dict(
        os.environ,
        {
            "GEMINI_BATCH_API_KEY": "test-api-key-123",
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret-key",
            "AWS_STORAGE_BUCKET_NAME": "test-bucket",
        },
    )
    def test_send_gemini_batches_success(
        self,
        mock_boto3_client,
        mock_wrapper_class,
        mock_tempfile,
        mock_remove,
    ):
        """Test successful batch submission end-to-end."""
        from django.core.management import call_command

        # Setup S3 mocks
        self._mock_s3_with_files(mock_boto3_client, num_files=3)

        # Setup temp file mocks
        mock_temp_files = []
        for i in range(3):
            mock_temp = MagicMock()
            mock_temp.name = f"/tmp/mock_file_{i}.pdf"
            mock_temp_files.append(mock_temp)

        mock_tempfile.return_value.__enter__.side_effect = mock_temp_files

        # Setup Google wrapper mocks
        mock_wrapper = MagicMock()
        mock_wrapper_class.return_value = mock_wrapper
        mock_wrapper.prepare_batch_requests.return_value = [
            {"key": f"scan-batch-1-{i}", "request": {"contents": []}}
            for i in range(3)
        ]
        mock_wrapper.execute_batch.return_value = "batches/test123abc"

        # Execute command
        call_command(
            "send_gemini_batches",
            path="llm-inputs/test-batch/",
            system_prompt=self.system_prompt.pk,
            user_prompt=self.user_prompt.pk,
            model="gemini-2.5-pro",
            request_name="Test Batch",
            cache_name="test-cache-v1",
        )

        # Assertions
        self.assertEqual(LLMRequest.objects.count(), 1)
        llm_request = LLMRequest.objects.first()
        self.assertEqual(llm_request.status, LLMTaskStatusChoices.IN_PROGRESS)
        self.assertEqual(llm_request.total_tasks, 3)
        self.assertEqual(llm_request.batch_id, "batches/test123abc")
        self.assertEqual(llm_request.provider, LLMProvider.GEMINI)
        self.assertEqual(llm_request.api_model_name, "gemini-2.5-pro")
        self.assertIsNotNone(llm_request.date_started)

        # Check LLMTask objects
        self.assertEqual(LLMTask.objects.count(), 3)
        for task in LLMTask.objects.all():
            self.assertEqual(task.request, llm_request)
            self.assertEqual(task.task, LLMTaskChoices.SCAN_EXTRACTION)
            self.assertTrue(task.llm_key.startswith("scan-batch-"))

        # Verify API calls
        mock_wrapper.prepare_batch_requests.assert_called_once()
        mock_wrapper.execute_batch.assert_called_once()

        # Verify temp file cleanup
        self.assertEqual(mock_remove.call_count, 3)

    @patch("cl.ai.management.commands.send_gemini_batches.os.remove")
    @patch(
        "cl.ai.management.commands.send_gemini_batches.tempfile.NamedTemporaryFile"
    )
    @patch(
        "cl.ai.management.commands.send_gemini_batches.GoogleGenAIBatchWrapper"
    )
    @patch("cl.ai.management.commands.send_gemini_batches.boto3.client")
    @patch.dict(
        os.environ,
        {
            "GEMINI_BATCH_API_KEY": "test-api-key-123",
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret-key",
            "AWS_STORAGE_BUCKET_NAME": "test-bucket",
        },
    )
    def test_send_gemini_batches_with_store_input_files(
        self,
        mock_boto3_client,
        mock_wrapper_class,
        mock_tempfile,
        mock_remove,
    ):
        """Test --store-input-files flag stores files in CourtListener storage."""
        from django.core.management import call_command

        # Setup S3 mocks
        self._mock_s3_with_files(mock_boto3_client, num_files=2)

        # Setup temp file mocks
        mock_temp_files = []
        for i in range(2):
            mock_temp = MagicMock()
            mock_temp.name = f"/tmp/mock_file_{i}.pdf"
            mock_temp_files.append(mock_temp)

        mock_tempfile.return_value.__enter__.side_effect = mock_temp_files

        # Setup Google wrapper mocks
        mock_wrapper = MagicMock()
        mock_wrapper_class.return_value = mock_wrapper
        mock_wrapper.prepare_batch_requests.return_value = [
            {"key": f"scan-batch-1-{i}", "request": {"contents": []}}
            for i in range(2)
        ]
        mock_wrapper.execute_batch.return_value = "batches/test456def"

        # Execute command with store_input_files flag
        call_command(
            "send_gemini_batches",
            path="llm-inputs/test-batch/",
            system_prompt=self.system_prompt.pk,
            user_prompt=self.user_prompt.pk,
            store_input_files=True,
        )

        # Verify files were stored (not just referenced)
        self.assertEqual(LLMTask.objects.count(), 2)
        for task in LLMTask.objects.all():
            # When store_input_files=True, the file is saved via .save()
            # which creates a real file path, not just an S3 key
            self.assertTrue(task.input_file.name)
            # The name should not be the S3 path format when stored
            self.assertFalse(task.input_file.name.startswith("llm-inputs/"))

    @patch.dict(
        os.environ,
        {
            "GEMINI_BATCH_API_KEY": "test-api-key-123",
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret-key",
            "AWS_STORAGE_BUCKET_NAME": "test-bucket",
        },
    )
    def test_send_gemini_batches_invalid_model(self):
        """Test validation fails for unsupported Gemini model."""
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError) as context:
            call_command(
                "send_gemini_batches",
                path="llm-inputs/test/",
                system_prompt=self.system_prompt.pk,
                user_prompt=self.user_prompt.pk,
                model="invalid-model-name",
            )

        self.assertIn("Invalid Gemini model", str(context.exception))
        self.assertIn("Supported models", str(context.exception))

        # Verify no database objects were created
        self.assertEqual(LLMRequest.objects.count(), 0)
        self.assertEqual(LLMTask.objects.count(), 0)

    @patch.dict(
        os.environ,
        {
            "GEMINI_BATCH_API_KEY": "test-api-key-123",
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret-key",
            "AWS_STORAGE_BUCKET_NAME": "test-bucket",
        },
    )
    def test_send_gemini_batches_invalid_prompts(self):
        """Test validation fails for invalid prompts (wrong type or non-existent)."""
        from django.core.management import call_command
        from django.core.management.base import CommandError

        # Test case 1: Prompt exists but has wrong type
        with self.subTest(case="wrong_prompt_type"):
            # Create a USER prompt but pass it as system_prompt argument
            wrong_type_prompt = Prompt.objects.create(
                name="Wrong Type",
                prompt_type=PromptTypes.USER,
                text="This should be SYSTEM",
            )

            with self.assertRaises(CommandError) as context:
                call_command(
                    "send_gemini_batches",
                    path="llm-inputs/test/",
                    system_prompt=wrong_type_prompt.pk,
                    user_prompt=self.user_prompt.pk,
                )

            self.assertIn(
                "Invalid system or user prompt", str(context.exception)
            )

        # Test case 2: Prompt doesn't exist at all
        with self.subTest(case="nonexistent_prompt"):
            with self.assertRaises(CommandError) as context:
                call_command(
                    "send_gemini_batches",
                    path="llm-inputs/test/",
                    system_prompt=99999,  # Non-existent
                    user_prompt=self.user_prompt.pk,
                )

            self.assertIn(
                "Invalid system or user prompt", str(context.exception)
            )

    @patch("cl.ai.management.commands.send_gemini_batches.os.remove")
    @patch(
        "cl.ai.management.commands.send_gemini_batches.tempfile.NamedTemporaryFile"
    )
    @patch(
        "cl.ai.management.commands.send_gemini_batches.GoogleGenAIBatchWrapper"
    )
    @patch("cl.ai.management.commands.send_gemini_batches.boto3.client")
    @patch.dict(
        os.environ,
        {
            "GEMINI_BATCH_API_KEY": "test-api-key-123",
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret-key",
            "AWS_STORAGE_BUCKET_NAME": "test-bucket",
        },
    )
    def test_send_gemini_batches_empty_s3_path(
        self,
        mock_boto3_client,
        mock_wrapper_class,
        mock_tempfile,
        mock_remove,
    ):
        """Test handling when S3 path has no files."""
        from django.core.management import call_command
        from django.core.management.base import CommandError

        # Setup S3 mock to return empty list
        mock_s3_client = MagicMock()
        mock_boto3_client.return_value = mock_s3_client
        mock_paginator = MagicMock()
        mock_s3_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{}]  # No "Contents" key

        # Should raise CommandError about no files found
        with self.assertRaises(CommandError) as context:
            call_command(
                "send_gemini_batches",
                path="llm-inputs/empty/",
                system_prompt=self.system_prompt.pk,
                user_prompt=self.user_prompt.pk,
            )

        self.assertIn("No .pdf files found", str(context.exception))

    @patch("cl.ai.management.commands.send_gemini_batches.os.remove")
    @patch(
        "cl.ai.management.commands.send_gemini_batches.tempfile.NamedTemporaryFile"
    )
    @patch(
        "cl.ai.management.commands.send_gemini_batches.GoogleGenAIBatchWrapper"
    )
    @patch("cl.ai.management.commands.send_gemini_batches.boto3.client")
    @patch.dict(
        os.environ,
        {
            "GEMINI_BATCH_API_KEY": "test-api-key-123",
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret-key",
            "AWS_STORAGE_BUCKET_NAME": "test-bucket",
        },
    )
    def test_send_gemini_batches_gemini_api_error(
        self,
        mock_boto3_client,
        mock_wrapper_class,
        mock_tempfile,
        mock_remove,
    ):
        """Test error handling when Gemini API fails."""
        from django.core.management import call_command
        from django.core.management.base import CommandError

        # Setup S3 mocks
        self._mock_s3_with_files(mock_boto3_client, num_files=2)

        # Setup temp file mocks
        mock_temp_files = []
        for i in range(2):
            mock_temp = MagicMock()
            mock_temp.name = f"/tmp/mock_file_{i}.pdf"
            mock_temp_files.append(mock_temp)

        mock_tempfile.return_value.__enter__.side_effect = mock_temp_files

        # Setup Google wrapper to raise exception
        mock_wrapper = MagicMock()
        mock_wrapper_class.return_value = mock_wrapper
        mock_wrapper.prepare_batch_requests.return_value = []
        mock_wrapper.execute_batch.side_effect = Exception("API Error")

        # Execute command - should fail gracefully
        with self.assertRaises(CommandError) as context:
            call_command(
                "send_gemini_batches",
                path="llm-inputs/test-batch/",
                system_prompt=self.system_prompt.pk,
                user_prompt=self.user_prompt.pk,
            )

        self.assertIn("Failed to create batch job", str(context.exception))

        # Verify request was created but marked as FAILED
        self.assertEqual(LLMRequest.objects.count(), 1)
        llm_request = LLMRequest.objects.first()
        self.assertEqual(llm_request.status, LLMTaskStatusChoices.FAILED)

    @patch("cl.ai.management.commands.send_gemini_batches.boto3.client")
    @patch.dict(
        os.environ,
        {
            "GEMINI_BATCH_API_KEY": "test-api-key-123",
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret-key",
            "AWS_STORAGE_BUCKET_NAME": "test-bucket",
        },
    )
    def test_send_gemini_batches_s3_access_denied(self, mock_boto3_client):
        """Test error handling for S3 permission errors."""
        from botocore.exceptions import ClientError
        from django.core.management import call_command
        from django.core.management.base import CommandError

        # Setup S3 mock to raise AccessDenied error
        mock_s3_client = MagicMock()
        mock_boto3_client.return_value = mock_s3_client
        mock_paginator = MagicMock()
        mock_s3_client.get_paginator.return_value = mock_paginator

        error_response = {"Error": {"Code": "AccessDenied"}}
        mock_paginator.paginate.side_effect = ClientError(
            error_response, "ListObjects"
        )

        with self.assertRaises(CommandError) as context:
            call_command(
                "send_gemini_batches",
                path="llm-inputs/test/",
                system_prompt=self.system_prompt.pk,
                user_prompt=self.user_prompt.pk,
            )

        self.assertIn("Access denied", str(context.exception))

    @patch("cl.ai.management.commands.send_gemini_batches.os.remove")
    @patch(
        "cl.ai.management.commands.send_gemini_batches.tempfile.NamedTemporaryFile"
    )
    @patch(
        "cl.ai.management.commands.send_gemini_batches.GoogleGenAIBatchWrapper"
    )
    @patch("cl.ai.management.commands.send_gemini_batches.boto3.client")
    @patch.dict(
        os.environ,
        {
            "GEMINI_BATCH_API_KEY": "test-api-key-123",
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret-key",
            "AWS_STORAGE_BUCKET_NAME": "test-bucket",
        },
    )
    def test_send_gemini_batches_custom_bucket(
        self,
        mock_boto3_client,
        mock_wrapper_class,
        mock_tempfile,
        mock_remove,
    ):
        """Test --bucket parameter works."""
        from django.core.management import call_command
        from django.core.management.base import CommandError

        # Setup S3 mocks
        self._mock_s3_with_files(mock_boto3_client, num_files=1)

        # Try with a custom bucket that's not in the allowed list
        with self.assertRaises(CommandError) as context:
            call_command(
                "send_gemini_batches",
                path="llm-inputs/test/",
                system_prompt=self.system_prompt.pk,
                user_prompt=self.user_prompt.pk,
                bucket="custom-bucket-name",
            )

        self.assertIn("not in allowed list", str(context.exception))


class CheckGeminiBatchStatusTest(TestCase):
    """Tests for the check_gemini_batch_status management command."""

    def setUp(self):
        """Set up test data for each test."""
        self.system_prompt = Prompt.objects.create(
            name="Test System Prompt",
            prompt_type=PromptTypes.SYSTEM,
            text="You are a helpful assistant.",
        )
        self.user_prompt = Prompt.objects.create(
            name="Test User Prompt",
            prompt_type=PromptTypes.USER,
            text="Extract text from this document.",
        )

    def _create_request_with_tasks(self, batch_id, num_tasks=3):
        """Helper to create LLMRequest with tasks."""
        llm_request = LLMRequest.objects.create(
            name="Test Batch Request",
            is_batch=True,
            provider=LLMProvider.GEMINI,
            api_model_name="gemini-2.5-pro",
            status=LLMTaskStatusChoices.IN_PROGRESS,
            batch_id=batch_id,
            total_tasks=num_tasks,
        )
        llm_request.prompts.set([self.system_prompt, self.user_prompt])

        tasks = []
        for i in range(num_tasks):
            # Use the same format as in mock results: scan-batch-{pk}-{index}
            task = LLMTask.objects.create(
                request=llm_request,
                task=LLMTaskChoices.SCAN_EXTRACTION,
                llm_key=f"scan-batch-{llm_request.pk}-{i}",
                status=LLMTaskStatusChoices.IN_PROGRESS,  # Set to IN_PROGRESS to match request status
            )
            tasks.append(task)

        return llm_request, tasks

    @patch(
        "cl.ai.management.commands.check_gemini_batch_status.GoogleGenAIBatchWrapper"
    )
    @patch.dict(
        os.environ,
        {"GEMINI_BATCH_API_KEY": "test-api-key-123"},
    )
    def test_check_status_job_succeeded(self, mock_wrapper_class):
        """Test successful result processing when job succeeds."""
        from django.core.management import call_command

        # Create test data
        llm_request, tasks = self._create_request_with_tasks(
            "batches/test123", num_tasks=3
        )

        # Setup mock wrapper
        mock_wrapper = MagicMock()
        mock_wrapper_class.return_value = mock_wrapper

        # Mock job status
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_SUCCEEDED"
        mock_wrapper.get_job.return_value = mock_job

        # Mock JSONL content - use actual request pk
        request_pk = llm_request.pk
        jsonl_content = (
            f'{{"key": "scan-batch-{request_pk}-0", "response": {{"candidates": [{{"content": {{"parts": [{{"text": "Result 1"}}]}}}}]}}}}\n'
            f'{{"key": "scan-batch-{request_pk}-1", "response": {{"candidates": [{{"content": {{"parts": [{{"text": "Result 2"}}]}}}}]}}}}\n'
            f'{{"key": "scan-batch-{request_pk}-2", "response": {{"candidates": [{{"content": {{"parts": [{{"text": "Result 3"}}]}}}}]}}}}'
        )
        mock_wrapper.download_results.return_value = jsonl_content

        # Mock processed results - use actual request pk
        mock_wrapper.process_results.return_value = [
            {
                "key": f"scan-batch-{request_pk}-0",
                "status": "SUCCEEDED",
                "content": "Result 1",
                "error_message": None,
                "raw_result": {"test": "data1"},
            },
            {
                "key": f"scan-batch-{request_pk}-1",
                "status": "SUCCEEDED",
                "content": "Result 2",
                "error_message": None,
                "raw_result": {"test": "data2"},
            },
            {
                "key": f"scan-batch-{request_pk}-2",
                "status": "SUCCEEDED",
                "content": "Result 3",
                "error_message": None,
                "raw_result": {"test": "data3"},
            },
        ]

        # Execute command
        call_command("check_gemini_batch_status")

        # Assertions
        mock_wrapper.get_job.assert_called_once_with("batches/test123")
        mock_wrapper.download_results.assert_called_once()
        mock_wrapper.process_results.assert_called_once()

        # Check LLMRequest status
        llm_request.refresh_from_db()
        self.assertEqual(llm_request.status, LLMTaskStatusChoices.FINISHED)
        self.assertEqual(llm_request.completed_tasks, 3)
        self.assertEqual(llm_request.failed_tasks, 0)
        self.assertIsNotNone(llm_request.date_completed)
        self.assertTrue(llm_request.batch_response_file)

        # Check all tasks
        for task in tasks:
            task.refresh_from_db()
            self.assertEqual(task.status, LLMTaskStatusChoices.SUCCEEDED)
            self.assertEqual(task.error_message, "")
            self.assertTrue(task.response_file)

    @patch(
        "cl.ai.management.commands.check_gemini_batch_status.GoogleGenAIBatchWrapper"
    )
    @patch.dict(
        os.environ,
        {"GEMINI_BATCH_API_KEY": "test-api-key-123"},
    )
    def test_check_status_job_with_mixed_results(self, mock_wrapper_class):
        """Test handling of both successful and failed tasks."""
        from django.core.management import call_command

        # Create test data
        llm_request, tasks = self._create_request_with_tasks(
            "batches/test456", num_tasks=3
        )

        # Setup mock wrapper
        mock_wrapper = MagicMock()
        mock_wrapper_class.return_value = mock_wrapper

        # Mock job status
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_SUCCEEDED"
        mock_wrapper.get_job.return_value = mock_job

        # Mock JSONL content with mixed results - use actual request pk
        request_pk = llm_request.pk
        jsonl_content = (
            f'{{"key": "scan-batch-{request_pk}-0", "response": {{}}}}'
        )
        mock_wrapper.download_results.return_value = jsonl_content

        # Mock processed results with mixed success/failure - use actual request pk
        mock_wrapper.process_results.return_value = [
            {
                "key": f"scan-batch-{request_pk}-0",
                "status": "SUCCEEDED",
                "content": "Success",
                "error_message": None,
                "raw_result": {"test": "data"},
            },
            {
                "key": f"scan-batch-{request_pk}-1",
                "status": "FAILED",
                "content": None,
                "error_message": "API error occurred",
                "raw_result": None,
            },
            {
                "key": f"scan-batch-{request_pk}-2",
                "status": "SUCCEEDED",
                "content": "Success",
                "error_message": None,
                "raw_result": {"test": "data"},
            },
        ]

        # Execute command
        call_command("check_gemini_batch_status")

        # Assertions
        llm_request.refresh_from_db()
        self.assertEqual(llm_request.status, LLMTaskStatusChoices.FINISHED)
        self.assertEqual(llm_request.completed_tasks, 2)
        self.assertEqual(llm_request.failed_tasks, 1)

        # Check individual tasks
        tasks[0].refresh_from_db()
        self.assertEqual(tasks[0].status, LLMTaskStatusChoices.SUCCEEDED)
        self.assertEqual(tasks[0].error_message, "")

        tasks[1].refresh_from_db()
        self.assertEqual(tasks[1].status, LLMTaskStatusChoices.FAILED)
        self.assertEqual(tasks[1].error_message, "API error occurred")

        tasks[2].refresh_from_db()
        self.assertEqual(tasks[2].status, LLMTaskStatusChoices.SUCCEEDED)
        self.assertEqual(tasks[2].error_message, "")

    @patch(
        "cl.ai.management.commands.check_gemini_batch_status.GoogleGenAIBatchWrapper"
    )
    @patch.dict(
        os.environ,
        {"GEMINI_BATCH_API_KEY": "test-api-key-123"},
    )
    def test_check_status_job_non_success_states(self, mock_wrapper_class):
        """Test handling when batch jobs end in non-success states (FAILED, CANCELLED, EXPIRED)."""
        from django.core.management import call_command

        # Test all three non-success states using subTest
        test_cases = [
            ("JOB_STATE_FAILED", "batches/test789"),
            ("JOB_STATE_CANCELLED", "batches/cancelled"),
            ("JOB_STATE_EXPIRED", "batches/expired"),
        ]

        for state_name, batch_id in test_cases:
            with self.subTest(state=state_name):
                # Create test data
                llm_request, tasks = self._create_request_with_tasks(
                    batch_id, num_tasks=2
                )

                # Setup mock wrapper
                mock_wrapper = MagicMock()
                mock_wrapper_class.return_value = mock_wrapper

                # Mock job status
                mock_job = MagicMock()
                mock_job.state.name = state_name
                mock_wrapper.get_job.return_value = mock_job

                # Execute command
                call_command("check_gemini_batch_status")

                # Assertions - all three states follow the same code path
                mock_wrapper.download_results.assert_not_called()

                # Check LLMRequest
                llm_request.refresh_from_db()
                self.assertEqual(
                    llm_request.status, LLMTaskStatusChoices.FAILED
                )
                self.assertIsNotNone(llm_request.date_completed)

                # Check all tasks marked as failed with state in error message
                for task in tasks:
                    task.refresh_from_db()
                    self.assertEqual(task.status, LLMTaskStatusChoices.FAILED)
                    self.assertIn(state_name, task.error_message)

    @patch(
        "cl.ai.management.commands.check_gemini_batch_status.GoogleGenAIBatchWrapper"
    )
    @patch.dict(
        os.environ,
        {"GEMINI_BATCH_API_KEY": "test-api-key-123"},
    )
    def test_check_status_job_still_running(self, mock_wrapper_class):
        """Test command skips jobs that are still running."""
        from django.core.management import call_command

        # Create two requests
        running_request, _ = self._create_request_with_tasks(
            "batches/running", num_tasks=2
        )
        succeeded_request, _ = self._create_request_with_tasks(
            "batches/succeeded", num_tasks=2
        )

        # Setup mock wrapper
        mock_wrapper = MagicMock()
        mock_wrapper_class.return_value = mock_wrapper

        # Mock different job states
        def get_job_side_effect(batch_id):
            mock_job = MagicMock()
            if batch_id == "batches/running":
                mock_job.state.name = "JOB_STATE_RUNNING"
            else:
                mock_job.state.name = "JOB_STATE_SUCCEEDED"
            return mock_job

        mock_wrapper.get_job.side_effect = get_job_side_effect
        mock_wrapper.download_results.return_value = "{}"
        mock_wrapper.process_results.return_value = []

        # Execute command
        call_command("check_gemini_batch_status")

        # Assertions
        running_request.refresh_from_db()
        self.assertEqual(
            running_request.status, LLMTaskStatusChoices.IN_PROGRESS
        )
        self.assertIsNone(running_request.date_completed)

        succeeded_request.refresh_from_db()
        self.assertEqual(
            succeeded_request.status, LLMTaskStatusChoices.FINISHED
        )
        self.assertIsNotNone(succeeded_request.date_completed)

    @patch(
        "cl.ai.management.commands.check_gemini_batch_status.GoogleGenAIBatchWrapper"
    )
    @patch.dict(
        os.environ,
        {"GEMINI_BATCH_API_KEY": "test-api-key-123"},
    )
    def test_check_status_download_error(self, mock_wrapper_class):
        """Test error handling when download fails."""
        from django.core.management import call_command

        # Create test data
        llm_request, tasks = self._create_request_with_tasks(
            "batches/downloaderror", num_tasks=2
        )

        # Setup mock wrapper
        mock_wrapper = MagicMock()
        mock_wrapper_class.return_value = mock_wrapper

        # Mock job succeeded but download fails
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_SUCCEEDED"
        mock_wrapper.get_job.return_value = mock_job
        mock_wrapper.download_results.side_effect = ValueError(
            "Download failed"
        )

        # Execute command
        call_command("check_gemini_batch_status")

        # Should catch the error and leave request IN_PROGRESS
        llm_request.refresh_from_db()
        self.assertEqual(llm_request.status, LLMTaskStatusChoices.IN_PROGRESS)

    @patch(
        "cl.ai.management.commands.check_gemini_batch_status.GoogleGenAIBatchWrapper"
    )
    @patch.dict(
        os.environ,
        {"GEMINI_BATCH_API_KEY": "test-api-key-123"},
    )
    def test_check_status_process_results_error(self, mock_wrapper_class):
        """Test handling when result processing fails."""
        from django.core.management import call_command

        # Create test data
        llm_request, tasks = self._create_request_with_tasks(
            "batches/processerror", num_tasks=1
        )

        # Setup mock wrapper
        mock_wrapper = MagicMock()
        mock_wrapper_class.return_value = mock_wrapper

        # Mock job succeeded but processing fails
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_SUCCEEDED"
        mock_wrapper.get_job.return_value = mock_job
        mock_wrapper.download_results.return_value = "{}"
        mock_wrapper.process_results.side_effect = Exception(
            "Processing failed"
        )

        # Execute command
        call_command("check_gemini_batch_status")

        # Should mark request as FAILED
        llm_request.refresh_from_db()
        self.assertEqual(llm_request.status, LLMTaskStatusChoices.FAILED)
        self.assertIsNotNone(llm_request.date_completed)

    @patch(
        "cl.ai.management.commands.check_gemini_batch_status.GoogleGenAIBatchWrapper"
    )
    @patch.dict(
        os.environ,
        {"GEMINI_BATCH_API_KEY": "test-api-key-123"},
    )
    def test_check_status_multiple_batches(self, mock_wrapper_class):
        """Test command processes multiple pending batches."""
        from django.core.management import call_command

        # Create 3 requests with different states
        request1, _ = self._create_request_with_tasks(
            "batches/multi1", num_tasks=1
        )
        request2, _ = self._create_request_with_tasks(
            "batches/multi2", num_tasks=1
        )
        request3, _ = self._create_request_with_tasks(
            "batches/multi3", num_tasks=1
        )

        # Setup mock wrapper
        mock_wrapper = MagicMock()
        mock_wrapper_class.return_value = mock_wrapper

        # Mock different states for each job
        def get_job_side_effect(batch_id):
            mock_job = MagicMock()
            if batch_id == "batches/multi1":
                mock_job.state.name = "JOB_STATE_SUCCEEDED"
            elif batch_id == "batches/multi2":
                mock_job.state.name = "JOB_STATE_FAILED"
            else:
                mock_job.state.name = "JOB_STATE_RUNNING"
            return mock_job

        mock_wrapper.get_job.side_effect = get_job_side_effect
        mock_wrapper.download_results.return_value = "{}"
        mock_wrapper.process_results.return_value = []

        # Execute command
        call_command("check_gemini_batch_status")

        # Check each request was processed correctly
        self.assertEqual(mock_wrapper.get_job.call_count, 3)

        request1.refresh_from_db()
        self.assertEqual(request1.status, LLMTaskStatusChoices.FINISHED)

        request2.refresh_from_db()
        self.assertEqual(request2.status, LLMTaskStatusChoices.FAILED)

        request3.refresh_from_db()
        self.assertEqual(request3.status, LLMTaskStatusChoices.IN_PROGRESS)

    @patch(
        "cl.ai.management.commands.check_gemini_batch_status.GoogleGenAIBatchWrapper"
    )
    @patch.dict(
        os.environ,
        {"GEMINI_BATCH_API_KEY": "test-api-key-123"},
    )
    def test_check_status_task_not_found(self, mock_wrapper_class):
        """Test handling when task key doesn't match any LLMTask."""
        from django.core.management import call_command

        # Create test data
        llm_request, tasks = self._create_request_with_tasks(
            "batches/notfound", num_tasks=2
        )

        # Setup mock wrapper
        mock_wrapper = MagicMock()
        mock_wrapper_class.return_value = mock_wrapper

        # Mock job succeeded
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_SUCCEEDED"
        mock_wrapper.get_job.return_value = mock_job
        mock_wrapper.download_results.return_value = "{}"

        # Return results with a key that doesn't exist - use actual request pk
        request_pk = llm_request.pk
        mock_wrapper.process_results.return_value = [
            {
                "key": f"scan-batch-{request_pk}-0",
                "status": "SUCCEEDED",
                "content": "Success",
                "error_message": None,
                "raw_result": {"test": "data"},
            },
            {
                "key": "nonexistent-key",  # This key doesn't exist
                "status": "SUCCEEDED",
                "content": "Success",
                "error_message": None,
                "raw_result": {"test": "data"},
            },
        ]

        # Execute command - should not crash
        call_command("check_gemini_batch_status")

        # Request should still be marked as finished
        llm_request.refresh_from_db()
        self.assertEqual(llm_request.status, LLMTaskStatusChoices.FINISHED)

        # First task should be updated
        tasks[0].refresh_from_db()
        self.assertEqual(tasks[0].status, LLMTaskStatusChoices.SUCCEEDED)

        # Second task should remain in progress (no matching key)
        tasks[1].refresh_from_db()
        self.assertEqual(tasks[1].status, LLMTaskStatusChoices.IN_PROGRESS)

    @patch(
        "cl.ai.management.commands.check_gemini_batch_status.GoogleGenAIBatchWrapper"
    )
    @patch.dict(
        os.environ,
        {"GEMINI_BATCH_API_KEY": "test-api-key-123"},
    )
    def test_check_status_response_file_save_error(self, mock_wrapper_class):
        """Test fallback when JSON serialization fails."""
        from django.core.management import call_command

        # Create test data
        llm_request, tasks = self._create_request_with_tasks(
            "batches/jsonerror", num_tasks=1
        )

        # Setup mock wrapper
        mock_wrapper = MagicMock()
        mock_wrapper_class.return_value = mock_wrapper

        # Mock job succeeded
        mock_job = MagicMock()
        mock_job.state.name = "JOB_STATE_SUCCEEDED"
        mock_wrapper.get_job.return_value = mock_job
        mock_wrapper.download_results.return_value = "{}"

        # Create a circular reference that can't be JSON serialized
        circular_obj = {}
        circular_obj["self"] = circular_obj

        # Use actual request pk
        request_pk = llm_request.pk
        mock_wrapper.process_results.return_value = [
            {
                "key": f"scan-batch-{request_pk}-0",
                "status": "SUCCEEDED",
                "content": "Success",
                "error_message": None,
                "raw_result": circular_obj,  # Can't be JSON serialized
            }
        ]

        # Execute command - should fall back to text storage
        call_command("check_gemini_batch_status")

        # Task should still be marked as succeeded
        tasks[0].refresh_from_db()
        self.assertEqual(tasks[0].status, LLMTaskStatusChoices.SUCCEEDED)
        # Response file should be saved (as .txt instead of .json)
        self.assertTrue(tasks[0].response_file)
