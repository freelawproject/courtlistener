from __future__ import annotations

import json
from datetime import date
from http import HTTPStatus

import requests
from django.core.files.base import ContentFile

from cl.lib.storage import (
    S3GlacierInstantRetrievalStorage,
    clobbering_get_name,
)

SCOTUS_COURT_ID = "scotus"
SCOTUS_JSON_URL_TEMPLATE = (
    "https://www.supremecourt.gov/RSS/Cases/JSON/{docket_number}.json"
)

# Three parallel docket-number sequences per SCOTUS term year:
#   low:          YY-1    ... YY-~3000
#   high:         YY-5001 ... YY-~12000
#   applications: YYA1    ... YYA~2000  (e.g. 24A1088)
LOW_SEQUENCE = "low"
HIGH_SEQUENCE = "high"
APPLICATIONS_SEQUENCE = "applications"
SEQUENCES: tuple[str, ...] = (
    LOW_SEQUENCE,
    HIGH_SEQUENCE,
    APPLICATIONS_SEQUENCE,
)

# Serial number one BELOW the first valid docket in each sequence. Used as
# the probe "watermark" when we haven't seen any case yet in a term: the
# probe will start at base + offset.
SEQUENCE_BASE: dict[str, int] = {
    LOW_SEQUENCE: 0,
    HIGH_SEQUENCE: 5000,
    APPLICATIONS_SEQUENCE: 0,
}

# Redis hash key that stores the latest probed serial per (sequence, term).
HIGHEST_SCOTUS_KNOWN_SERIAL = "scotus:highest_known_serial"


def current_scotus_term_year(today: date) -> int:
    """Return the SCOTUS term year for ``today`` as a 2-digit int.

    SCOTUS terms start on July 1. The 2025 term, for example, begins
    2025-07-01 and ends 2026-06-30, so both 2025-10-15 and 2026-02-01
    resolve to term year 25.

    :param today: The date to compute the term year for.
    :return: The 2-digit SCOTUS term year (e.g. ``25`` for the 2025 term).
    """
    year = today.year if today.month >= 7 else today.year - 1
    return year % 100


def next_term_starts_probing(today: date) -> bool:
    """Return True while we should also probe candidate dockets for the NEXT
    term year.

    SCOTUS cuts the new term on July 1, but the very first docket numbers
    sometimes trickle in over the following days/weeks. Between July 1 and
    December 31 we probe both the current term and ``term + 1`` so we don't
    miss the rollover moment.

    :param today: The date to check.
    :return: Whether next-term probing should be active.
    """
    return today.month >= 7


def format_docket_number(
    term_year_2digit: int, serial: int, sequence: str = LOW_SEQUENCE
) -> str:
    """Format a docket number for the given sequence.

    Low/high sequences use ``YY-N`` form (e.g. ``"25-150"``).
    Applications use ``YYAN`` form (e.g. ``"24A1088"``).

    :param term_year_2digit: The 2-digit SCOTUS term year (e.g. ``25``).
    :param serial: The docket serial number.
    :param sequence: The docket-number sequence (``"low"``, ``"high"``, or
        ``"applications"``).
    :return: The formatted docket number.
    """
    if sequence == APPLICATIONS_SEQUENCE:
        return f"{term_year_2digit:02d}A{serial}"
    return f"{term_year_2digit:02d}-{serial}"


def scotus_court_wait_key() -> str:
    """Redis key (with TTL) that pauses the daemon while set."""
    return "scotus:court_wait"


def scotus_blocked_attempts_key() -> str:
    """Counter key used by the exponential-backoff path."""
    return "scotus:court_blocked_attempts"


def scotus_empty_probe_attempts_key() -> str:
    """Counter key used by the empty-probe staleness alert."""
    return "scotus:court_empty_probe_attempts"


def scotus_highest_known_field(sequence: str, term_year_2digit: int) -> str:
    """Hash field name for the highest-known serial per (sequence, term).

    :param sequence: The docket-number sequence (``"low"`` or ``"high"``).
    :param term_year_2digit: The 2-digit SCOTUS term year (e.g. ``25``).
    :return: The Redis hash field name (e.g. ``"low:25"``).
    """
    if sequence not in SEQUENCES:
        raise ValueError(f"Unknown sequence: {sequence!r}")
    return f"{sequence}:{term_year_2digit:02d}"


def fetch_scotus_docket_json(
    docket_number: str,
) -> tuple[str | None, int]:
    """Fetch a SCOTUS docket JSON file.

    :param docket_number: A SCOTUS docket number (e.g. ``25-150``).
    :return: ``(content_text, http_status)``. ``content_text`` is ``None`` for
        404 responses or for 200 responses that don't contain valid JSON.
    :raises HTTPError: For non-404 4xx/5xx responses. The caller relies on this
        to trigger exponential backoff, matching the iquery probe semantics.
    """
    url = SCOTUS_JSON_URL_TEMPLATE.format(docket_number=docket_number)
    resp = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Free Law Project"},
    )
    if resp.status_code == HTTPStatus.NOT_FOUND:
        return None, HTTPStatus.NOT_FOUND
    resp.raise_for_status()
    text = resp.text.strip()
    # SCOTUS sometimes returns an empty body or an HTML error page with HTTP 200.
    try:
        json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None, resp.status_code
    return text, resp.status_code


def save_scotus_raw_to_s3(docket_number: str, content: str) -> None:
    """Upload a raw SCOTUS docket JSON to S3.
    :param docket_number: A SCOTUS docket number.
    :param content: Content to be uploaded.
    :return: None
    """
    storage = S3GlacierInstantRetrievalStorage(
        naming_strategy=clobbering_get_name
    )
    file_name = f"responses/dockets/scotus/{docket_number}.json"
    storage.save(file_name, ContentFile(content.encode("utf-8")))
