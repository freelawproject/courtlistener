from __future__ import annotations

import re
from datetime import date

SCOTUS_COURT_ID = "scotus"

# Two parallel docket-number sequences per SCOTUS term year, identified by
# their serial range:
#   low:  YY-1    ... YY-~3000
#   high: YY-5001 ... YY-~12000
LOW_SEQUENCE = "low"
HIGH_SEQUENCE = "high"
SEQUENCES: tuple[str, ...] = (LOW_SEQUENCE, HIGH_SEQUENCE)

# Serial number one BELOW the first valid docket in each sequence. Used as
# the probe "watermark" when we haven't seen any case yet in a term: the
# probe will start at base + offset.
SEQUENCE_BASE: dict[str, int] = {
    LOW_SEQUENCE: 0,
    HIGH_SEQUENCE: 5000,
}

_DOCKET_NUMBER_RE = re.compile(r"^(\d{2})-(\d{1,6})$")

# Redis hash key that stores the latest probed serial per (sequence, term).
HIGHEST_KNOWN_HASH = "scotus:highest_known_serial"


def current_scotus_term_year(today: date) -> int:
    """Return the SCOTUS term year for ``today`` as a 2-digit int.

    SCOTUS terms start on July 1. The 2025 term, for example, begins
    2025-07-01 and ends 2026-06-30, so both 2025-10-15 and 2026-02-01
    resolve to term year 25.
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
    """
    return today.month >= 7


def parse_docket_number(dn: str) -> tuple[int, int]:
    """Parse a SCOTUS docket number such as ``25-150`` or ``25-5200``.

    Returns ``(term_year_2digit, serial)``. Raises ``ValueError`` on bad input.
    """
    match = _DOCKET_NUMBER_RE.match(dn.strip())
    if not match:
        raise ValueError(f"Unrecognized SCOTUS docket number: {dn!r}")
    return int(match.group(1)), int(match.group(2))


def format_docket_number(term_year_2digit: int, serial: int) -> str:
    """Format a docket number back to ``YY-N`` form (no leading zeros on N)."""
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
    """Hash field name for the highest-known serial per (sequence, term)."""
    if sequence not in SEQUENCES:
        raise ValueError(f"Unknown sequence: {sequence!r}")
    return f"{sequence}:{term_year_2digit:02d}"


def scotus_raw_s3_key(docket_number: str) -> str:
    """Build the S3 key for a raw docket JSON file.

    Follows the existing scraper convention in ``back_scrape_dockets.py``
    (``responses/dockets/{scraper}/...``). SCOTUS docket numbers are
    ``YY-N`` by construction and already encode the term, so we don't need
    any extra partitioning directory.
    """
    return f"responses/dockets/scotus/{docket_number}.json"
