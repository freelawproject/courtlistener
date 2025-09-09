import json

from openai import OpenAI

# Cache for loaded prompts
_PROMPT_CACHE = {}


def load_prompt_cached(prompt_path: str) -> str:
    """Load prompt template text from a .txt file and cache in memory to avoid repeated I/O

    :param prompt_path: File path to prompt template (.txt file)
    :return: Prompt template string
    """
    if prompt_path not in _PROMPT_CACHE:
        with open(prompt_path, encoding="utf-8") as f:
            _PROMPT_CACHE[prompt_path] = f.read()
    return _PROMPT_CACHE[prompt_path]


def parse_llm_json(s: str) -> dict | None:
    """
    Parse JSON string returned by LLM, handling common formatting issues

    - Removes markdown code blocks (``````json).
    - Strips whitespace.
    - Only catches JSON decoding errors, not all exceptions.

    :param s: JSON string, possibly wrapped with markdown code blocks.
    :return: Parsed dictionary or None if parsing fails.
    """
    s_clean = s.replace("``````", "").replace("``````", "").strip()
    try:
        return json.loads(s_clean)
    except json.JSONDecodeError:
        return None


def call_llm(
    system_prompt: str, prompt: str, user_text: str, model: str = "gpt-4o-mini"
) -> str:
    """Generic function to call the OpenAI LLM with provided system prompt and user message

    :param system_prompt: System prompt string (instructions for the LLM's behavior)
    :param prompt: Detailed task prompt describing what to do
    :param user_text: The main input data (e.g., 1st page of opinion + docket title)
    :param model: Model name
    :return: Raw response content (string)
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "text", "text": user_text},
            ],
        },
    ]
    # Use retries from the calling celery task
    with OpenAI(max_retries=0) as client:
        resp = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=messages,
        )
    return resp.choices[0].message.content
