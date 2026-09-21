import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
from django.core.management.base import CommandError
from django.db.models import Q
from django.utils import timezone

from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Citation, Opinion

# Courts damaged by the juriscraper DeferringList bug. DeferringList did not
# inherit from list, so AbstractSite._date_sort skipped it while reordering
# every other attribute. The deferred attribute kept page order and the files
# ended up on the wrong records.
DEFAULT_COURTS = ["tex", "nd", "ndctapp"]

# Bug window. The back scrapes that did the damage all ran inside it.
DEFAULT_CREATED_AFTER = "2013-01-01"
DEFAULT_CREATED_BEFORE = "2015-07-01"

# `_date_sort` was fixed in August 2014, so anything scraped well after that
# is undamaged and can be used to measure how often each source of evidence
# is right. See the --calibrate flag.
CALIBRATION_AFTER = "2015-01-01"

TAGS = re.compile(r"<[^>]+>")
# A Word export opens with tens of thousands of characters of CSS. It is
# not text and must not push the header past the cut.
# Bounded, so an unclosed <style> cannot swallow the document up to a
# later closing tag.
BLOCKS = re.compile(
    r"<(style|script)\b[^>]*>.{0,200000}?</\1\s*>", re.S | re.I
)
ENTITIES = re.compile(r"&[#a-zA-Z0-9]+;")
WHITESPACE = re.compile(r"\s+")
WORDS = re.compile(r"[A-Za-z]{5,}")

# The docket number sits in the document header; no need to scan the body.
HEADER_CHARS = 20000
# A stored file carries its full markup, and a Word export puts tens of
# thousands of characters of styles before the first word, so more raw
# markup is read before cutting the text down to HEADER_CHARS.
STORED_RAW_CHARS = 1000000

# North Dakota names the file after the case both ways it served them: the
# modern /wp/<docket>.wpd and the older /court/opinions/<docket>.htm.
ND_URL_DOCKET = re.compile(r"/(?:wp|court/opinions)/(\d+)\.(?:wpd|html?)")
# Headers print "No.", "NO.", "Nos." for consolidated cases, and sometimes
# letter-space it as "N o . 01-0774". One Texas header prints the number
# with an en dash, "No. 03–0831".
TEX_DOCKET = re.compile(r"N\s*[Oo]\s*[Ss]?\s*\.?\s*(\d{2}[-\u2013]\d{4})")
# Modern North Dakota numbers are 8 digits (20010162); pre-1998 ones are 6
# (960082) and the record spells them "Civil 960082".
ND_DOCKET = re.compile(r"N\s*[Oo]\s*[Ss]?\s*\.?\s*(?:Civil\s+)?(\d{6,8})")
NON_DIGITS = re.compile(r"\D")
EN_DASH = "\u2013"

# A record's docket field can carry several numbers: "20130119, 20130120",
# "Criminal 970326-970328", "20020064-20020065, 20020066-20020067". These
# read every number the field covers, so a file carrying any one of them
# is recognised as belonging to the record.
# Bounded, so "07-15-00090-CV" (a court of appeals number kept on some tex
# dockets) does not yield "15-0009".
ND_NUMBER = re.compile(r"(?<!\d)\d{6,8}(?!\d)")
TEX_NUMBER = re.compile(r"(?<![\d-])\d{2}[-\u2013]\d{4}(?![\d-])")
ND_RANGE = re.compile(r"(\d{6,8})\s*[-\u2013\u2014]\s*(\d{6,8})")
# Consolidated appeals run to a dozen or so numbers; anything wider is a typo.
MAX_RANGE = 50

BY_URL = "download_url"
BY_HTML = "html_header"
BY_TEXT = "plain_text_header"
# The file itself, read from storage. Used only when the html and
# plain_text columns yield nothing: for 18 of the 20 Texas records the
# audit could not read, the html column holds a truncated copy of a file
# that is complete in storage.
BY_FILE = "stored_file"

STORAGE_URL = "https://storage.courtlistener.com/"
FETCH_TIMEOUT = 30
# Nothing legitimate is this large; a bigger body is not read.
MAX_FETCH_BYTES = 20 * 1024 * 1024
PDFTOTEXT_TIMEOUT = 60
# A PDF that prints "CASE: 08-0725" or "Case Number: 11-0252" has no "No."
# to anchor on. The number is taken after such a label, and only this
# close to the top.
BARE_CHARS = 3000
TEX_LABELLED = re.compile(
    r"\bCase\b[^0-9]{0,20}?(\d{2}[-\u2013]\d{4})(?![\d-])", re.I
)

ALIGNED = "aligned"
MISATTACHED = "misattached"
UNDETERMINED = "undetermined"
CONFLICTED = "conflicted"

HIGH = "high"
MEDIUM = "medium"

BY_DOCKET = "docket_number"
BY_TEXT_MATCH = "text_match"
# Several in-run records carry the docket: they are different opinions of
# one case. The file's own filing date and neutral citation pick the one.
BY_FILING_DATE = "filing_date"

# Texas files end "OPINION DELIVERED: May 22, 2009". The header names the
# author: "Justice Medina delivered the opinion of the Court", "PER CURIAM",
# or, for a separate opinion, "Justice O'Neill, joined by ..., concurring".
BY_DELIVERED = "delivered_date"
DELIVERED = re.compile(
    r"OPINION\s+DELIVERED[:\s]+([A-Z][a-z]+)\.?\s+(\d{1,2}),\s+(\d{4})", re.I
)
MAJORITY_LINE = re.compile(
    r"delivered the opinion of the court|(?<!\()per curiam", re.I
)
SEPARATE_LINE = re.compile(r"\b(concurring|dissenting)\b", re.I)
MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        1,
    )
}
MAJORITY = "majority"
CONCURRENCE = "concurrence"
DISSENT = "dissent"
ORDER = "order"
# Opinion.type values each kind of file may land on.
KIND_TYPES = {
    MAJORITY: {"010combined", "015unamimous", "020lead", "025plurality"},
    CONCURRENCE: {"030concurrence"},
    DISSENT: {"040dissent"},
}
# A caption and author line fit in this many characters. A file with fewer
# words than ORDER_WORDS is treated as an order whatever its author line,
# because a per curiam abating rehearing looks like a per curiam opinion.
# Genuine short per curiam opinions are refused too, which is the safe side.
CAPTION_CHARS = 2500
ORDER_WORDS = 400

# North Dakota files open "Filed 12/13/11 by Clerk of Supreme Court" and
# cite themselves as "2011 ND 233" or "2011 ND App 5".
FILED_NUMERIC = re.compile(r"Filed\s+(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b")
NEUTRAL_CITE = re.compile(r"\b(\d{4})\s+(ND(?:\s+App)?)\s+(\d{1,4})\b")
# Both sit in the first 250 characters of every aligned file measured
# (p99 = 127). Reading further picks up a cited case instead.
ND_HEADER_CHARS = 300
# The sources read different numbers, but one record's consolidated docket
# covers all of them.
BY_COVERING = "covering_docket"
# The sources read different numbers, only one of which any record carries,
# and that record's case name is printed in the document.
BY_OWNED = "sole_owned_number"

# Shared word runs, used to pick between candidates that share a docket
# number. Containment rather than Jaccard, so a 250-word clerk letter
# stays comparable to a 9,000-word opinion.
SHINGLE = 5
# Scores are strongly bimodal: winners sit above 0.5, losers below 0.2.
# Both bars must be cleared, so a near-tie is left for a person.
MATCH_FLOOR = 0.5
MATCH_MARGIN = 0.2

