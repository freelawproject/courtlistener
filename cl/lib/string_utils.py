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
        rf"[{normal_dash}{en_dash}{em_dash}{hyphen}{non_breaking_hyphen}{figure_dash}{horizontal_bar}]+",
        normal_dash,
        text,
    )


# Characters that strongly indicate the latin-1/CP1252 mojibake described in
# GitHub issue #410. The C1 control block (U+0080-U+009F) is undefined in
# ISO-8859-1 and essentially never appears as intentional content in legal
# text; the replacement character (U+FFFD) is what lxml inserts when it
# cannot map a byte at all. See:
#   https://github.com/freelawproject/courtlistener/issues/410
_CP1252_CORRUPTION_CODEPOINTS = (
    set(range(0x80, 0xA0))  # C1 control block, undefined in ISO-8859-1
    | {0xFFFD}  # REPLACEMENT CHARACTER
)


def looks_like_lawbox_cp1252_corruption(s: str) -> bool:
    """Heuristically detect CP1252 mojibake of the kind described in issue #410.

    The Lawbox importer (removed in commit 805877a36) decoded the corpus's
    HTML files under the files' self-declared ``ISO-8859-1`` charset. Bytes in
    the ``0x80-0x9F`` range are actually CP1252 code points (em-dash ``0x97``,
    ellipsis ``0x85``, Euro ``0x80``, smart quotes, etc.), so they were either
    mapped to the C1 control characters (U+0080-U+009F) or to the replacement
    character (U+FFFD). This predicate reports whether ``s`` contains any of
    those markers.

    A ``True`` result is a strong *signal* of corruption, not a proof; combine
    with :func:`repair_lawbox_cp1252` (which is itself safe-by-construction)
    before mutating stored data.

    :param s: The string to inspect.
    :return: ``True`` if any likely-corruption codepoint is present.
    """
    if not isinstance(s, str):
        return False
    return any(ord(ch) in _CP1252_CORRUPTION_CODEPOINTS for ch in s)


def repair_lawbox_cp1252(s: str) -> str:
    """Repair CP1252-mis-decoded text of the kind described in issue #410.

    The repair is only attempted when
    :func:`looks_like_lawbox_cp1252_corruption` flags ``s``. The remembered
    original bytes are gone (the importer is deleted and the DB stores the
    decoded text), so we attempt the inverse of the wrong decode: encode the
    text back to latin-1 bytes and re-decode those bytes as CP1252. This is
    the standard idiom for this class of mojibake and is length-preserving.

    The round-trip is **only safe** when ``s`` contains no codepoint above
    U+00FF that is *not* itself a corruption marker: a genuine high-codepoint
    character (for example a correctly-encoded em-dash U+2014, a smart quote,
    or any non-Latin character) would be destroyed by ``encode("latin-1")``.
    When such characters are present alongside the corruption markers, the
    string is a mixed-content document and we leave it **unchanged** rather
    than risk silent data loss. The caller (e.g. the
    ``repair_lawbox_encoding`` management command) should log these skipped
    rows for manual review.

    When the round-trip raises ``UnicodeEncodeError`` (mixed content with
    high codepoints) the input is returned unchanged. When the round-trip
    succeeds but yields a string identical to the input, the input is
    returned unchanged (idempotent / no-op).

    :param s: The possibly-corrupted string.
    :return: The repaired string, or the original if it is not safe to repair
        (no corruption detected, mixed-content, or a round-trip no-op).
    """
    if not isinstance(s, str) or not s:
        return s
    if not looks_like_lawbox_cp1252_corruption(s):
        return s

    # Reject mixed content: any codepoint above U+00FF that is NOT itself one
    # of the corruption markers would be lost by the latin-1 encode below.
    for ch in s:
        cp = ord(ch)
        if cp > 0xFF and cp not in _CP1252_CORRUPTION_CODEPOINTS:
            return s

    try:
        repaired = s.encode("latin-1").decode("cp1252")
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Defensive: should not happen given the checks above, but never
        # silently mangle data.
        return s

    if repaired == s:
        # The round-trip did nothing (e.g. the corruption markers were
        # already correct under both codecs). Don't return a fresh object.
        return s
    return repaired


def repair_lawbox_content_if_needed(s: str) -> tuple[str, bool]:
    """Convenience wrapper for :func:`repair_lawbox_cp1252`.

    :param s: The possibly-corrupted string.
    :return: A ``(repaired, changed)`` tuple where ``changed`` is True iff the
        returned string differs from the input.
    """
    repaired = repair_lawbox_cp1252(s)
    return repaired, repaired != s


def get_token_count_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(string))
    return num_tokens
