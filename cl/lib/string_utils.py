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
        else:
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

# CP1252 leaves five of the 32 C1 bytes undefined, so there is no character to
# recover for them: they can only ever be *detected*, never repaired.
_CP1252_UNDEFINED_C1_CODEPOINTS = frozenset({0x81, 0x8D, 0x8F, 0x90, 0x9D})

# C1 control character -> the CP1252 character the original byte stood for.
# Derived from the codec itself so the table can never drift from CP1252.
_CP1252_REPAIR_TABLE = {
    cp: bytes([cp]).decode("cp1252")
    for cp in range(0x80, 0xA0)
    if cp not in _CP1252_UNDEFINED_C1_CODEPOINTS
}

# Markers that flag a row as probably corrupted but cannot be repaired from
# the stored text alone: the undefined C1 bytes above, plus U+FFFD, which is
# above U+00FF and so is not even representable as a latin-1 byte.
_CP1252_UNREPAIRABLE_MARKERS = _CP1252_UNDEFINED_C1_CODEPOINTS | {0xFFFD}

_CP1252_CORRUPTION_CODEPOINTS = (
    frozenset(_CP1252_REPAIR_TABLE) | _CP1252_UNREPAIRABLE_MARKERS
)

# The same set as single-character strings. Passing a str to
# ``frozenset.isdisjoint`` iterates *characters*, not code points, so the
# predicate has to compare against characters; comparing code points here
# would silently never match and the detector would never fire.
_CP1252_CORRUPTION_CHARS = frozenset(map(chr, _CP1252_CORRUPTION_CODEPOINTS))


def looks_like_lawbox_cp1252_corruption(s: str) -> bool:
    """Heuristically detect CP1252 mojibake of the kind described in issue #410.

    The Lawbox importer (removed in commit 805877a36) decoded the corpus's
    HTML files under the files' self-declared ``ISO-8859-1`` charset. Bytes in
    the ``0x80-0x9F`` range are actually CP1252 code points (em-dash ``0x97``,
    ellipsis ``0x85``, Euro ``0x80``, smart quotes, etc.), so they were either
    mapped to the C1 control characters (U+0080-U+009F) or to the replacement
    character (U+FFFD). This predicate reports whether ``s`` contains any of
    those markers.

    A ``True`` result covers both the repairable markers (the C1 characters
    CP1252 defines) and the unrepairable ones (U+FFFD and the five C1 bytes
    CP1252 leaves undefined). Use :func:`repair_lawbox_cp1252` to tell them
    apart.

    A ``True`` result is a strong *signal* of corruption, not a proof; combine
    with :func:`repair_lawbox_cp1252` (which is itself safe-by-construction)
    before mutating stored data.

    :param s: The string to inspect.
    :return: ``True`` if any likely-corruption codepoint is present.
    """
    if not isinstance(s, str):
        return False
    # ``isdisjoint`` iterates and compares in C and stops at the first hit, so
    # this stays cheap even on multi-megabyte ``html_lawbox`` values.
    return not _CP1252_CORRUPTION_CHARS.isdisjoint(s)


def repair_lawbox_cp1252(s: str) -> str:
    """Repair CP1252-mis-decoded text of the kind described in issue #410.

    The remembered original bytes are gone (the importer is deleted and the DB
    stores the decoded text), so we apply the inverse of the wrong decode:
    every C1 control character is replaced by the character CP1252 assigns to
    the corresponding byte (``0x97`` -> em-dash, ``0x85`` -> ellipsis,
    ``0x80`` -> Euro sign, ``0x93``/``0x94`` -> curly quotes, and so on).

    The repair is a ``str.translate`` over the C1 block only, which makes it
    safe by construction: no other character is touched, so a genuine
    high-codepoint character sitting next to a corruption marker survives
    instead of being destroyed. Worked examples, where ``U+0097`` is the
    em-dash byte ``0x97`` that the importer stored as a C1 control character:

    * ``"the MHL U+0097 and the discretion U+2014 as held"`` repairs the
      ``U+0097`` and leaves the genuine em-dash ``U+2014`` alone.
    * ``"smart U+201CquotesU+201D U+0097"`` keeps the curly quotes.
    * ``"café U+0097"`` repairs the marker; ``U+00E9`` is below ``U+00FF`` and
      so was never at risk of being dropped.
    * A run of CJK (``U+6CD5 U+9662``) next to a marker is left intact.

    Two markers can be detected but never repaired, because the original byte
    is unrecoverable from the stored text: the five C1 bytes CP1252 leaves
    undefined (``0x81``, ``0x8D``, ``0x8F``, ``0x90``, ``0x9D``), and
    ``U+FFFD``, which points at an earlier decode having dropped the byte
    rather than the Lawbox importer having mis-decoded it. Rows carrying only
    those markers are returned unchanged, and the caller (e.g. the
    ``repair_lawbox_encoding`` management command) should report them for
    manual review instead of silently counting them as clean.

    The repair is idempotent: every character the table produces is above
    U+00FF, so a second pass finds no markers.

    :param s: The possibly-corrupted string.
    :return: The repaired string, or the original if nothing was recoverable.
    """
    if not isinstance(s, str) or not s:
        return s
    # Cheap pre-filter. This is not merely an optimisation: ``str.translate``
    # only has an in-place fast path for UCS1 strings, so skipping it on rows
    # that carry no marker keeps a clean row several times cheaper to scan.
    if not looks_like_lawbox_cp1252_corruption(s):
        return s

    repaired = s.translate(_CP1252_REPAIR_TABLE)
    if repaired == s:
        # Every marker was one of the unrepairable ones. Return the input
        # object itself rather than a fresh copy.
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