# Case-name words too common to corroborate anything. Measured on the tex
# 2013-06-06 run: without the second group, 62 of 489 misattached records
# still "matched" their record's name, almost all on a word like "medical"
# or "services". With it, 39 do, and the aligned side is unchanged at 1 of
# 257. Requiring two matching words instead would cut the 39 to 3 but break
# the aligned side to 43, because many case names carry only one real name.
COMMON_WORDS = {
    "america",
    "american",
    "appeals",
    "association",
    "bank",
    "board",
    "center",
    "city",
    "commission",
    "company",
    "corporation",
    "county",
    "court",
    "dakota",
    "department",
    "district",
    "energy",
    "estate",
    "general",
    "group",
    "health",
    "hospital",
    "insurance",
    "interest",
    "limited",
    "matter",
    "medical",
    "mutual",
    "national",
    "north",
    "parte",
    "partner",
    "partners",
    "petition",
    "school",
    "service",
    "services",
    "state",
    "states",
    "supreme",
    "texas",
    "trust",
    "united",
    "university",
    "water",
}


@dataclass(frozen=True)
class CourtProfile:
    """How to read a docket number out of one court's documents.

    :param docket_re: pattern matching the number as the court prints it
    :param read_download_url: whether the file name carries the number, as
        North Dakota's /wp/<docket>.wpd does
    :param number_re: pattern matching one number inside the record's docket
        field, which can list several
    :param digits_only: compare on digits alone. North Dakota records spell
        older numbers "Civil 960082" while the file says "960082", so a
        literal comparison reports every one of them as a mismatch.
    :param bare_number_fallback: in a stored file with no "No." line, accept
        a number after a "Case" label near the top. Texas PDFs print
        "CASE:" or "Case Number:".
    :param filing_date_header: the file prints its filing date and neutral
        citation in the header, so they can separate two opinions of one
        case
    :param delivered_footer: the file ends with "OPINION DELIVERED: <date>",
        which separates a superseding opinion from the version it withdrew
    """

    docket_re: re.Pattern
    read_download_url: bool
    number_re: re.Pattern
    digits_only: bool = False
    bare_number_fallback: bool = False
    filing_date_header: bool = False
    delivered_footer: bool = False


# The 2013 back scraper pulled nd and ndctapp off one shared month page
# and split them by neutral citation, using the same misaligned lists. A
# file can therefore land in the sibling court, so resolution has to look
# at the pair rather than one court at a time.
COURT_GROUPS = {
    "nd": ("nd", "ndctapp"),
    "ndctapp": ("nd", "ndctapp"),
}

PROFILES = {
    "tex": CourtProfile(
        TEX_DOCKET,
        False,
        TEX_NUMBER,
        bare_number_fallback=True,
        delivered_footer=True,
    ),
    "nd": CourtProfile(
        ND_DOCKET, True, ND_NUMBER, digits_only=True, filing_date_header=True
    ),
    "ndctapp": CourtProfile(
        ND_DOCKET, True, ND_NUMBER, digits_only=True, filing_date_header=True
    ),
}


def docket_key(value: str | None, profile: CourtProfile) -> str | None:
    """Reduce a single docket number to the form used for comparison."""
    if not value:
        return None
    return NON_DIGITS.sub("", value) if profile.digits_only else value


def docket_numbers(value: str | None, profile: CourtProfile) -> set[str]:
    """Every docket number a record's docket field covers, as comparison keys.

    Consolidated cases list several numbers, sometimes as a range. Reducing
    the whole field to digits fuses them into one long string that no file
    can match, which reported every such record as misattached and hid its
    owner from the destination lookup.
    """
    if not value:
        return set()
    numbers = {
        n.replace(EN_DASH, "-") for n in profile.number_re.findall(value)
    }
    if profile.digits_only:
        for start, end in ND_RANGE.findall(value):
            span = int(end) - int(start)
            if len(start) == len(end) and 0 < span <= MAX_RANGE:
                numbers.update(
                    str(n).zfill(len(start))
                    for n in range(int(start), int(end) + 1)
                )
    if numbers:
        return numbers
    # A field the pattern cannot read falls back to the single-number key.
    key = docket_key(value, profile)
    return {key} if key else set()


def normalize_markup(value: str | None, raw_chars: int = HEADER_CHARS) -> str:
    """Flatten markup so a docket number in the header can be matched.

    Tags and HTML entities sit between "No." and the number often enough that
    matching raw HTML under-reports the damage by about 17%.

    :param value: raw markup
    :param raw_chars: how much raw markup to read before flattening
    :return: normalised text, cut to HEADER_CHARS
    """
    if not value:
        return ""
    text = BLOCKS.sub(" ", value[:raw_chars])
    text = TAGS.sub(" ", text)
    text = ENTITIES.sub(" ", text)
    return WHITESPACE.sub(" ", text)[:HEADER_CHARS]


def normalize_text(value: str | None) -> str:
    """Collapse whitespace in already-plain text."""
    if not value:
        return ""
    return WHITESPACE.sub(" ", value[:HEADER_CHARS])


def docket_from_url(download_url: str | None) -> str | None:
    """Read the docket number out of an ndcourts.gov file name.

    North Dakota serves each opinion as /wp/<docket number>.wpd, so the URL
    names the case the file belongs to.
    """
    if not download_url:
        return None
    match = ND_URL_DOCKET.search(download_url)
    return match.group(1) if match else None


def docket_from_body(body: str, pattern: re.Pattern) -> str | None:
    """Read the first docket number printed in a normalised document body.

    Caveat: this takes the first match. In documents that reproduce a lower
    court record or bundle companion cases, the first number is not always the
    document's own, which is why no single source is trusted alone.
    """
    if not body:
        return None
    match = pattern.search(body)
    return match.group(1).replace(EN_DASH, "-") if match else None


