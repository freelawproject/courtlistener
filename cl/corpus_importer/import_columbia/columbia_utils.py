import re
from datetime import date
from typing import Any

import dateutil.parser as dparser
from juriscraper.lib.string_utils import clean_string

FILED_TAGS = [
    "filed",
    "opinion filed",
    "date",
    "order filed",
    "delivered and filed",
    "letter filed",
    "dated",
    "release date",
    "filing date",
    "filed date",
    "date submitted",
    "as of",
    "opinions filed",
    "filed on",
    "decision filed",
    "date delivered",
    "affirmed and opinion filed",
    "dismissed and opinion filed",
    "decided and entered",
]
DECIDED_TAGS = ["decided", "date decided", "decided on", "decided date"]
ARGUED_TAGS = [
    "argued",
    "submitted",
    "submitted on briefs",
    "on briefs",
    "heard",
    "considered on briefs",
    "argued and submitted",
    "opinion",
    "opinions delivered",
    "opinion delivered",
    "assigned on briefs",
    "assigned on brief",
    "opinion issued",
    "delivered",
    "rendered",
    "considered on briefs on",
    "opinion delivered and filed",
    "orally argued",
    "rendered on",
    "oral argument",
    "submitted on record and briefs",
    "argued on",
    "on reargument",
]
REARGUE_DENIED_TAGS = [
    "reargument denied",
    "rehearing denied",
    "further rehearing denied",
    "as modified on denial of rehearing",
    "order denying rehearing",
    "petition for rehearing filed",
    "motion for rehearing filed",
    "rehearing denied to bar commission",
    "reconsideration denied",
    "denied",
    "review denied",
    "motion for rehearing and/or transfer to supreme court denied",
    "motion for reargument denied",
    "petition and crosspetition for review denied",
    "opinion modified and as modified rehearing denied",
    "motion for rehearing andor transfer to supreme court denied",
    "petition for rehearing denied",
    "leave to appeal denied",
    "rehearings denied",
    "motion for rehearing denied",
    "second rehearing denied",
    "petition for review denied",
    "appeal dismissed",
    "rehearing en banc denied",
    "rehearing and rehearing en banc denied",
    "order denying petition for rehearing",
    "all petitions for review denied",
    "petition for allowance of appeal denied",
    "opinion modified and rehearing denied",
    "as amended on denial of rehearing",
    "reh denied",
    "opinion dissenting from denial of rehearing",
]
REARGUE_TAGS = ["reargued", "reheard", "upon rehearing", "on rehearing"]
CERT_GRANTED_TAGS = [
    "certiorari granted",
    "petition and crosspetition for writ of certiorari granted",
]
CERT_DENIED_TAGS = [
    "certiorari denied",
    "certiorari quashed",
    "certiorari denied by supreme court",
    "petition for certiorari denied by supreme court",
]
UNKNOWN_TAGS = [
    "petition for review allowed",
    "affirmed",
    "reversed and remanded",
    "rehearing overruled",
    "motion for rehearing overruled" "review granted",
    "decision released",
    "transfer denied",
    "released for publication",
    "application to transfer denied",
    "amended",
    "reversed",
    "opinion on petition to rehear",
    "suggestion of error overruled",
    "cv",
    "case stored in record room",
    "met to file petition for review disposed granted",
    "rehearing granted",
    "opinion released",
    "permission to appeal denied by supreme court",
    "rehearing pending",
    "on motion for rehearing",
    "application for transfer denied",
    "effective date",
    "modified",
    "opinion modified",
    "transfer granted",
    "discretionary review denied",
    "discretionary review refused",
    "application for leave to file second petition for rehearing denied",
    "final",
    "date of judgment entry on appeal",
    "petition for review pending",
    "writ denied",
    "rehearing filed",
    "as extended",
    "officially released",
    "appendix filed",
    "spring sessions",
    "summer sessions",
    "fall sessions",
    "winter sessions",
    "discretionary review denied by supreme court",
    "dissenting opinion",
    "en banc reconsideration denied",
    "answer returned",
    "refiled",
    "revised",
    "modified upon denial of rehearing",
    "session mailed",
    "reversed and remanded with instructions",
    "writ granted",
    "date of judgment entry",
    "preliminary ruling rendered",
    "amended on",
    "dissenting opinion filed",
    "concurring opinion filed",
    "memorandum dated",
    "mandamus denied on mandate",
    "updated",
    "date of judgment entered",
    "released and journalized",
    "submitted on",
    "case assigned",
    "opinion circulated for comment",
    "submitted on rehearing",
    "united states supreme court dismissed appeal",
    "answered",
    "reconsideration granted in part and as amended",
    "as amended on denial of rehearing",
    "reassigned",
    "as amended",
    "as corrected",
    "writ allowed",
    "released",
    "application for leave to appeal filed",
    "affirmed on appeal reversed and remanded",
    "as corrected",
    "withdrawn substituted and refiled",
    "answered",
    "released",
    "as modified and ordered published",
    "remanded",
    "concurring opinion added",
    "decision and journal entry dated",
    "memorandum filed",
    "as modified",
    "application for permission to appeal denied by supreme court",
    "rehearing and clarification denied",
    "reversed and remanded for reconsideration",
    "opinion granting rehearing in part",
]


