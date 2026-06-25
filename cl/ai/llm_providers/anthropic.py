import base64
import json
import logging
import mimetypes
from datetime import date
from typing import Any, TypedDict

import anthropic
from anthropic.types.message_create_params import (
    MessageCreateParamsNonStreaming,
)
from anthropic.types.messages import MessageBatch
from anthropic.types.messages.batch_create_params import Request

logger = logging.getLogger(__name__)

# Default ceiling on tokens generated per task. Extraction outputs can be
# long; callers may override via ``execute_batch``.
DEFAULT_MAX_TOKENS = 8192

# Processing status returned by the Message Batches API once a batch has
# finished (whether or not every request succeeded). Individual request
# outcomes are inspected separately in ``process_results``.
BATCH_ENDED_STATUS = "ended"

# Supported Anthropic models for batch operations.
# Maps model name to its retirement date (None if no date announced).
# See https://docs.claude.com/en/docs/about-claude/model-deprecations
SUPPORTED_ANTHROPIC_MODELS: dict[str, date | None] = {
    "claude-opus-4-8": None,
    "claude-opus-4-7": None,
    "claude-opus-4-6": None,
    "claude-opus-4-5": None,
    "claude-opus-4-1": date(2026, 8, 5),
    "claude-sonnet-4-6": None,
    "claude-sonnet-4-5": None,
    "claude-haiku-4-5": None,
}


class ProcessedResult(TypedDict):
    """Structure for a processed batch result.

    Mirrors the shape produced by the Google provider so the shared
    status-checking command can consume either provider's output.
    """

    key: str
    status: str  # "SUCCEEDED" or "FAILED"
    content: str | None
    error_message: str | None
    raw_result: dict[str, Any]