def pdf_text(content: bytes) -> str:
    """Text of a PDF, through pdftotext, or "" when it is not installed."""
    if not shutil.which("pdftotext"):
        logger.warning("pdftotext is not installed; PDF files are not read")
        return ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
            handle.write(content)
            handle.flush()
            result = subprocess.run(
                ["pdftotext", "-l", "3", handle.name, "-"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=PDFTOTEXT_TIMEOUT,
                check=False,
            )
    except subprocess.SubprocessError as error:
        logger.warning("pdftotext failed: %s", error)
        return ""
    if result.returncode != 0:
        logger.warning("pdftotext failed: %s", result.stderr.strip())
        return ""
    return normalize_text(result.stdout)


def stored_file_text(local_path: str | None, storage_url: str) -> str:
    """Normalised text of the file in storage, or "" when it cannot be read.

    Read only. The html column is a copy of this file made at scrape time,
    and for some records that copy is truncated while the file is whole.

    :param local_path: Opinion.local_path
    :param storage_url: base URL the files are served from
    :return: the first HEADER_CHARS of normalised text
    """
    if not local_path:
        return ""
    url = f"{storage_url.rstrip('/')}/{local_path.lstrip('/')}"
    try:
        response = requests.get(url, timeout=FETCH_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as error:
        logger.warning("Could not fetch %s: %s", url, error)
        return ""
    if len(response.content) > MAX_FETCH_BYTES:
        logger.warning("Not reading %s: %s bytes", url, len(response.content))
        return ""
    if local_path.lower().endswith(".pdf"):
        return pdf_text(response.content)
    # Storage serves no charset, and the requests default of Latin-1 turns
    # an en dash into three stray characters.
    markup = response.content.decode("utf-8", errors="replace")
    return normalize_markup(markup, STORED_RAW_CHARS)


def docket_from_stored_file(body: str, profile: CourtProfile) -> str | None:
    """Read the docket number out of a stored file's normalised text."""
    found = docket_from_body(body, profile.docket_re)
    if found or not profile.bare_number_fallback:
        return found
    match = TEX_LABELLED.search(body[:BARE_CHARS])
    return match.group(1).replace(EN_DASH, "-") if match else None


def document_body(row: dict[str, Any]) -> str:
    """The text the case-name check runs on.

    The stored file wins when it was read, because it is read only when the
    columns hold nothing usable, and a truncated html column still yields a
    few characters of markup that would otherwise be taken as the body.
    """
    return (
        row.get("_stored_text")
        or normalize_markup(row.get("html"))
        or normalize_text(row.get("plain_text"))
    )


def collect_sources(
    row: dict[str, Any],
    profile: CourtProfile,
    storage_url: str | None = None,
) -> dict[str, str | None]:
    """Read the docket number from every source available for one opinion.

    Only sources that travel with the file are used. `local_path` looks
    tempting but is not one: the filename was built from the record's case
    name at scrape time, so it agrees with the record by construction and
    corroborates nothing. The file it points at is one, though, and it is
    read when the html and plain_text columns yield nothing.

    :param row: an Opinion values() row; `_stored_text` is added to it when
        the stored file was read
    :param profile: the court's reading rules
    :param storage_url: where stored files are served from, or None to
        leave them unread
    :return: source name to docket number, with None where nothing was read
    """
    markup = normalize_markup(row.get("html"))
    text = normalize_text(row.get("plain_text"))

    sources: dict[str, str | None] = {}
    if profile.read_download_url:
        sources[BY_URL] = docket_from_url(row["download_url"])
    sources[BY_HTML] = docket_from_body(markup, profile.docket_re)
    sources[BY_TEXT] = docket_from_body(text, profile.docket_re)
    if storage_url and not any(sources.values()):
        body = stored_file_text(row.get("local_path"), storage_url)
        row["_stored_text"] = body
        sources[BY_FILE] = docket_from_stored_file(body, profile)
    return sources


def name_in_document(case_name: str | None, body: str) -> bool | None:
    """Whether a distinctive word from the record's case name is in the file.

    A weak second dimension, independent of the docket number. Absence is not
    proof of damage on its own: an illegible scan also lacks the name. Returns
    None when there is no text or no distinctive word to look for.
    """
    if not body or not case_name:
        return None
    words = [
        w.lower()
        for w in WORDS.findall(case_name)
        if w.lower() not in COMMON_WORDS
    ]
    if not words:
        return None
    lowered = body.lower()
    return any(w in lowered for w in words)


def shingles(body: str) -> set[str]:
    """Word runs of a fixed length, for comparing two documents."""
    words = body.lower().split()
    if len(words) < SHINGLE:
        return set()
    return {
        " ".join(words[i : i + SHINGLE])
        for i in range(len(words) - SHINGLE + 1)
    }


def containment(left: set[str], right: set[str]) -> float:
    """Share of the smaller document's word runs found in the larger."""
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def pick_by_text(body: str, candidate_bodies: dict[int, str]) -> int | None:
    """Choose the candidate whose stored text is the same document.

    Used when several records carry the docket number read from a file. In
    practice those candidates are one case holding different documents: the
    opinion, a dissent, a clerk letter. The docket number cannot separate
    them; the text can.

    Returns None unless one candidate clears both bars, so a near-tie between
    two copies of a reissued opinion is left for a person.

    :param body: normalised text of the misattached document
    :param candidate_bodies: candidate opinion id to its normalised text
    :return: the winning opinion id, or None
    """
    source = shingles(body)
    if not source:
        return None

    scores = sorted(
        (
            (containment(source, shingles(t)), i)
            for i, t in candidate_bodies.items()
            if t
        ),
        reverse=True,
    )
    if not scores or scores[0][0] < MATCH_FLOOR:
        return None
    runner_up = scores[1][0] if len(scores) > 1 else 0.0
    if scores[0][0] - runner_up < MATCH_MARGIN:
        return None
    return scores[0][1]


def full_text(row: dict[str, Any]) -> str:
    """The whole document flattened, with no cut, for its last lines."""
    if row.get("_stored_text"):
        return row["_stored_text"]
    if row.get("html"):
        text = BLOCKS.sub(" ", row["html"])
        text = TAGS.sub(" ", text)
        text = ENTITIES.sub(" ", text)
    else:
        text = row.get("plain_text") or ""
    return WHITESPACE.sub(" ", text)


def delivered_facts(text: str) -> tuple[date | None, str]:
    """The date a Texas opinion says it was delivered, and what kind it is.

    :param text: the whole document, flattened
    :return: the delivered date, or None; and one of majority, concurrence,
        dissent, order
    """
    delivered = None
    if match := DELIVERED.search(text):
        month, day, year = match.groups()
        try:
            delivered = date(int(year), MONTHS[month.lower()], int(day))
        except (KeyError, ValueError):
            delivered = None
    caption = text[:CAPTION_CHARS]
    if len(text.split()) < ORDER_WORDS:
        return delivered, ORDER
    majority = MAJORITY_LINE.search(caption)
    separate = SEPARATE_LINE.search(caption)
    if separate and (not majority or separate.start() < majority.start()):
        kind = (
            CONCURRENCE
            if separate.group(1).lower() == "concurring"
            else DISSENT
        )
    else:
        kind = MAJORITY
    return delivered, kind


def candidate_delivery_facts(opinion_ids: list[int]) -> list[dict[str, Any]]:
    """What the delivered-date rule needs to know about each candidate."""
    rows = list(
        Opinion.objects.filter(id__in=opinion_ids).values(
            "id",
            "type",
            "date_created",
            "cluster__date_filed",
            "cluster__case_name",
            *FILE_FIELDS,
        )
    )
    for row in rows:
        row["holds_file"] = any(row.get(f) for f in FILE_FIELDS)
    return rows


def pick_by_delivered_date(
    delivered: date | None,
    kind: str,
    body: str,
    candidates: list[dict[str, Any]],
) -> tuple[int | None, str | None]:
    """Choose the fileless candidate filed on the day the opinion was delivered.

    Same-docket candidates are the same case as several records: a Lawbox
    or Harvard import with text but no file, and 2015 scrapes holding a
    withdrawn earlier version or a separate opinion. The delivered date
    separates a superseding opinion from the version it replaced. A
    majority opinion may land on any fileless record of that day, the
    oldest first, since a combined record and a lead record of one case
    hold the same text. A concurrence or dissent may land only on a record
    of that type; an order is left for a person. A record whose case name
    is absent from the file is never chosen. A record holding any file
    column, even a dead pointer, is never written to.

    :param delivered: the date the file says it was delivered
    :param kind: majority, concurrence, dissent or order
    :param body: normalised text of the file, for the case-name check
    :param candidates: candidate_delivery_facts() rows
    :return: the winning opinion id, or None, and a reason when none
    """
    if not delivered:
        return None, "no delivered date printed"
    if kind == ORDER:
        return None, "file is an order, not an opinion"
    on_date = [c for c in candidates if c["cluster__date_filed"] == delivered]
    if not on_date:
        return None, f"no candidate filed on {delivered.isoformat()}"
    empty = [c for c in on_date if not c["holds_file"]]
    if not empty:
        return None, f"candidates on {delivered.isoformat()} all hold a file"
    typed = [c for c in empty if c["type"] in KIND_TYPES[kind]]
    if not typed:
        return None, f"no fileless {kind} record on {delivered.isoformat()}"
    named = [
        c
        for c in typed
        if name_in_document(c["cluster__case_name"], body) is not False
    ]
    if not named:
        return None, "no candidate names the parties in the file"
    winner = min(named, key=lambda c: (c["date_created"], c["id"]))
    return winner["id"], None


def header_facts(
    body: str,
) -> tuple[date | None, tuple[str, str, str] | None]:
    """The filing date and neutral citation a North Dakota file prints.

    :param body: normalised document text
    :return: the date, and (volume, reporter, page) of the neutral citation
        as strings, the way search_citation stores them; None for whichever
        is not printed
    """
    filed = None
    if match := FILED_NUMERIC.search(body[:ND_HEADER_CHARS]):
        month, day, year = (int(g) for g in match.groups())
        if year < 100:
            year += 1900 if year >= 90 else 2000
        try:
            filed = date(year, month, day)
        except ValueError:
            filed = None
    cite = None
    if match := NEUTRAL_CITE.search(body[:ND_HEADER_CHARS]):
        volume, reporter, page = match.groups()
        cite = (volume, WHITESPACE.sub(" ", reporter), page)
    return filed, cite


FilingFacts = dict[int, tuple[date | None, set[tuple[str, str, str]]]]


def shape_filing_facts(
    opinions: list[dict[str, Any]],
    citations: list[tuple[int, Any, str, Any]],
) -> FilingFacts:
    """Join opinion rows to their neutral citations, keyed as strings.

    search_citation stores volume and page as text, so the header's
    reading is compared as text too; an int here would never match.

    :param opinions: values() rows with id, cluster_id, cluster__date_filed
    :param citations: (cluster_id, volume, reporter, page) rows
    :return: opinion id to its filing date and neutral citations
    """
    cites: dict[int, set[tuple[str, str, str]]] = {}
    for cluster_id, volume, reporter, page in citations:
        cites.setdefault(cluster_id, set()).add(
            (str(volume), reporter, str(page))
        )
    return {
        r["id"]: (r["cluster__date_filed"], cites.get(r["cluster_id"], set()))
        for r in opinions
    }


def candidate_filing_facts(opinion_ids: list[int]) -> FilingFacts:
    """Filing date and neutral citations of each candidate opinion."""
    rows = list(
        Opinion.objects.filter(id__in=opinion_ids).values(
            "id", "cluster_id", "cluster__date_filed"
        )
    )
    citations = list(
        Citation.objects.filter(
            cluster_id__in={r["cluster_id"] for r in rows},
            reporter__in=["ND", "ND App"],
        ).values_list("cluster_id", "volume", "reporter", "page")
    )
    return shape_filing_facts(rows, citations)


def pick_by_filing_date(
    body: str,
    facts: Mapping[int, tuple[date | None, set[tuple[str, str, str]]]],
) -> int | None:
    """Choose the candidate filed on the date the file prints, with its cite.

    Same-docket candidates are different opinions of one case: an original
    and one on rehearing, for example. The docket cannot separate them; the
    filing date and the neutral citation printed in the file can. Both must
    be readable and both must agree on exactly one candidate. A file with no
    neutral citation, as before 1997, is left for a person: a rehearing
    denial can reprint the original opinion's date. A candidate whose
    cluster carries no neutral citation row cannot win either, which is
    safe: about 1% of aligned files print a citation their cluster lacks.

    :param body: normalised text of the misattached document
    :param facts: candidate opinion id to its filing date and citations
    :return: the winning opinion id, or None
    """
    filed, cite = header_facts(body)
    if not filed or not cite:
        return None
    hits = [
        i
        for i, (candidate_date, cites) in facts.items()
        if candidate_date == filed and cite in cites
    ]
    return hits[0] if len(hits) == 1 else None


def judge(
    sources: dict[str, str | None],
    on_record: str,
    profile: CourtProfile | None = None,
) -> tuple[str, str | None, str | None]:
    """Decide what the sources say about one record.

    Agreement between two or more independent sources is treated as high
    confidence, a lone source as medium, and disagreement as a conflict for a
    person to settle. Calibration against undamaged records shows no single
    source is better than 99%, so corroboration matters.

    :return: status, the docket number the file claims, confidence
    """
    profile = profile or PROFILES["tex"]
    found = [v for v in sources.values() if v]
    if not found:
        return UNDETERMINED, None, None

    keys = {docket_key(v, profile) for v in found}
    if len(keys) > 1:
        # A consolidated case is filed under several numbers. The URL can
        # carry one and the header another, and both belong to this record.
        # The record's own docket takes precedence: another record covering
        # the same numbers would be a duplicate of the same case, and the
        # file is already on one of them. Records this branch never
        # reaches are settled in resolve_conflicts.
        if keys <= docket_numbers(on_record, profile):
            return ALIGNED, found[0], HIGH
        return CONFLICTED, None, None

    claimed = found[0]
    confidence = HIGH if len(found) > 1 else MEDIUM
    status = (
        ALIGNED
        if docket_key(claimed, profile) in docket_numbers(on_record, profile)
        else MISATTACHED
    )
    return status, claimed, confidence


def upgrade_confidence(
    status: str, confidence: str | None, name_match: bool | None
) -> str | None:
    """Raise a lone docket source to high when the case name agrees with it.

    Texas needs this: a document is either HTML or a PDF, never both, so its
    two body sources can never corroborate each other. The case name is the
    only independent second dimension available there.

    Measured on the tex 2013-06-06 run: of 257 aligned records just 1 lacked
    the record's name, so agreement in the same direction is meaningful.
    Disagreement is left at medium rather than demoted, because a missing
    name can simply mean an illegible scan.
    """
    if confidence != MEDIUM or name_match is None:
        return confidence
    agrees = (status == ALIGNED and name_match) or (
        status == MISATTACHED and not name_match
    )
    return HIGH if agrees else confidence


BASE_FIELDS = [
    "id",
    "cluster_id",
    "date_created",
    "local_path",
    "sha1",
    "download_url",
    "html",
    "plain_text",
    "cluster__case_name",
    "cluster__date_filed",
    "cluster__source",
    "cluster__docket_id",
    "cluster__docket__docket_number",
]


def scraped_opinions(
    court_id: str, created_after: datetime, created_before: datetime
):
    """Opinions this court's scraper wrote in a window.

    A non-empty download_url is what marks scraper output. On `tex` it selects
    exactly the same rows as a cluster source containing "C".
    """
    return (
        Opinion.objects.filter(
            cluster__docket__court_id=court_id,
            date_created__gte=created_after,
            date_created__lt=created_before,
        )
        .exclude(download_url__isnull=True)
        .exclude(download_url="")
        .values(*BASE_FIELDS)
        .order_by("id")
    )


def audit_court(
    court_id: str,
    created_after: datetime,
    created_before: datetime,
    limit: int | None,
    storage_url: str | None = None,
) -> list[dict[str, Any]]:
    """Compare each scraped file against the record it is attached to.

    :param court_id: the court to audit
    :param created_after: lower bound on Opinion.date_created
    :param created_before: upper bound on Opinion.date_created
    :param limit: stop after this many opinions, for dry runs
    :param storage_url: where stored files are served from, or None to
        leave them unread
    :return: one result dict per opinion examined
    """
    profile = PROFILES.get(court_id, PROFILES["tex"])

    # Opinion.date_created is the scrape timestamp. The cluster and docket
    # timestamps come from later backfills and cannot identify a run.
    #
    # The file fields are read from Opinion. search_opinioncontent exists but
    # is empty; once it is backfilled, check which table is authoritative.
    queryset = scraped_opinions(court_id, created_after, created_before)
    if limit:
        queryset = queryset[:limit]

    records = []
    for row in queryset.iterator(chunk_size=500):
        on_record = row["cluster__docket__docket_number"]
        sources = collect_sources(row, profile, storage_url)
        status, claimed, confidence = judge(sources, on_record, profile)

        body = document_body(row)
        name_match = name_in_document(row["cluster__case_name"], body)
        confidence = upgrade_confidence(status, confidence, name_match)
        delivered, kind = (
            delivered_facts(full_text(row))
            if profile.delivered_footer
            else (None, None)
        )
        records.append(
            {
                "opinion_id": row["id"],
                "court_id": court_id,
                "cluster_id": row["cluster_id"],
                "docket_id": row["cluster__docket_id"],
                "scrape_run": row["date_created"].date().isoformat(),
                "date_filed": row["cluster__date_filed"],
                "case_name": row["cluster__case_name"],
                "cluster_source": row["cluster__source"],
                "docket_number_on_record": on_record,
                "docket_number_in_file": claimed,
                # Every distinct number the sources read, as comparison
                # keys. More than one means the sources disagreed.
                "numbers_in_file": sorted(
                    {
                        k
                        for v in sources.values()
                        if (k := docket_key(v, profile))
                    }
                ),
                "sources": sources,
                "agreeing_sources": len([v for v in sources.values() if v]),
                "record_name_in_file": name_match,
                # Texas only: the date printed at the end of the file, and
                # whether it is a majority opinion, a separate one or an
                # order.
                "file_delivered": delivered,
                "file_kind": kind,
                "status": status,
                "confidence": confidence,
                "local_path": row["local_path"],
                "sha1": row["sha1"],
                "download_url": row["download_url"],
                "target_opinion_id": None,
                "target_scope": None,
                "target_method": None,
                "target_is_scraped": None,
                # Dropped before the report is written.
                "_body": body,
                "needs_review": status == CONFLICTED,
                "review_reason": (
                    "sources disagree: "
                    + ", ".join(f"{k}={v}" for k, v in sources.items() if v)
                    if status == CONFLICTED
                    else None
                ),
            }
        )

    logger.info("%s: examined %s opinions", court_id, len(records))
    return records


def lookup_destinations(
    group: tuple[str, ...], wanted: set[str], profile: CourtProfile
) -> dict[str, list[int]]:
    """Find opinions in these courts whose docket field covers a wanted number.

    Matches on the same keys the audit compares with, so a record spelled
    "Civil 980067CA" is found by "980067" read out of a file, and a record
    spelled "20130119, 20130120" is found by either number. The docket
    fields are read in Python with `docket_numbers`, because SQL cannot
    expand the ranges. The court group holds a few tens of thousands of
    rows, so one pass is cheap.

    :param group: court ids to search
    :param wanted: docket keys to look for
    :param profile: the court's comparison rules
    :return: docket key to the opinion ids carrying it
    """
    # Non-scraped records are legitimate destinations: the Harvard or Lawbox
    # cluster is often the rightful owner. They are marked in the report
    # rather than excluded here.
    opinions = Opinion.objects.filter(
        cluster__docket__court_id__in=group
    ).values_list("cluster__docket__docket_number", "id")

    found: dict[str, list[int]] = {}
    for docket_number, opinion_id in opinions.iterator(chunk_size=5000):
        for key in docket_numbers(docket_number, profile) & wanted:
            found.setdefault(key, []).append(opinion_id)
    return found


# The columns a file occupies. A destination with any of them set holds a
# file that a move would overwrite. sha1 is left out: Lawbox imports carry
# one without a file, and it is recomputed from whatever file arrives.
FILE_FIELDS = ["download_url", "local_path", "html", "plain_text"]


def scraped_destinations(opinion_ids: set[int]) -> set[int]:
    """Of these candidate destinations, which already hold a file.

    A destination outside the damaged run can be a legitimate owner, so these
    are not excluded. The report records which ones they are, because moving a
    file onto a record that never held one is a different decision from
    swapping two scraped files. Any file column counts: a Columbia import has
    no download_url but keeps its XML in local_path, and that must not be
    overwritten.
    """
    holding = Q()
    for column in FILE_FIELDS:
        holding |= Q(**{f"{column}__isnull": False}) & ~Q(**{column: ""})
    return set(
        Opinion.objects.filter(id__in=opinion_ids)
        .filter(holding)
        .values_list("id", flat=True)
    )


def candidate_bodies(
    opinion_ids: list[int], audited: set[int]
) -> dict[int, str]:
    """Normalised text for each candidate destination.

    Prefers text merged from other providers, because the scraped fields of a
    record in the damaged run may themselves hold a misattached file. For a
    candidate inside the audited set, its own html and plain_text are
    therefore ignored.

    :param opinion_ids: candidates to load
    :param audited: opinion ids covered by this audit run
    :return: opinion id to normalised text, empty string where none exists
    """
    rows = Opinion.objects.filter(id__in=opinion_ids).values(
        "id",
        "xml_harvard",
        "html_lawbox",
        "html_columbia",
        "html",
        "plain_text",
    )
    bodies = {}
    for row in rows:
        merged = (
            row["xml_harvard"] or row["html_lawbox"] or row["html_columbia"]
        )
        if merged:
            bodies[row["id"]] = normalize_markup(merged)
            continue
        if row["id"] in audited:
            bodies[row["id"]] = ""
            continue
        bodies[row["id"]] = normalize_markup(row["html"]) or normalize_text(
            row["plain_text"]
        )
    return bodies


def resolve_targets(
    court_id: str,
    records: list[dict[str, Any]],
    profile: CourtProfile | None = None,
    peers: list[dict[str, Any]] | None = None,
) -> None:
    """Name the opinion that each misattached file belongs on.

    A target inside the same scrape run is preferred, because that is where the
    permutation happened. Anything ambiguous is flagged rather than guessed.

    :param court_id: the court these records belong to
    :param records: audit rows, modified in place
    :param profile: the court's comparison rules
    :param peers: audit rows from the other courts in this court's group,
        offered as destinations but never modified
    :return: None
    """
    profile = profile or PROFILES["tex"]
    group = COURT_GROUPS.get(court_id, (court_id,))
    audited = {r["opinion_id"] for r in [*records, *(peers or [])]}

    in_run: dict[str, list[int]] = {}
    for record in [*records, *(peers or [])]:
        for key in docket_numbers(record["docket_number_on_record"], profile):
            in_run.setdefault(key, []).append(record["opinion_id"])

    misattached = [r for r in records if r["status"] == MISATTACHED]

    # Files whose owner was not part of this run. Looked up in one query
    # rather than one per record.
    orphans = {
        key
        for r in misattached
        if (key := docket_key(r["docket_number_in_file"], profile))
        and key not in in_run
    }
    outside = lookup_destinations(group, orphans, profile) if orphans else {}

    for record in misattached:
        wanted = record["docket_number_in_file"]
        key = docket_key(wanted, profile)
        candidates = in_run.get(key) if key else None
        scope = "in_run"
        if not candidates:
            candidates = outside.get(key, []) if key else []
            scope = "outside_run"

        candidates = [c for c in candidates if c != record["opinion_id"]]
        if len(candidates) == 1:
            record["target_opinion_id"] = candidates[0]
            record["target_scope"] = scope
            record["target_method"] = BY_DOCKET
            continue

        # Without the document's own text there is nothing to match, so
        # skip the candidate lookup rather than query for nothing.
        if len(candidates) > 1 and record.get("_body"):
            winner = pick_by_text(
                record["_body"],
                candidate_bodies(candidates, audited),
            )
            if winner:
                record["target_opinion_id"] = winner
                record["target_scope"] = scope
                record["target_method"] = BY_TEXT_MATCH
                continue
            # Only in-run candidates are different opinions of one case
            # that the header can separate. Query only when the header
            # gives both facts.
            if (
                profile.filing_date_header
                and scope == "in_run"
                and all(header_facts(record["_body"]))
            ):
                winner = pick_by_filing_date(
                    record["_body"], candidate_filing_facts(candidates)
                )
                if winner:
                    record["target_opinion_id"] = winner
                    record["target_scope"] = scope
                    record["target_method"] = BY_FILING_DATE
                    continue
            if profile.delivered_footer and record.get("file_delivered"):
                winner, why = pick_by_delivered_date(
                    record["file_delivered"],
                    record["file_kind"],
                    record["_body"],
                    candidate_delivery_facts(candidates),
                )
                if winner:
                    record["target_opinion_id"] = winner
                    record["target_scope"] = scope
                    record["target_method"] = BY_DELIVERED
                    continue
                record["needs_review"] = True
                record["review_reason"] = (
                    f"{len(candidates)} opinions share docket {wanted}; {why}"
                )
                continue

        record["needs_review"] = True
        record["review_reason"] = (
            f"no opinion found for docket {wanted}"
            if not candidates
            else f"{len(candidates)} opinions share docket {wanted}"
        )

    names = {
        r["opinion_id"]: r["case_name"] for r in [*records, *(peers or [])]
    }
    resolve_conflicts(records, group, profile, in_run, names)


def covering(numbers: list[str], found: dict[str, list[int]]) -> set[int]:
    """Opinions whose docket covers every one of these numbers."""
    sets = [set(found.get(n, [])) for n in numbers]
    return set.intersection(*sets) if sets else set()


def case_names(
    opinion_ids: set[int], known: dict[int, str | None]
) -> dict[int, str | None]:
    """Case names for these opinions, reading the database only for unknowns."""
    missing = opinion_ids - set(known)
    found = dict(known)
    if missing:
        found.update(
            Opinion.objects.filter(id__in=missing).values_list(
                "id", "cluster__case_name"
            )
        )
    return found


def resolve_conflicts(
    records: list[dict[str, Any]],
    group: tuple[str, ...],
    profile: CourtProfile,
    in_run: dict[str, list[int]],
    names: dict[int, str | None],
) -> None:
    """Settle records whose sources disagree, in two steps.

    Covering rule. A consolidated case is filed under several numbers. The
    file name can carry one and the header another. When exactly one other
    record's docket covers every number read, the file belongs on that
    record and the disagreement is not a conflict. Both sources point at
    the same case, so the verdict is high confidence.

    Sole owned number. Otherwise, when exactly one of the numbers read is
    carried by any record, exactly one record carries it, and that record's
    case name is printed in the document, the file belongs on that record.
    The other number is a misprint or an appeal number the record does not
    list. One source plus the case name, so medium confidence. This is a
    fallback for conflicts only; it never touches the ordinary paths.

    :param records: audit rows, modified in place
    :param group: court ids to search outside the run
    :param profile: the court's comparison rules
    :param in_run: docket key to the audited opinion ids covering it
    :param names: opinion id to case name for every audited row
    :return: None
    """
    conflicted = [
        r
        for r in records
        if r["status"] == CONFLICTED
        and len(r.get("numbers_in_file") or []) > 1
    ]
    if not conflicted:
        return

    # Only records the run cannot cover need the database.
    orphans = {
        n
        for r in conflicted
        if not covering(r["numbers_in_file"], in_run) - {r["opinion_id"]}
        for n in r["numbers_in_file"]
    }
    outside = lookup_destinations(group, orphans, profile) if orphans else {}

    def settle(
        record: dict[str, Any],
        target: int,
        scope: str,
        method: str,
        confidence: str,
        number: str,
    ) -> None:
        record["status"] = MISATTACHED
        record["confidence"] = confidence
        # Stays a single number, as everywhere else; the full set is in
        # numbers_in_file.
        record["docket_number_in_file"] = number
        record["target_opinion_id"] = target
        record["target_scope"] = scope
        record["target_method"] = method
        record["needs_review"] = False
        record["review_reason"] = None

    for record in conflicted:
        numbers = record["numbers_in_file"]
        me = {record["opinion_id"]}
        candidates = covering(numbers, in_run) - me
        scope = "in_run"
        if not candidates:
            candidates = covering(numbers, outside) - me
            scope = "outside_run"
        if len(candidates) == 1:
            settle(
                record, candidates.pop(), scope, BY_COVERING, HIGH, numbers[0]
            )
            continue
        if candidates:
            record["review_reason"] = (
                f"{record['review_reason']}; {len(candidates)} opinions "
                f"cover dockets {', '.join(numbers)}"
            )
            continue

        # Fallback: a single number that any record carries.
        owned = {
            n: (set(in_run.get(n, [])) - me, set(outside.get(n, [])) - me)
            for n in numbers
        }
        owned = {n: o for n, o in owned.items() if o[0] or o[1]}
        if len(owned) != 1:
            continue
        number, (inside, beyond) = owned.popitem()
        owners, scope = (
            (inside, "in_run") if inside else (beyond, "outside_run")
        )
        if len(owners) != 1:
            record["review_reason"] = (
                f"{record['review_reason']}; {len(owners)} opinions carry "
                f"docket {number}"
            )
            continue
        owner = owners.pop()
        name = case_names({owner}, names).get(owner)
        if name_in_document(name, record.get("_body", "")) is not True:
            continue
        settle(record, owner, scope, BY_OWNED, MEDIUM, number)


def calibrate(court_id: str, created_after: datetime) -> dict[str, Any]:
    """Measure how often each source is right, on records the bug never hit.

    Runs the same extractors over opinions scraped well after the August 2014
    fix. Those files are attached correctly, so any disagreement with the
    record is the extractor being wrong, not damage. Use this to decide how
    much weight a source deserves. Stored files are not fetched here; that
    source is measured only by the 20 records it was built for, each
    confirmed by case name.

    :param court_id: the court to calibrate
    :param created_after: only use records scraped after this moment
    :return: per-source extracted/agreed counts
    """
    profile = PROFILES.get(court_id, PROFILES["tex"])
    far_future = timezone.make_aware(datetime(2100, 1, 1))
    tally: dict[str, dict[str, float]] = {}

    examined = 0
    for row in scraped_opinions(court_id, created_after, far_future).iterator(
        chunk_size=500
    ):
        examined += 1
        # Compare on the same key judge() uses. A literal comparison counts
        # every prefixed North Dakota record as extractor error.
        on_record = docket_numbers(
            row["cluster__docket__docket_number"], profile
        )
        for source, value in collect_sources(row, profile).items():
            counts = tally.setdefault(source, {"extracted": 0, "agrees": 0})
            if not value:
                continue
            counts["extracted"] += 1
            if docket_key(value, profile) in on_record:
                counts["agrees"] += 1

    for source, counts in tally.items():
        extracted = counts["extracted"]
        counts["agreement_pct"] = (
            round(100.0 * counts["agrees"] / extracted, 1)
            if extracted
            else 0.0
        )
    logger.info("%s: calibrated on %s opinions", court_id, examined)
    return {"examined": examined, "sources": tally}


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Count the outcomes for one court."""

    def n(predicate) -> int:
        return sum(1 for r in records if predicate(r))

    return {
        "examined": len(records),
        "aligned": n(lambda r: r["status"] == ALIGNED),
        "misattached": n(lambda r: r["status"] == MISATTACHED),
        "undetermined": n(lambda r: r["status"] == UNDETERMINED),
        "conflicted": n(lambda r: r["status"] == CONFLICTED),
        "misattached_high_confidence": n(
            lambda r: r["status"] == MISATTACHED and r["confidence"] == HIGH
        ),
        # A misattached file should not carry the record's own case name.
        # If it does, treat the finding with suspicion.
        "misattached_but_name_matches": n(
            lambda r: (
                r["status"] == MISATTACHED and r["record_name_in_file"] is True
            )
        ),
        "aligned_but_name_missing": n(
            lambda r: (
                r["status"] == ALIGNED and r["record_name_in_file"] is False
            )
        ),
        "resolved": n(lambda r: r["target_opinion_id"]),
        "needs_review": n(lambda r: r["needs_review"]),
    }


CONFIDENCE_RANK = {MEDIUM: 1, HIGH: 2}

# Why a record was left out of the plan.
NO_TARGET = "no target resolved"
LOW_CONFIDENCE = "below the requested confidence"
TARGET_NOT_MOVING = "target keeps its own file, so it cannot receive another"
TARGET_UNKNOWN = "the audit did not say whether the target holds a file"
TARGET_CONTESTED = "several files claim the same target"
BROKEN_CHAIN = "depends on a record that was itself excluded"


@dataclass
class Moves:
    """The resolved moves and what is known about their targets.

    :param moves: opinion id to target opinion id
    :param excluded: exclusions by opinion id
    :param claims: how many resolved files claim each target, counted before
        the confidence filter so a dropped claim still marks its target
        contested
    :param fileless: targets the audit found to hold no file, and that are
        not themselves audited records
    :param unknown: targets the audit did not describe
    """

    moves: dict[int, int] = field(default_factory=dict)
    excluded: dict[int, str] = field(default_factory=dict)
    claims: Counter = field(default_factory=Counter)
    fileless: set[int] = field(default_factory=set)
    unknown: set[int] = field(default_factory=set)


def build_moves(records: list[dict[str, Any]], min_confidence: str) -> Moves:
    """Collect the file moves the audit resolved.

    :param records: audit rows
    :param min_confidence: skip misattached rows weaker than this
    :return: the moves, exclusions and target facts
    """
    floor = CONFIDENCE_RANK[min_confidence]
    audited = {r["opinion_id"] for r in records}
    found = Moves()
    for record in records:
        if record["status"] != MISATTACHED:
            continue
        target = record["target_opinion_id"]
        if not target:
            found.excluded[record["opinion_id"]] = NO_TARGET
            continue
        found.claims[target] += 1
        rank = CONFIDENCE_RANK.get(record["confidence"] or MEDIUM, 1)
        if rank < floor:
            found.excluded[record["opinion_id"]] = LOW_CONFIDENCE
            continue
        found.moves[record["opinion_id"]] = target
        holds_file = record.get("target_is_scraped")
        # An audited record always holds a scraped file, whatever the flag
        # says; only a record outside the report can be empty.
        if target in audited:
            continue
        if holds_file is False:
            found.fileless.add(target)
        elif holds_file is None:
            found.unknown.add(target)
    return found


def prune_moves(found: Moves) -> dict[int, int]:
    """Drop every move that cannot be applied without overwriting a file.

    A file can only be written onto a record once that record's own file has
    been moved away, or when the record has no scraped file at all. Two cases
    break that:

    - the target keeps a scraped file of its own, so applying the move would
      overwrite a file we have nowhere to put;
    - two files claim the same target, so at most one of them can be right.

    Removing a move can strand others that pointed into it, so this repeats
    until nothing more drops. What survives has exactly one incoming move
    per target, and every target is either moving too or holds no file: a
    disjoint union of closed cycles and of open chains that end on a
    fileless record.

    :param found: the moves and target facts; moves and exclusions are
        narrowed and extended in place
    :return: the surviving moves
    """
    moves, excluded = found.moves, found.excluded
    while True:
        doomed = {}
        for source, target in moves.items():
            if found.claims[target] > 1:
                doomed[source] = TARGET_CONTESTED
            elif target not in moves and target not in found.fileless:
                if target in excluded:
                    # Dropped earlier in this loop, or never resolved.
                    doomed[source] = BROKEN_CHAIN
                elif target in found.unknown:
                    doomed[source] = TARGET_UNKNOWN
                else:
                    doomed[source] = TARGET_NOT_MOVING
        if not doomed:
            return moves
        for source, reason in doomed.items():
            excluded[source] = reason
            del moves[source]


def walk(
    moves: dict[int, int],
) -> tuple[list[list[int]], list[tuple[list[int], int]]]:
    """Split the pruned moves into closed cycles and open chains.

    A chain starts at a record nothing points at and ends at a record that
    is not itself moving, which after pruning is always a fileless one.
    Whatever is left once the chains are removed is a union of cycles.

    :param moves: opinion id to target opinion id, already pruned
    :return: each cycle as opinion ids in move order, and each chain as its
        opinion ids in move order plus the fileless record it ends on
    """
    seen: set[int] = set()
    has_incoming = set(moves.values())

    chains = []
    for start in sorted(moves):
        if start in seen or start in has_incoming:
            continue
        path = []
        node = start
        while node in moves and node not in seen:
            seen.add(node)
            path.append(node)
            node = moves[node]
        chains.append((path, node))

    cycles = []
    for start in sorted(moves):
        if start in seen:
            continue
        cycle = []
        node = start
        while node not in seen:
            seen.add(node)
            cycle.append(node)
            node = moves[node]
        cycles.append(cycle)
    return cycles, chains


def plan_cycles(
    records: list[dict[str, Any]], min_confidence: str
) -> dict[str, Any]:
    """Turn audit rows into an ordered, applicable fix plan.

    Each cycle and each chain in the result is safe to apply on its own,
    inside one transaction. A chain ends on a record that holds no scraped
    file, so its moves are listed last move first: the file lands on the
    empty record, which frees the record before it, and so on back to the
    start. The start record is left without a scraped file, because no
    resolved file belongs on it; it is reported as the chain's `orphan`.
    Anything that could not be made safe is listed with a reason rather
    than dropped silently.

    :param records: audit rows from one or more report files
    :param min_confidence: skip misattached rows weaker than this
    :return: the plan, ready to serialise
    """
    by_id = {r["opinion_id"]: r for r in records}
    found = build_moves(records, min_confidence)
    moves = prune_moves(found)
    excluded = found.excluded

    def court_of(members: list[int]) -> str:
        courts = {by_id[m]["court_id"] for m in members}
        return courts.pop() if len(courts) == 1 else "mixed"

    cycle_members, chain_members = walk(moves)
    cycles = []
    for members in cycle_members:
        cycles.append(
            {
                "court_id": court_of(members),
                "size": len(members),
                "members": members,
                # The file currently on `file_on` belongs on `belongs_on`.
                "moves": [
                    {"file_on": m, "belongs_on": moves[m]} for m in members
                ],
            }
        )
    chains = []
    for members, end in chain_members:
        chains.append(
            {
                "court_id": court_of(members),
                "size": len(members),
                "members": members,
                # Holds no file; receives the last member's file. Not an
                # audited record, so the fix script must read its docket
                # and case name from the database before writing.
                "end": end,
                "end_in_report": False,
                # Loses its file and receives none. After the moves, its
                # file fields are cleared.
                "orphan": members[0],
                # In application order: onto the empty record first.
                "moves": [
                    {"file_on": m, "belongs_on": moves[m]}
                    for m in reversed(members)
                ],
            }
        )

    return {
        "summary": {
            "records_in_report": len(records),
            "applicable_moves": len(moves),
            "cycles": len(cycles),
            "chains": len(chains),
            "orphans": len(chains),
            "excluded": len(excluded),
            "excluded_by_reason": dict(Counter(excluded.values())),
            "cycles_by_size": dict(
                sorted(Counter(len(m) for m in cycle_members).items())
            ),
            "chains_by_size": dict(
                sorted(Counter(len(m) for m, _ in chain_members).items())
            ),
            "moves_by_court": dict(
                Counter(by_id[m]["court_id"] for m in moves)
            ),
        },
        # The columns a move carries, and the columns cleared on an orphan.
        "file_fields": FILE_FIELDS,
        "cycles": cycles,
        "chains": chains,
        "excluded": [
            {
                "opinion_id": opinion_id,
                "court_id": by_id[opinion_id]["court_id"],
                "case_name": by_id[opinion_id]["case_name"],
                "docket_number_on_record": by_id[opinion_id][
                    "docket_number_on_record"
                ],
                "docket_number_in_file": by_id[opinion_id][
                    "docket_number_in_file"
                ],
                "reason": reason,
            }
            for opinion_id, reason in sorted(excluded.items())
        ],
    }


class Command(VerboseCommand):
    help = (
        "Audit opinions whose file was attached to the wrong record by the "
        "juriscraper DeferringList sorting bug. Read only; writes a JSON "
        "report naming the opinion each misattached file belongs on."
    )

    def add_arguments(self, parser):
        """Register the audit's arguments.

        :param parser: the command's argument parser
        :return: None
        """
        parser.add_argument(
            "--courts",
            nargs="+",
            default=DEFAULT_COURTS,
            help=f"Court ids to audit. Default: {' '.join(DEFAULT_COURTS)}",
        )
        parser.add_argument(
            "--created-after",
            default=DEFAULT_CREATED_AFTER,
            help=(
                "Lower bound on Opinion.date_created, YYYY-MM-DD. Narrow this "
                "to a single scrape run to audit that run alone. Read in the "
                "project time zone, not UTC, so a run picked out of SQL with "
                "date_created::date can fall outside a same-day bound. Pad it "
                f"by a day. Default: {DEFAULT_CREATED_AFTER}"
            ),
        )
        parser.add_argument(
            "--created-before",
            default=DEFAULT_CREATED_BEFORE,
            help=(
                "Upper bound on Opinion.date_created, exclusive, YYYY-MM-DD. "
                f"Default: {DEFAULT_CREATED_BEFORE}"
            ),
        )
        parser.add_argument(
            "--output",
            help="Path to write the JSON report to. Required unless --from-reports.",
        )
        parser.add_argument(
            "--plan",
            help=(
                "Also write a fix plan here: the resolved moves grouped into "
                "closed rotations and open chains, each safe to apply in one "
                "transaction, plus everything that could not be made safe."
            ),
        )
        parser.add_argument(
            "--from-reports",
            nargs="+",
            help=(
                "Build the plan from these saved reports instead of auditing. "
                "Touches no database. Use it after a person has written a "
                "target into a report, or to change --min-confidence."
            ),
        )
        parser.add_argument(
            "--min-confidence",
            choices=[MEDIUM, HIGH],
            default=MEDIUM,
            help=(
                "Skip misattached records weaker than this in the plan. "
                "'high' means two independent sources agreed. Default: "
                "medium, which includes records resting on a single source."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Stop after this many opinions per court, for dry runs.",
        )
        parser.add_argument(
            "--storage-url",
            default=STORAGE_URL,
            help=(
                "Where Opinion.local_path files are served from. A file is "
                "fetched only when the html and plain_text columns yield no "
                f"docket number. Default: {STORAGE_URL}"
            ),
        )
        parser.add_argument(
            "--no-stored-files",
            action="store_true",
            help="Do not read stored files; rely on the columns alone.",
        )
        parser.add_argument(
            "--calibrate",
            action="store_true",
            help=(
                "Also measure each source against records scraped after "
                f"{CALIBRATION_AFTER}, which the bug never touched. Any "
                "disagreement there is the extractor being wrong rather than "
                "damage, so it tells you how far to trust each source."
            ),
        )

    def handle(self, *args, **options):
        """Audit each court and write the JSON report.

        Reads only. Narrow --created-after and --created-before to a single
        scrape run when auditing one back scrape, since the permutation
        happened inside a run and target resolution prefers in-run matches.

        :return: None
        """
        super().handle(*args, **options)

        if options["from_reports"]:
            if not options["plan"]:
                raise CommandError("--from-reports needs --plan.")
            records = []
            for name in options["from_reports"]:
                path = Path(name)
                if not path.is_file():
                    raise CommandError(f"No such report: {path}")
                records.extend(json.loads(path.read_text())["records"])
            self.write_plan(records, options["from_reports"], options)
            return
        if not options["output"]:
            raise CommandError("--output is required unless --from-reports.")

        try:
            created_after = timezone.make_aware(
                datetime.strptime(options["created_after"], "%Y-%m-%d")
            )
            created_before = timezone.make_aware(
                datetime.strptime(options["created_before"], "%Y-%m-%d")
            )
            calibration_after = timezone.make_aware(
                datetime.strptime(CALIBRATION_AFTER, "%Y-%m-%d")
            )
        except ValueError as error:
            raise CommandError(f"Bad date: {error}") from error

        # Audit every court before resolving any of them. Resolution needs
        # the sibling court's records as candidate destinations, because
        # files crossed between nd and ndctapp.
        storage_url = (
            None if options["no_stored_files"] else options["storage_url"]
        )
        if storage_url is not None and not storage_url.strip():
            raise CommandError(
                "--storage-url is empty; pass --no-stored-files to skip files"
            )
        found_by_court = {
            court_id: audit_court(
                court_id,
                created_after,
                created_before,
                options["limit"],
                storage_url,
            )
            for court_id in options["courts"]
        }

        summary: dict[str, Any] = {}
        calibration: dict[str, Any] = {}
        records: list[dict[str, Any]] = []
        for court_id, found in found_by_court.items():
            peers = [
                row
                for peer_id in COURT_GROUPS.get(court_id, (court_id,))
                if peer_id != court_id
                for row in found_by_court.get(peer_id, [])
            ]
            resolve_targets(
                court_id,
                found,
                PROFILES.get(court_id, PROFILES["tex"]),
                peers,
            )
            summary[court_id] = summarize(found)
            records.extend(found)
            if options["calibrate"]:
                calibration[court_id] = calibrate(court_id, calibration_after)

        payload = {
            "generated_at": timezone.now().isoformat(),
            "params": {
                "courts": options["courts"],
                "created_after": options["created_after"],
                "created_before": options["created_before"],
                "limit": options["limit"],
                "calibrated": options["calibrate"],
                "stored_files_read": storage_url is not None,
                "storage_url": storage_url,
            },
            "summary": summary,
            "calibration": calibration,
            "records": records,
        }

        # Moving a file onto a record that never held one is a different
        # decision from swapping two scraped files. Mark which is which.
        scraped = scraped_destinations(
            {r["target_opinion_id"] for r in records if r["target_opinion_id"]}
        )
        for record in records:
            record.pop("_body", None)
            if record["target_opinion_id"]:
                record["target_is_scraped"] = (
                    record["target_opinion_id"] in scraped
                )

        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, default=str))

        for court_id, counts in summary.items():
            logger.info("%s: %s", court_id, counts)
        for court_id, counts in calibration.items():
            logger.info("%s calibration: %s", court_id, counts)
        logger.info("Wrote %s records to %s", len(records), output)
        if options["plan"]:
            self.write_plan(records, [str(output)], options)

    def write_plan(
        self,
        records: list[dict[str, Any]],
        sources: list[str],
        options: dict[str, Any],
    ) -> None:
        """Group the resolved moves into a plan and write it to --plan.

        :param records: audit rows, from this run or from saved reports
        :param sources: the report files the rows came from, for the record
        :param options: the command options
        :return: None
        """
        seen = {r["opinion_id"] for r in records}
        if len(seen) != len(records):
            raise CommandError(
                "The reports overlap; the same opinion appears twice."
            )
        plan = plan_cycles(records, options["min_confidence"])
        plan["generated_at"] = timezone.now().isoformat()
        plan["source_reports"] = sources
        plan["min_confidence"] = options["min_confidence"]

        output = Path(options["plan"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(plan, indent=2, default=str))
        logger.info("plan summary: %s", plan["summary"])
        logger.info(
            "Wrote %s cycles and %s chains to %s",
            len(plan["cycles"]),
            len(plan["chains"]),
            output,
        )
