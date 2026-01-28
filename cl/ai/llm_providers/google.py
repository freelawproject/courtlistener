import json
import mimetypes
import os
import tempfile
from typing import Any

from google import genai
from google.genai import types


class _ResponseValidator:
    """Internal helper to validate responses from Google GenAI API.

    Works with both batch API responses (which have a "response" wrapper)
    and single API call responses (which don't have the wrapper).
    """

    @staticmethod
    def normalize_response(result: dict) -> dict:
        """
        Normalize batch or single response to consistent format.

        Batch responses wrap the actual response in a "response" field:
        {"key": "...", "response": {"candidates": [...]}}

        Single API responses return the response directly:
        {"candidates": [...]}

        This method extracts the inner response for consistent parsing.

        :param result: Response dict from Google GenAI API
        :return: The normalized response dict (without batch wrapper)
        """
        if "response" in result:
            # Batch response - unwrap it
            return result["response"]
        # Single response - use as-is
        return result

    @staticmethod
    def get_text(result: dict) -> str | None:
        """
        Extracts the text content from a successful result.

        Works with both batch and single API responses.

        :param result: A dict from Google GenAI API (batch or single)
        :return: The extracted text, or None if not found.
        """
        try:
            normalized = _ResponseValidator.normalize_response(result)
            return normalized["candidates"][0]["content"]["parts"][0]["text"]
        except (IndexError, KeyError, TypeError):
            return None

    @staticmethod
    def get_error(result: dict) -> str | None:
        """
        Extracts the error message from a failed result.

        Works with both batch and single API responses.

        :param result: A dict from Google GenAI API (batch or single)
        :return: A formatted error string, or a default error message.
        """
        if "error" in result:
            error = result["error"]
            return f"Code {error.get('code')}: {error.get('message')}"
        return "Invalid response structure or empty content"