class _ResponseValidator:
    """Internal helper to read Message Batches result items.

    Each item is the ``to_dict()`` form of a result streamed from
    ``client.messages.batches.results(...)`` — a dict with a ``custom_id``
    and a ``result`` whose ``type`` is one of ``succeeded``, ``errored``,
    ``canceled``, or ``expired``.
    """

    @staticmethod
    def get_text(result: dict) -> str | None:
        """Extract concatenated text from a succeeded result.

        :param result: A batch result item in dict form.
        :return: The joined text of every ``text`` content block, or None
            if the request did not succeed or carried no text.
        """
        inner = result.get("result", {})
        if inner.get("type") != "succeeded":
            return None
        try:
            blocks = inner["message"]["content"]
        except (KeyError, TypeError):
            return None
        texts = [
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        joined = "".join(texts)
        return joined or None

    @staticmethod
    def get_error(result: dict) -> str | None:
        """Extract an error message from a non-succeeded result.

        :param result: A batch result item in dict form.
        :return: A formatted error string, or a default message.
        """
        inner = result.get("result", {})
        result_type = inner.get("type")
        if result_type == "errored":
            error = inner.get("error", {})
            # The error payload nests the actual error under "error".
            detail = error.get("error", error)
            err_type = detail.get("type", "unknown")
            message = detail.get("message", "")
            return f"{err_type}: {message}".strip(": ")
        if result_type in ("canceled", "expired"):
            return f"Request {result_type} before completion"
        return "Invalid response structure or empty content"


class AnthropicBatchWrapper:
    """A stateless wrapper for Anthropic Message Batches, decoupled from
    Django.

    Parallels ``GoogleGenAIBatchWrapper`` so the two providers expose the
    same surface to the batch management commands. Two notable differences
    from the Gemini path simplify this implementation:

    * ``messages.batches.create`` accepts the request list directly — there
      is no intermediate JSONL file to upload.
    * Prompt caching is implicit prefix caching applied via a
      ``cache_control`` breakpoint on the system block, so there is no cache
      object to create or look up.
    """

    def __init__(self, api_key: str, model_name: str | None = None):
        """Initialize the Anthropic client.

        :param api_key: The Anthropic API key (required, no fallback).
        :param model_name: Optional model name. When provided, it is
            validated and stored for later use by ``execute_batch``.
        :raises ValueError: If the API key is not provided or the model is
            invalid.
        """
        if not api_key:
            raise ValueError("API key is required for AnthropicBatchWrapper")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model_name: str | None = None
        if model_name is not None:
            self.validate_model(model_name)
            self.model_name = model_name

    @staticmethod
    def validate_model(model: str) -> None:
        """Validate that a model is supported and not past its retirement
        date.

        Logs a warning when the model has no announced retirement date,
        prompting the caller to verify manually.

        :param model: The Anthropic model name to validate.
        :raises ValueError: If the model is not supported or past its
            retirement date.
        """
        if model not in SUPPORTED_ANTHROPIC_MODELS:
            raise ValueError(
                f"Invalid Anthropic model '{model}'. Supported models: "
                f"{', '.join(sorted(SUPPORTED_ANTHROPIC_MODELS))}"
            )

        retirement_date = SUPPORTED_ANTHROPIC_MODELS[model]
        if retirement_date is None:
            logger.warning(
                "Model '%s' does not have a retirement date. Verify at "
                "https://docs.claude.com/en/docs/about-claude/"
                "model-deprecations",
                model,
            )
            return

        if date.today() >= retirement_date:
            raise ValueError(
                f"Model '{model}' was retired on {retirement_date}. See "
                "https://docs.claude.com/en/docs/about-claude/"
                "model-deprecations"
            )

    def prepare_batch_requests(
        self, tasks_data: list[dict[str, Any]], user_prompt: str
    ) -> list[dict]:
        """Prepare per-task content from raw task data.

        For each task, an inline document block is built from its input
        file (base64-encoded) and/or a text block from its inline text,
        followed by the shared user prompt. The system prompt is applied
        later, in ``execute_batch``.

        :param tasks_data: A list of dicts, each with an ``llm_key`` and
            either an ``input_file_path`` or ``input_text``.
        :param user_prompt: The user prompt text appended to each request.
        :return: A list of dicts with ``custom_id`` and ``content`` keys,
            ready to be assembled into batch requests.
        """
        prepared: list[dict] = []
        for task_data in tasks_data:
            llm_key = task_data.get("llm_key")
            if not llm_key:
                continue

            content: list[dict[str, Any]] = []
            if file_path := task_data.get("input_file_path"):
                # Inline base64 documents are limited to 32 MB / 600 pages
                # per request; larger inputs need the Files API.
                media_type, _ = mimetypes.guess_type(file_path)
                if not media_type:
                    media_type = "application/pdf"
                with open(file_path, "rb") as fh:
                    encoded = base64.standard_b64encode(fh.read()).decode(
                        "utf-8"
                    )
                content.append(
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": encoded,
                        },
                    }
                )

            if text := task_data.get("input_text"):
                content.append({"type": "text", "text": text})

            content.append({"type": "text", "text": user_prompt})

            prepared.append({"custom_id": llm_key, "content": content})
        return prepared

    def execute_batch(
        self,
        requests: list[dict],
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        """Create and submit a Message Batches job.

        When a system prompt is provided it is attached to every request
        with a ``cache_control`` breakpoint, so the shared prefix is cached
        across the batch.

        Requires ``model_name`` to have been set at construction time.

        :param requests: Prepared dicts from ``prepare_batch_requests``.
        :param system_prompt: System prompt text shared across the batch.
        :param max_tokens: Maximum tokens to generate per request.
        :return: The batch ID assigned by the provider.
        :raises ValueError: If ``model_name`` was not provided at init.
        """
        if not self.model_name:
            raise ValueError(
                "model_name is required for batch execution. Pass it when "
                "constructing AnthropicBatchWrapper."
            )

        system: list[dict[str, Any]] | None = None
        if system_prompt:
            system = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }
            ]

        batch_requests: list[Request] = []
        for req in requests:
            params: dict[str, Any] = {
                "model": self.model_name,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": req["content"]}],
            }
            if system is not None:
                params["system"] = system
            batch_requests.append(
                Request(
                    custom_id=req["custom_id"],
                    params=MessageCreateParamsNonStreaming(**params),
                )
            )

        batch = self.client.messages.batches.create(requests=batch_requests)
        return batch.id

    def get_job(self, batch_id: str) -> MessageBatch:
        """Retrieve the batch object, including its processing status.

        :param batch_id: The batch ID returned by ``execute_batch``.
        :return: The Anthropic ``MessageBatch`` object.
        """
        return self.client.messages.batches.retrieve(batch_id)

    def download_results(self, job: MessageBatch) -> str:
        """Download a finished batch's results as a JSONL string.

        Each line is the dict form of one result item, keyed by its
        ``custom_id``. The serialized string is suitable for archival on
        ``LLMRequest.batch_response_file``.

        :param job: A ``MessageBatch`` whose ``processing_status`` is
            ``ended``.
        :return: The results serialized as JSONL.
        :raises ValueError: If the batch has not ended.
        """
        if job.processing_status != BATCH_ENDED_STATUS:
            raise ValueError(
                f"Cannot download results for batch in state "
                f"'{job.processing_status}'. Expected "
                f"'{BATCH_ENDED_STATUS}'."
            )

        lines = [
            json.dumps(result.to_dict())
            for result in self.client.messages.batches.results(job.id)
        ]
        return "\n".join(lines)

    def process_results(self, jsonl_content: str) -> list[ProcessedResult]:
        """Parse a raw JSONL result string and validate each line item.

        :param jsonl_content: The JSONL content from a finished batch.
        :return: A list of structured dicts, one per task result,
            containing the key, status, content, and any error message.
        """
        if not jsonl_content or not jsonl_content.strip():
            return []

        results = [
            json.loads(line)
            for line in jsonl_content.splitlines()
            if line.strip()
        ]

        processed_results: list[ProcessedResult] = []
        for result in results:
            key = result.get("custom_id")
            text = _ResponseValidator.get_text(result)
            status = "SUCCEEDED" if text else "FAILED"
            processed_results.append(
                {
                    "key": key,
                    "status": status,
                    "content": text,
                    "error_message": (
                        None
                        if status == "SUCCEEDED"
                        else _ResponseValidator.get_error(result)
                    ),
                    "raw_result": result,
                }
            )
        return processed_results
