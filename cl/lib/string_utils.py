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


def filter_invalid_XML_chars(input: str) -> str:
    """XML allows:

       Char ::= #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]

    This strips out everything else.

    See: https://stackoverflow.com/a/25920392/64911
    """
    if isinstance(input, str):
        # Only do str, unicode, etc.
        return re.sub(
            "[^\u0020-\ud7ff\u0009\u000a\u000d\ue000-\ufffd"
            "\U00010000-\U0010ffff]+",
            "",
            input,
        )
    else:
        return input


def removeLeftMargin(s: str) -> str:
    """Gets rid of left hand margin.

    Given a block of text, calculates the mode of the number of spaces before
    text in the doc, and then removes that number of spaces from the text. This
    should not be used in the general case, but can be used in cases where a
    left-hand margin is known to exist.
    """
    lines = s.split("\n")
    marginSizes = []
    for line in lines:
        if len(line) > 0:
            if line[0] == " ":
                # if the line has length and starts with a space
                newlength = len(line.lstrip())
                oldlength = len(line)
                diff = oldlength - newlength
                if diff != 0:
                    marginSizes.append(oldlength - newlength)

    mode = max([marginSizes.count(y), y] for y in marginSizes)[1]
    lines_out = []
    for line in lines:
        numLSpaces = len(line) - len(line.lstrip())
        if numLSpaces < mode:
            # Strip only that number of spaces
            line_out = line[numLSpaces:]
        elif numLSpaces >= mode:
            # Strip off the mode number of spaces
            line_out = line[mode:]

        lines_out.append(line_out)

    return "\n".join(lines_out)


def removeDuplicateLines(s: str) -> str:
    """Remove duplicate lines next to each other."""
    lines = s.split("\n")
    lines_out = []
    previous_line = ""
    for line in lines:
        if line != previous_line:
            lines_out.append(line)
            previous_line = line

    return "\n".join(lines_out)


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
        rf"[{en_dash}{em_dash}{hyphen}{non_breaking_hyphen}{figure_dash}{horizontal_bar}]",
        normal_dash,
        text,
    )


def get_token_count_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(string))
    return num_tokens