def convert_columbia_html(text: str, opinion_index: int) -> str:
    """Convert xml tags to html tags and process additional data from opinions
    like footnotes,
    :param text: Text to convert to html
    :param opinion_index: opinion index from a list of all opinions
    :return: converted text
    """
    conversions = [
        ("italic", "em"),
        ("block_quote", "blockquote"),
        ("bold", "strong"),
        ("underline", "u"),
        ("strikethrough", "strike"),
        ("superscript", "sup"),
        ("subscript", "sub"),
        ("heading", "h3"),
        ("table", "pre"),
    ]

    for pattern, replacement in conversions:
        text = re.sub(f"<{pattern}>", f"<{replacement}>", text)
        text = re.sub(f"</{pattern}>", f"</{replacement}>", text)

        # grayed-out page numbers
        text = re.sub(
            "<page_number>", ' <span class="star-pagination">*', text
        )
        text = re.sub("</page_number>", "</span> ", text)

        # footnotes
        foot_references = re.findall(
            "<footnote_reference>.*?</footnote_reference>", text
        )

        # We use opinion index to ensure that all footnotes are linked to the
        # corresponding opinion
        for ref in foot_references:
            if (match := re.search(r"[\*\d]+", ref)) is not None:
                f_num = match.group()
            elif (match := re.search(r"\[fn(.+)\]", ref)) is not None:
                f_num = match.group(1)
            else:
                f_num = None
            if f_num:
                rep = f'<sup id="op{opinion_index}-ref-fn{f_num}"><a href="#op{opinion_index}-fn{f_num}">{f_num}</a></sup>'
                text = text.replace(ref, rep)

        # Add footnotes to opinion
        footnotes = re.findall(
            "<footnote_body>.[\s\S]*?</footnote_body>", text
        )
        for fn in footnotes:
            content = re.search(
                "<footnote_body>(.[\s\S]*?)</footnote_body>", fn
            )
            if content:
                rep = r'<div class="footnote">%s</div>' % content.group(1)
                text = text.replace(fn, rep)

        # Replace footnote numbers
        foot_numbers = re.findall(
            "<footnote_number>.*?</footnote_number>", text
        )
        for ref in foot_numbers:
            if (match := re.search(r"[\*\d]+", ref)) is not None:
                f_num = match.group()
            elif (match := re.search(r"\[fn(.+)\]", ref)) is not None:
                f_num = match.group(1)
            else:
                f_num = None
            if f_num:
                rep = (
                    rf'<sup id="op{opinion_index}-fn%s"><a href="#op{opinion_index}-ref-fn%s">%s</a></sup>'
                    % (
                        f_num,
                        f_num,
                        f_num,
                    )
                )
                text = text.replace(ref, rep)

    # Make nice paragraphs. This replaces double newlines with paragraphs, then
    # nests paragraphs inside blockquotes, rather than vice versa. The former
    # looks good. The latter is bad.
    text = f"<p>{text}</p>"
    text = re.sub(r"</blockquote>\s*<blockquote>", "\n\n", text)
    text = re.sub("\n\n", "</p>\n<p>", text)
    text = re.sub("\n  ", "</p>\n<p>", text)
    text = re.sub(r"<p>\s*<blockquote>", "<blockquote><p>", text, re.M)
    text = re.sub("</blockquote></p>", "</p></blockquote>", text, re.M)

    return text


def parse_dates(
    raw_dates: list[str],
) -> list[list[tuple[Any, date] | tuple[None, date]]]:
    """Parses the dates from a list of string.
    Returns a list of lists of (string, datetime) tuples if there is a string
    before the date (or None).
    :param raw_dates: A list of (probably) date-containing strings
    """
    months = re.compile(
        "january|february|march|april|may|june|july|august|"
        "september|october|november|december"
    )
    dates = []
    for raw_date in raw_dates:
        # there can be multiple years in a string, so we split on possible
        # indicators
        raw_parts = re.split(r"(?<=[0-9][0-9][0-9][0-9])(\s|.)", raw_date)

        # index over split line and add dates
        inner_dates = []
        for raw_part in raw_parts:
            # consider any string without either a month or year not a date
            no_month = False
            if re.search(months, raw_part.lower()) is None:
                no_month = True
                if re.search("[0-9][0-9][0-9][0-9]", raw_part) is None:
                    continue
            # strip parenthesis from the raw string (this messes with the date
            # parser)
            raw_part = raw_part.replace("(", "").replace(")", "")
            # try to grab a date from the string using an intelligent library
            try:
                d = dparser.parse(raw_part, fuzzy=True).date()
            except:
                continue

            # split on either the month or the first number (e.g. for a
            # 1/1/2016 date) to get the text before it
            if no_month:
                text = re.compile(r"(\d+)").split(raw_part.lower())[0].strip()
            else:
                text = months.split(raw_part.lower())[0].strip()
            # remove footnotes and non-alphanumeric characters
            text = re.sub(r"(\[fn.?\])", "", text)
            text = re.sub(r"[^A-Za-z ]", "", text).strip()
            # if we ended up getting some text, add it, else ignore it
            if text:
                inner_dates.append((clean_string(text), d))
            else:
                inner_dates.append((None, d))
        dates.append(inner_dates)

    return dates
