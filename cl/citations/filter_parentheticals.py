import re

_MODIFIABLE = r"(omissions?|quotations?|quotes?|headings?|(quotations? )?marks|ellips.s|cites?|citations?|emphas.s|italics?|footnotes?|alterations?|punctuation|modifications?|brackets?|bracketed material|formatting)"
_MODIFABLE_TYPE = r"(internal|former|latter|first|second|third|fourth|fifth|last|some|further|certain|numbered|other|transcript)"
_FULL_MODIFIABLE = f"(({_MODIFABLE_TYPE} )?{_MODIFIABLE})"
_QUOTE_MODIFICATION = r"(added|provided|removed|adopted|(in )?(the )original|omitted|included|deleted|eliminated|altered|modified|supplied|ours|mine|changed|(in|by) \S+|by \S+ court)"
_DOCUMENT_TYPES = r"(opinion|continuance|order|op\.|decision|case|disposition|authority|authoritie|statement)"
_OPINION_TYPES = r"(separate|supplemental|amended|majority|dissent|dissenting|concurrence|concurring|plurality|unpublished|revised|per curi.m|in.chambers|judgment|joint|principal|panel|unanimous|5-4|statement)"
_OPINION_TYPE_MODIFICATION = r"(in (the )?(judgment|result)s?( in part)?|in result|in part|dubitante|in relevant part|(from|with|respecting) .{1,50})"  # TIL: https://en.wikipedia.org/wiki/Dubitante
_FULL_OPINION_DESCRIPTOR = (
    f"({_OPINION_TYPES}( {_OPINION_TYPE_MODIFICATION})?)"
)
_REFERENTIAL = r"(quoting|citing|cited in|referencing|adopted)"
_AGGREGATOR_TYPES = r"(collecting|reviewing|listing)"
_HONORIFICS = r"(Mr.?|Mister)"
_JUDGE_NAME = rf"((.{{1,25}}J\.,?)|({_HONORIFICS} Justice .{{1,25}})|the Court|(.{{1,25}}Circuit Justice),?)"
_TOO_SHORT = r"(\S+\s){0,3}\S*"

PARENTHETICAL_REGEX_BLOCKLIST_RULES = [
    r".n banc",  # en banc or in banc
    # Scalia, J., dissenting; Roberts, C.J., concurring in the judgment, concurring in part, and dissenting in part
    f"{_JUDGE_NAME}( {_FULL_OPINION_DESCRIPTOR})?([ ,]+(and )?{_FULL_OPINION_DESCRIPTOR})*",
    f"{_JUDGE_NAME}.{{1,75}}",
    # concurring in result
    f"({_DOCUMENT_TYPES} )?{_FULL_OPINION_DESCRIPTOR}",
    # opinion of Breyer, J.; opinion of Scalia and Alito, J.J.
    f"{_DOCUMENT_TYPES} of {_JUDGE_NAME}",
    # plurality opinion, supplemental order
    f"{_OPINION_TYPES}( {_DOCUMENT_TYPES})?( {_OPINION_TYPE_MODIFICATION})?",
    rf"({_DOCUMENT_TYPES} )?opinion.*",
    r"dictum|dicta",
    r"on rehearing|denying cert(iorari)?",
    r"simplified|cleaned up|as amended",
    r"same|similar|contra",
    r"standard of review",
    r"(and )?cases cited therein",
    # No. 12-345
    r"No. \d+.?\d+",
    # n. 6
    r"n. \d+",
    # case below
    f"{_DOCUMENT_TYPES} below",
    # collecting cases, reviewing cases
    f"{_AGGREGATOR_TYPES} {_DOCUMENT_TYPES}s?",
    f"({_OPINION_TYPES} )?table( {_DOCUMENT_TYPES})?",
    # internal citations omitted
    f"{_FULL_MODIFIABLE} {_QUOTE_MODIFICATION}",
    f"{_FULL_MODIFIABLE} and {_FULL_MODIFIABLE} {_QUOTE_MODIFICATION}",
    f"{_FULL_MODIFIABLE} {_QUOTE_MODIFICATION}[;,] ?{_FULL_MODIFIABLE} {_QUOTE_MODIFICATION}",
    f"({_MODIFABLE_TYPE} )?{_MODIFIABLE}, {_MODIFIABLE}, and {_MODIFIABLE} {_QUOTE_MODIFICATION}",
    # Match any short parenthetical that looks like a modification (e.g. "citations and internal marks omitted, emphasis added")
    rf"(?=.*{_MODIFIABLE}.*).{{1,75}}",
    # citing Gonzales v. Raich, 123 U.S. 456 (2019). A tad over-inclusive but very helpful
    f"{_REFERENTIAL} .*",
    # 2nd Cir. 2019, Third Circuit 1993
    r".{1,20} \d{4}",
    # Gonzales II
    r".{1,25} I+",
    # Tenth Circuit, 5th Cir.
    r".{1,10} (Circuit|Cir.)",
    # hereinafter, "Griffin II"
    r"here(in)?after(,)? .+",
    # Imbalanced parentheses (for when eyecite cuts off the parenthetical too soon) e.g. "holding Section 4(a"
    r"^.{1,35}\([^\)]{1,35}$",
    _TOO_SHORT,
]

_SURROUNDING_CHARS = r'[.!;,"“” ]'
_PREFIX = rf"^{_SURROUNDING_CHARS}*("  # Begin string, optional whitespace/puncutation, begin capture group
_SUFFIX = rf"){_SURROUNDING_CHARS}*$"  # Close capture group, optional whitespace/punctuation, end string

PARENTHETICAL_BLOCKLIST_REGEX = re.compile(
    _PREFIX
    + r"|".join(  # Wrap each rule in its own group
        map(lambda reg: f"({reg})", PARENTHETICAL_REGEX_BLOCKLIST_RULES)
    )
    + _SUFFIX,
    re.IGNORECASE,
)


def is_parenthetical_descriptive(text: str) -> bool:
    text = clean_parenthetical_text(text)
    return not re.match(PARENTHETICAL_BLOCKLIST_REGEX, text)


def clean_parenthetical_text(text: str) -> str:
    # Remove star page numbers (e.g. *389)
    text = re.sub(r"\* ?\d+", " ", text)
    # Remove weird "word ----- word" stuff (but don't screw up something like "123 U.S. ---")
    text = re.sub(r" [_-]{4,} ", " ", text)
    # Remove excess whitespace that may have appeared as a result of sequential dash sequences
    text = re.sub(r"\s+", " ", text)
    return text
