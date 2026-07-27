import re

import tiktoken


def camel_to_snake(key: str) -> str:
    """Converts a camelCase string to snake_case.

    :param key: The camelCase string to convert.
    :return: The snake_case version of the input string.
    """
    return re.sub(r"([a-z])([A-Z])", r"\1_\2", key).lower()


def trunc(s: str, length: int, ellipsis: str | None = None) -> str:
    """Truncates a string at a good length.

    Finds the rightmost space in a string, and truncates there. Lacking such
    a space, truncates at length.

    If an ellipsis is provided, the right most space is used that allows the
    addition of the ellipsis without being longer than length.
    """
    if ellipsis:
        ellipsis_length = len(ellipsis)
    else:
        ellipsis_length = 0

    if len(s) <= length:
        # Do not ellipsize if the item is not truncated.
        return s
    else:
        # find the rightmost space using a zero-indexed (+1) length minus the
        # length of the ellipsis.
        rightmost_space_index = length - ellipsis_length + 1
        end = s.rfind(" ", 0, rightmost_space_index)
        if end == -1:
            # no spaces found, just use max position
            end = length - ellipsis_length
        s = s[0:end]
        if ellipsis:
            s = f"{s}{ellipsis}"
        return s


def normalize_dashes(text: str) -> str:
    """Convert en & em dash(es) to hyphen(s)

    :param text: The text to convert
    :return: the better text
    """
    # Simple variables b/c in monospace code, you can't see the difference
    # otherwise.
    normal_dash = "-"
    en_dash = "–"
    em_dash = "—"
    hyphen = "‐"
    non_breaking_hyphen = "‑"
    figure_dash = "‒"
    horizontal_bar = "―"
    return re.sub(
        rf"[{normal_dash}{en_dash}{em_dash}{hyphen}{non_breaking_hyphen}{figure_dash}{horizontal_bar}]+",
        normal_dash,
        text,
    )


def get_token_count_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(string))
    return num_tokens
