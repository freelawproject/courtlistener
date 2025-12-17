from typing import IO, Any

import instructor
from openai import OpenAI
from pydantic import BaseModel


def call_llm(
    system_prompt: str,
    user_prompt: str | list[str] | list[dict],
    model: str = "openai/gpt-4o-mini",
    response_model: type[BaseModel] | None = None,
    api_key: str | None = None,
    **kwargs,
) -> tuple[BaseModel | dict | str, Any]:
    """Call an LLM via Instructor to get structured or raw output

    You must set any of these environment variables for some providers:
    OPENAI_API_KEY, ANTHROPIC_API_KEY or MISTRAL_API_KEY

    :param system_prompt: Instructions as system prompt for the LLM
    :param user_prompt: Task-specific prompt content, it may be: a single string, a list of strings, a list of prebuilt
    content parts like {"type": "text", "text": "..."}
    :param model: Instructor provider/model identifier (e.g., "openai/gpt-4o-mini")
    :param response_model: Optional Pydantic model to validate and return typed output
    :param api_key: Optional explicit API key for the provider
    :param kwargs: Extra generation parameters (e.g., temperature, max_tokens, etc)
    :return: Parsed Pydantic model instance if response_model is set, else raw dict or string and raw completion response
    """

    # if api_key is provided, inject it, else fallback to env var
    client = instructor.from_provider(model, api_key=api_key)

    def to_content_part(x: str | dict) -> dict:
        if isinstance(x, str):
            return {"type": "text", "text": x}
        # Assume already a valid content part dict, e.g. {"type": "text", "text": "..."}
        return x

    if isinstance(user_prompt, str):
        user_content = [to_content_part(user_prompt)]
    else:
        user_content = [to_content_part(p) for p in user_prompt]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    # Default params
    kwargs.setdefault("temperature", 0.0)
    kwargs.setdefault("max_tokens", 1000)

    response, raw_response = client.chat.completions.create_with_completion(
        messages=messages, response_model=response_model, **kwargs
    )
    return response, raw_response


def call_llm_transcription(
    audio: tuple[str, IO[bytes]],
    api_key: str,
    model: str = "gpt-4o-transcribe",
) -> str:
    """Call an LLM transcription service with a given base64 encoded audio file.

    The OPENAI_API_KEY environment variable must be set.

    Currently only supports OpenAI transcription models, but may be extended to support other options in the future.

    :param audio: Audio file to transcribe, as a binary IO stream.
    :param api_key: OpenAI transcription API key
    :param model: The OpenAI transcription model to use.
    :return: The transcription text."""
    client = OpenAI(api_key=api_key)

    return client.audio.transcriptions.create(
        model=model, file=audio, response_format="text"
    )