class GoogleGenAIBatchWrapper:
    """
    A stateless wrapper for Google GenAI batch operations, decoupled from Django.
    """

    def __init__(self, api_key: str):
        """
        Initializes the Google GenAI client.

        :param api_key: The Google API key (required, no fallback).
        :raises ValueError: If the API key is not provided.
        """
        if not api_key:
            raise ValueError("API key is required for GoogleGenAIBatchWrapper")
        self.client = genai.Client(api_key=api_key)

    def get_or_create_cache(
        self,
        system_prompt: str,
        model_name: str,
        cache_display_name: str,
        cache_ttl: str = "3600s",
    ) -> str:
        """
        Retrieves an existing cache by display name, or creates a new one.

        :param system_prompt: The system prompt text to cache.
        :param model_name: The model for which the cache is created.
        :param cache_display_name: The human-readable name for the cache.
        :param cache_ttl: TTL for cache
        :return: The full resource name of the valid cache.
        """
        for cache in self.client.caches.list():
            if cache.display_name == cache_display_name:
                print(f"Found existing cache: {cache_display_name}")
                return cache.name

        print(f"Creating new cache: {cache_display_name}")
        cached_content = self.client.caches.create(
            model=model_name,
            config=types.CreateCachedContentConfig(
                display_name=cache_display_name,
                system_instruction=types.Content(
                    parts=[types.Part(text=system_prompt)]
                ),
                ttl=cache_ttl,
            ),
        )
        print(f"Cache created successfully: {cache_display_name}")
        return cached_content.name

    def prepare_batch_requests(
        self, tasks_data: list[dict[str, Any]], user_prompt: str
    ) -> list[dict]:
        """
        Prepares request dictionaries for a batch job from raw task data.

        For each task, it uploads its input file (if provided) to the Google
        File Service and constructs the request payload.

        :param tasks_data: A list of dictionaries, where each dict represents a task.
                           Each dict must have an 'llm_key', and either an
                           'input_file_path' or 'input_text'.
        :param user_prompt: The user prompt text to be appended to each request.
        :return: A list of request dictionaries ready for JSONL formatting.
        """
        batch_requests = []
        for task_data in tasks_data:
            llm_key = task_data.get("llm_key")
            if not llm_key:
                continue

            parts = []
            if file_path := task_data.get("input_file_path"):
                mime_type, _ = mimetypes.guess_type(file_path)
                if not mime_type:
                    mime_type = "application/octet-stream"

                uploaded_file = self.client.files.upload(
                    file=file_path,
                    config=types.UploadFileConfig(
                        display_name=llm_key, mime_type=mime_type
                    ),
                )
                parts.append(
                    {
                        "file_data": {
                            "file_uri": uploaded_file.uri,
                            "mime_type": mime_type,
                        }
                    }
                )

            if text := task_data.get("input_text"):
                parts.append({"text": text})

            parts.append({"text": user_prompt})

            request_dict = {
                "key": llm_key,
                "request": {"contents": [{"parts": parts, "role": "user"}]},
            }
            batch_requests.append(request_dict)
        return batch_requests

    def execute_batch(
        self,
        model_name: str,
        requests: list[dict],
        system_prompt: str | None = None,
        cache_display_name: str | None = "cl-default-cache",
        batch_display_name: str | None = "CourtListener Batch Job",
    ) -> str:
        """
        Creates and executes a batch job with Google GenAI. If a system prompt
        is provided, it will be cached and applied to all requests in the batch.

        :param model_name: The name of the model to use.
        :param requests: A list of prepared request dictionaries.
        :param system_prompt: The system prompt text to use for this batch.
        :param cache_display_name: An optional, stable name for the system prompt cache.
        :param batch_display_name: An optional display name for the job in the Google Cloud console.
        :return: The unique name (ID) of the created batch job.
        """
        if system_prompt:
            cache_name = self.get_or_create_cache(
                system_prompt, model_name, cache_display_name
            )
            for req in requests:
                req["request"]["cached_content"] = cache_name

        jsonl_content = "\n".join(json.dumps(req) for req in requests)

        with tempfile.NamedTemporaryFile(
            mode="w+", delete=False, suffix=".jsonl"
        ) as temp_f:
            temp_f.write(jsonl_content)
            temp_f.flush()
            temp_file_path = temp_f.name

        try:
            jsonl_file = self.client.files.upload(
                file=temp_file_path,
                config=types.UploadFileConfig(
                    display_name=batch_display_name,
                    mime_type="application/jsonl",
                ),
            )
        finally:
            os.remove(temp_file_path)

        config = types.CreateBatchJobConfig(display_name=batch_display_name)

        job = self.client.batches.create(
            model=model_name,
            src=jsonl_file.name,
            config=config,
        )
        return job.name

    def get_job(self, batch_id: str) -> types.BatchJob:
        """
        Retrieves the full BatchJob object, including its status, from Google.

        :param batch_id: The unique name (ID) of the batch job.
        :return: The Google GenAI BatchJob object.
        """
        return self.client.batches.get(name=batch_id)

    def download_results(self, job: types.BatchJob) -> str:
        """
        Downloads the result file of a completed job and returns its raw content.

        :param job: A completed Google GenAI BatchJob object.
        :return: The raw JSONL content of the result file as a string.
        :raises ValueError: If the job has not succeeded.
        """
        if job.state != types.JobState.JOB_STATE_SUCCEEDED:
            raise ValueError(
                "Cannot download results for a job that has not succeeded."
            )

        return self.client.files.download(file=job.dest.file_name).decode(
            "utf-8"
        )

    def process_results(self, jsonl_content: str) -> list[dict[str, Any]]:
        """
        Parses a raw JSONL result string and validates each line item.

        :param jsonl_content: The raw JSONL content from a completed batch job.
        :return: A list of structured dictionaries, one for each task result,
                 containing the key, status, content, and any error messages.
        """
        processed_results = []
        results = [
            json.loads(line)
            for line in jsonl_content.splitlines()
            if line.strip()
        ]

        for result in results:
            key = result.get("key")
            text = _ResponseValidator.get_text(result)

            status = "SUCCEEDED" if text else "FAILED"
            processed_results.append(
                {
                    "key": key,
                    "status": status,
                    "content": text,
                    "error_message": None
                    if status == "SUCCEEDED"
                    else _ResponseValidator.get_error(result),
                    "raw_result": result,
                }
            )
        return processed_results
