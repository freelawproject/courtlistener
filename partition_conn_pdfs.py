"""Re-extract metadata and partition Connecticut Reports PDFs.

Reads partial-volume PDFs downloaded from the CT Judicial Branch website,
extracts per-opinion metadata (fixing bugs in the original extraction),
and splits each opinion into its own PDF file using PyPDF2.

Uses multiprocessing (1 process per PDF) for fast extraction.

Fixes over the original extract_conn_metadata.py:
- Expanded search window (10 pages instead of 3) to find dates that appear
  deep in long syllabus sections
- Added "Submitted on briefs", "Heard", and broken "offi cially" date patterns
- Added re.DOTALL to date regex for multi-line "Argued...released" spans
- Deduplicates docket numbers globally across files within a volume

Usage:
    python partition_conn_pdfs.py \
        --input-dir '/path/to/conn citations pdfs' \
        --output-dir /tmp/conn-partitioned \
        --metadata-out /tmp/conn-partitioned-metadata.json

    # Dry run (no PDF splitting, just metadata extraction + validation):
    python partition_conn_pdfs.py \
        --input-dir '/path/to/conn citations pdfs' \
        --metadata-out /tmp/conn-partitioned-metadata.json \
        --dry-run
"""

import argparse
import hashlib
import io
import json
import logging
import re
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence

import fitz  # PyMuPDF — for true redaction of preceding opinion text
import pdfplumber
from dateutil import parser as date_parser
from PyPDF2 import PdfReader, PdfWriter

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# Volume range for CAP gap opinions
MIN_VOLUME = 333
MAX_VOLUME = 999

# How many pages ahead to search for citation/date from the docket page.
# Some opinions have very long syllabus sections (6+ pages) before the
# "Argued...released" date line appears.
SEARCH_WINDOW = 10

# --- Regex patterns ---

REGEX_HEADER = re.compile(
    r"(?P<cite>\d+ Conn\.( App\.)? \d+)\s+[A-Z]+, 20\d{2}\s+(?P<page_number>\d+)\n(?P<name>.+)\n"
)
REGEX_HEADER_ALT = re.compile(
    r"(?P<page_number>\d+)\s+[A-Z]+, 20\d{2}\s+(?P<cite>\d+ Conn\.( App\.)? \d+)\n(?P<name>.+)\n"
)
REGEX_DATE = re.compile(
    r"(Argued .+(released|officially)"
    r"|offi\s*cially released"
    r"|officially released"
    r"|Submitted on briefs .+released"
    r"|Heard .+released),?\s+"
    r"(?P<date>[A-Z][a-z]+ \d+, \d{4})",
    re.DOTALL,
)
REGEX_DOCKET_AND_NAME = re.compile(
    r"(?P<name>\n{1,}?\s*[A-Z\d][A-Z0-9)(,.v \n*'&#:\u2019-]+)\n"
    r"\(?\s*(?P<docket>(?:SC|AC) [\d-]+)(\s*\n|\))"
)
REGEX_ORDER_START = re.compile(
    r"(?:Supreme|Appellate) Court Orders begin at page \d+|^[\n\s]*ORDERS\s*\n"
)

NOISE_PATTERNS = [
    "CASES ARGUED AND DETERMINED",
    "IN THE SUPREME COURT OF THE STATE OF CONNECTICUT",
    "IN THE APPELLATE COURT OF THE STATE OF CONNECTICUT",
]

EXTRACT_TEXT_KWARGS = {"keep_blank_chars": True, "x_tolerance": 1}


def _clean_case_name(raw_name: str) -> str:
    name = re.sub(r"[\s\n]+", " ", raw_name).strip("* ")
    for noise in NOISE_PATTERNS:
        name = name.replace(noise, "")
    return name.strip()


def _citation_slug(citation: str) -> str:
    """Convert '345 Conn. 174' to '345_conn_174'."""
    return re.sub(r"[.\s]+", "_", citation.lower()).strip("_")


def extract_opinions_from_pdf(pdf_path: Path, pages_text: Sequence[str | None]) -> list[dict]:
    """Extract opinion metadata from pre-read PDF pages."""
    opinions: list[dict] = []
    seen_dockets: set[str] = set()
    is_partial = "full_volume" not in pdf_path.name

    for page_idx, page in enumerate(pages_text):
        if not page:
            continue

        if not is_partial and REGEX_ORDER_START.search(page):
            break

        docket_match = REGEX_DOCKET_AND_NAME.search(page)
        if not docket_match:
            continue

        docket = docket_match.group("docket")
        if docket in seen_dockets:
            continue
        seen_dockets.add(docket)

        name = _clean_case_name(docket_match.group("name"))

        if len(name) < 5:
            direct_match = re.search(
                r"(?P<name>[A-Z][A-Z .,'&*\d\u2019-]+v\.\s+[A-Z][A-Z .,'&*\d\n\u2019-]+)\n"
                rf"\(?\s*{re.escape(docket)}",
                page,
            )
            if direct_match:
                name = direct_match.group("name").strip("* ")
            else:
                continue

        if re.search(r"THE .+ APPEAL", name):
            continue

        # Citation
        citation = None
        short_name = None
        for nearby_page in pages_text[page_idx : min(page_idx + SEARCH_WINDOW, len(pages_text))]:
            if not nearby_page:
                continue
            if header_match := REGEX_HEADER.search(nearby_page):
                citation = header_match.group("cite")
                short_name = header_match.group("name")
                break
            elif header_match := REGEX_HEADER_ALT.search(nearby_page):
                citation = header_match.group("cite")
                short_name = header_match.group("name")
                break

        if not citation:
            continue

        # Date
        date_str = None
        for nearby_page in pages_text[page_idx : min(page_idx + SEARCH_WINDOW, len(pages_text))]:
            if not nearby_page:
                continue
            if date_match := REGEX_DATE.search(nearby_page):
                date_str = date_match.group("date")
                break

        if not date_str:
            logger.warning(
                "%s page %d: docket %s (%s) — no date found",
                pdf_path.name, page_idx, docket, citation,
            )
            continue

        try:
            date_filed = date_parser.parse(date_str)
        except (ValueError, OverflowError):
            continue

        opinions.append({
            "case_name": name,
            "case_name_short": short_name or "",
            "date_filed": date_filed.strftime("%Y-%m-%d"),
            "docket_number": docket,
            "citation": citation,
            "source_file": pdf_path.name,
            "original_source_file": pdf_path.name,
            "page_start": page_idx,
        })

    # Hardcoded shared-page overrides for edge cases where the heuristic
    # fails because the preceding opinion's ending is very short (<10%
    # of page text).  Key = citation that needs page_end extended.
    FORCE_SHARED_PAGE: set[str] = {
        "335 Conn. 300",
        "336 Conn. 386",
        "341 Conn. 463",
        "342 Conn. 25",
        "345 Conn. 354",
        "350 Conn. 393",
    }
    # False positives: the heuristic thinks the page is shared but the
    # next opinion actually starts at the top of its own page (e.g.,
    # consolidated cases with multiple docket numbers pushing the
    # primary docket past 10%).
    FORCE_NOT_SHARED: set[str] = {
        "343 Conn. 62",   # next (343 Conn. 88) starts clean
        "349 Conn. 619",  # next (349 Conn. 647) starts clean (consolidated dockets)
    }

    # Compute page_end.  When the next opinion starts mid-page (its
    # docket doesn't appear near the top of the page text), include
    # that shared page so this opinion keeps its concluding text.
    # The next opinion's content will be redacted from that page later.
    total_pages = len(pages_text)
    for i, op in enumerate(opinions):
        if i + 1 >= len(opinions):
            op["page_end"] = total_pages - 1
            continue

        next_op = opinions[i + 1]
        shared_page_text = pages_text[next_op["page_start"]] or ""

        # Detect a shared page: the next opinion's docket appears
        # after body text from the current opinion.  We use text
        # position as a proxy for y-coordinate (>10% into the page
        # text means there's content above it beyond just the page
        # header).
        docket_pos = shared_page_text.find(next_op["docket_number"])
        page_is_shared = (
            (
                docket_pos > 0
                and docket_pos / max(len(shared_page_text), 1) > 0.10
            )
            or op["citation"] in FORCE_SHARED_PAGE
        ) and op["citation"] not in FORCE_NOT_SHARED

        if page_is_shared:
            op["page_end"] = next_op["page_start"]
        else:
            op["page_end"] = next_op["page_start"] - 1

    return opinions


def _process_single_pdf(pdf_path_str: str) -> list[dict]:
    """Worker function for multiprocessing: extract opinions from one PDF.

    Takes a string path (for pickling) and returns the opinion list.
    """
    pdf_path = Path(pdf_path_str)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_text = [
                p.extract_text(**EXTRACT_TEXT_KWARGS) for p in pdf.pages
            ]
    except Exception:
        return []

    return extract_opinions_from_pdf(pdf_path, pages_text)


def split_pdf(
    source_path: Path,
    page_start: int,
    page_end: int,
    output_path: Path,
) -> str:
    """Extract pages [page_start, page_end] from source PDF into output.

    :return: SHA1 hex digest of the output PDF bytes.
    """
    reader = PdfReader(str(source_path))
    writer = PdfWriter()
    for page_num in range(page_start, min(page_end + 1, len(reader.pages))):
        writer.add_page(reader.pages[page_num])
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()
    with open(output_path, "wb") as f:
        f.write(pdf_bytes)
    return hashlib.sha1(pdf_bytes).hexdigest()


def verify_output_pdf(
    output_path: Path,
    expected_citation: str,
    expected_docket: str,
) -> bool:
    """Verify the first page of the output PDF contains the expected citation or docket."""
    try:
        with pdfplumber.open(output_path) as pdf:
            if not pdf.pages:
                return False
            text = pdf.pages[0].extract_text(**EXTRACT_TEXT_KWARGS) or ""
            return expected_citation in text or expected_docket in text
    except Exception:
        return False


# Minimum y-coordinate (pdfplumber, top-down) for the case name to
# indicate there's preceding text worth redacting.  Below this threshold
# the content above the case name is just the page header, not opinion text.
MIN_REDACT_Y = 200


def _is_case_name_line(text: str) -> bool:
    """Check if a line is part of an ALL-CAPS case name block."""
    stripped = text.strip()
    if not stripped:
        return False
    alpha_count = sum(1 for c in stripped if c.isalpha())
    if alpha_count == 0:
        return False
    upper_count = sum(1 for c in stripped if c.isupper())
    return upper_count / alpha_count > 0.85


def _find_opinion_start_y(
    page,  # pdfplumber Page
    docket_number: str,
) -> float | None:
    """Find the y-coordinate where the opinion's case name block starts.

    Searches for the docket number on the page, then walks upward
    through ALL-CAPS lines (the multi-line case name) to find the
    topmost line of the case name block.

    :return: pdfplumber y-coordinate (top-down) or None if not found.
    """
    results = page.search(re.escape(docket_number))
    if not results:
        return None
    docket_y = results[0]["top"]

    lines = page.extract_text_lines(return_chars=True)

    case_start_y = docket_y
    for line in reversed(lines):
        if line["top"] >= docket_y:
            continue
        if _is_case_name_line(line["text"]):
            case_start_y = line["top"]
        else:
            break

    return case_start_y


def redact_preceding_text(pdf_path: Path, docket_number: str) -> bool:
    """Redact text from preceding opinion on the first page of a split PDF.

    Uses PyMuPDF to truly remove text (not just visually hide it),
    so downstream text extraction won't pick up the preceding opinion.

    :return: True if redaction was applied, False if not needed.
    """
    with pdfplumber.open(pdf_path) as pdf:
        start_y = _find_opinion_start_y(pdf.pages[0], docket_number)

    if start_y is None or start_y < MIN_REDACT_Y:
        return False

    tmp_path = str(pdf_path) + ".tmp"
    doc = fitz.open(pdf_path)
    fitz_page = doc[0]
    redact_rect = fitz.Rect(0, 0, fitz_page.rect.width, start_y)
    fitz_page.add_redact_annot(redact_rect, fill=[1, 1, 1])
    fitz_page.apply_redactions()
    doc.save(tmp_path, deflate=True)
    doc.close()
    Path(tmp_path).replace(pdf_path)
    return True


def redact_following_text(pdf_path: Path, next_docket_number: str) -> bool:
    """Redact the next opinion's text from the last page of a split PDF.

    Mirror of redact_preceding_text: finds where the next opinion's case
    name block starts on the last page, and redacts everything from there
    to the bottom of the page.

    :return: True if redaction was applied, False if not needed.
    """
    with pdfplumber.open(pdf_path) as pdf:
        last_page = pdf.pages[-1]
        start_y = _find_opinion_start_y(last_page, next_docket_number)
        page_height = last_page.height

        # Find the lowest header separator on the last page.  The page
        # header block (CT Law Journal line, citation header, short case
        # name) spans three horizontal separators in the top ~180pt.
        # We redact everything up to the last separator in that block.
        h_lines = sorted(
            [
                line
                for line in last_page.lines
                if abs(line["top"] - line["bottom"]) < 1
                and line["top"] < 200  # only separators in the header region
            ],
            key=lambda line: line["top"],
        )
        last_header_separator_y = (
            h_lines[-1]["top"] if h_lines else None
        )

    if start_y is None:
        return False

    tmp_path = str(pdf_path) + ".tmp"
    doc = fitz.open(pdf_path)
    last_fitz_page = doc[-1]

    # Redact the next opinion's body text (case name block to bottom)
    body_rect = fitz.Rect(0, start_y, last_fitz_page.rect.width, page_height)
    last_fitz_page.add_redact_annot(body_rect, fill=[1, 1, 1])

    # Redact the page header (everything up to the last header separator)
    if last_header_separator_y is not None:
        header_rect = fitz.Rect(
            0, 0, last_fitz_page.rect.width, last_header_separator_y + 2
        )
        last_fitz_page.add_redact_annot(header_rect, fill=[1, 1, 1])

    last_fitz_page.apply_redactions()
    doc.save(tmp_path, deflate=True)
    doc.close()
    Path(tmp_path).replace(pdf_path)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-extract and partition Connecticut Reports PDFs."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Directory containing downloaded partial-volume PDFs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for partitioned single-opinion PDFs.",
    )
    parser.add_argument(
        "--metadata-out",
        type=Path,
        required=True,
        help="Path for the output metadata JSON.",
    )
    parser.add_argument(
        "--old-metadata",
        type=Path,
        help="Path to old metadata JSON for comparison.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only extract metadata and validate, don't split PDFs.",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.output_dir:
        logger.error("--output-dir is required unless --dry-run is set")
        sys.exit(1)

    # Collect all volume 333+ PDFs
    pdf_files = sorted(args.input_dir.glob("*.pdf"))
    vol_files: dict[int, list[Path]] = defaultdict(list)
    for pdf_path in pdf_files:
        vol_match = re.search(r"vol\.(\d+)", pdf_path.name)
        if not vol_match:
            continue
        vol = int(vol_match.group(1))
        if vol < MIN_VOLUME:
            continue
        vol_files[vol].append(pdf_path)

    all_pdf_paths = [
        p for vol in sorted(vol_files) for p in sorted(vol_files[vol])
    ]
    logger.info(
        "Found %d volumes (%d-%d) with %d PDF files — extracting in parallel",
        len(vol_files),
        min(vol_files) if vol_files else 0,
        max(vol_files) if vol_files else 0,
        len(all_pdf_paths),
    )

    # --- Parallel extraction: 1 process per PDF ---
    pdf_to_opinions: dict[str, list[dict]] = {}
    with ProcessPoolExecutor() as executor:
        future_to_path = {
            executor.submit(_process_single_pdf, str(p)): p
            for p in all_pdf_paths
        }
        done_count = 0
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            done_count += 1
            try:
                result = future.result()
                pdf_to_opinions[path.name] = result
            except Exception:
                logger.exception("Worker failed for %s", path.name)
                pdf_to_opinions[path.name] = []

            if done_count % 50 == 0:
                logger.info("Extracted %d/%d PDFs...", done_count, len(all_pdf_paths))

    logger.info("Extraction complete for all %d PDFs", len(all_pdf_paths))

    # --- Assemble results by volume, deduplicating ---
    all_opinions: list[dict] = []
    global_dockets: set[str] = set()
    duplicate_dockets: list[tuple[str, str, str]] = []
    vol_stats: dict[int, int] = {}

    for vol in sorted(vol_files):
        vol_opinions: list[dict] = []
        vol_seen_dockets: set[str] = set()

        for pdf_path in sorted(vol_files[vol]):
            opinions = pdf_to_opinions.get(pdf_path.name, [])

            for op in opinions:
                if op["docket_number"] in vol_seen_dockets:
                    logger.info(
                        "Duplicate docket %s in vol %d (from %s), skipping",
                        op["docket_number"], vol, pdf_path.name,
                    )
                    continue
                vol_seen_dockets.add(op["docket_number"])

                if op["docket_number"] in global_dockets:
                    duplicate_dockets.append(
                        (op["docket_number"], op["citation"], pdf_path.name)
                    )
                global_dockets.add(op["docket_number"])
                vol_opinions.append(op)

        vol_stats[vol] = len(vol_opinions)
        all_opinions.extend(vol_opinions)
        logger.info("Vol %d: %d opinions", vol, len(vol_opinions))

    # --- Validation ---
    logger.info("\n=== VALIDATION ===")
    logger.info("Total opinions extracted: %d", len(all_opinions))

    cite_counts: dict[str, int] = defaultdict(int)
    for op in all_opinions:
        cite_counts[op["citation"]] += 1
    dup_cites = {c: n for c, n in cite_counts.items() if n > 1}
    if dup_cites:
        logger.warning("Duplicate citations: %s", dup_cites)

    if duplicate_dockets:
        logger.warning(
            "Dockets appearing in multiple volumes: %s", duplicate_dockets
        )

    # Compare with old metadata if provided
    if args.old_metadata and args.old_metadata.exists():
        with open(args.old_metadata) as f:
            old_data = json.load(f)
        old_counts: dict[int, int] = defaultdict(int)
        for op in old_data:
            v = int(op["citation"].split()[0])
            if v >= MIN_VOLUME:
                old_counts[v] += 1
        old_total = sum(old_counts.values())

        logger.info("\nComparison with old metadata:")
        logger.info("Old total: %d, New total: %d", old_total, len(all_opinions))
        for vol in sorted(set(list(vol_stats) + list(old_counts))):
            old = old_counts.get(vol, 0)
            new = vol_stats.get(vol, 0)
            if new < old:
                logger.warning("Vol %d DECREASED: %d -> %d", vol, old, new)
            elif new != old:
                logger.info("Vol %d: %d -> %d (+%d)", vol, old, new, new - old)

    # Check for known missing opinion
    found_taijha = any("20151" in op["docket_number"] for op in all_opinions)
    if found_taijha:
        logger.info("SC 20151 (IN RE TAIJHA): FOUND")
    else:
        logger.warning("SC 20151 (IN RE TAIJHA): MISSING")

    # --- PDF splitting ---
    if args.dry_run:
        logger.info("Dry run — skipping PDF splitting")
    else:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        output_filenames: set[str] = set()
        verify_failures: list[str] = []
        sha1_to_opinions: dict[str, list[str]] = defaultdict(list)
        redact_count = 0

        for idx, op in enumerate(all_opinions):
            slug = _citation_slug(op["citation"])
            output_name = f"{slug}.pdf"

            if output_name in output_filenames:
                output_name = f"{slug}_{op['docket_number'].replace(' ', '_')}.pdf"
            output_filenames.add(output_name)

            source_path = args.input_dir / op["source_file"]
            output_path = args.output_dir / output_name

            sha1_hash = split_pdf(source_path, op["page_start"], op["page_end"], output_path)

            # Redact preceding opinion text from first page
            first_redacted = redact_preceding_text(output_path, op["docket_number"])
            if first_redacted:
                redact_count += 1

            # Redact following opinion text from last page (shared page)
            last_redacted = False
            if idx + 1 < len(all_opinions):
                next_op = all_opinions[idx + 1]
                # Only if they share a source file and this opinion's
                # page_end == next opinion's page_start (shared page)
                if (
                    op["original_source_file"] == next_op["original_source_file"]
                    and op["page_end"] == next_op["page_start"]
                ):
                    last_redacted = redact_following_text(
                        output_path, next_op["docket_number"]
                    )
                    if last_redacted:
                        redact_count += 1

            # Recompute SHA1 after any redaction
            if first_redacted or last_redacted:
                sha1_hash = hashlib.sha1(output_path.read_bytes()).hexdigest()

            op["needs_first_page_redaction"] = first_redacted
            op["needs_last_page_redaction"] = last_redacted
            op["source_file"] = output_name
            op["sha1"] = sha1_hash
            sha1_to_opinions[sha1_hash].append(op["citation"])

            if not verify_output_pdf(output_path, op["citation"], op["docket_number"]):
                verify_failures.append(
                    f"{output_name} (expected {op['citation']} / {op['docket_number']})"
                )

        logger.info(
            "Split %d PDFs into %s (%d redaction operations)",
            len(all_opinions), args.output_dir, redact_count,
        )

        # Check for duplicate SHA1 hashes
        dup_sha1s = {h: cites for h, cites in sha1_to_opinions.items() if len(cites) > 1}
        if dup_sha1s:
            logger.warning("Duplicate SHA1 hashes (%d):", len(dup_sha1s))
            for h, cites in dup_sha1s.items():
                logger.warning("  %s: %s", h, cites)
        else:
            logger.info("All %d output PDFs have unique SHA1 hashes", len(all_opinions))

        if verify_failures:
            logger.warning("Verification failures (%d):", len(verify_failures))
            for f in verify_failures:
                logger.warning("  %s", f)
        else:
            logger.info("All output PDFs passed verification")

    # --- Sanity check: redaction consistency for consecutive opinions ---
    redaction_mismatches = []
    for idx in range(len(all_opinions) - 1):
        op = all_opinions[idx]
        next_op = all_opinions[idx + 1]

        if op["original_source_file"] != next_op["original_source_file"]:
            continue

        if op.get("needs_last_page_redaction") and not next_op.get(
            "needs_first_page_redaction"
        ):
            redaction_mismatches.append(
                f"{op['citation']} has last-page redaction but next "
                f"{next_op['citation']} has NO first-page redaction"
            )
        if next_op.get("needs_first_page_redaction") and not op.get(
            "needs_last_page_redaction"
        ):
            redaction_mismatches.append(
                f"{next_op['citation']} has first-page redaction but prev "
                f"{op['citation']} has NO last-page redaction"
            )

    if redaction_mismatches:
        logger.warning(
            "Redaction consistency mismatches (%d):",
            len(redaction_mismatches),
        )
        for m in redaction_mismatches:
            logger.warning("  %s", m)
    else:
        logger.info("Redaction consistency check passed")

    # --- Sanity check: last-page header should be redacted (not show
    # the next opinion's citation).  Only checks for the specific next
    # opinion's citation, ignoring unrelated citations that appear in
    # body text or footnotes.
    if not args.dry_run:
        foreign_header_issues: list[str] = []

        for idx in range(len(all_opinions) - 1):
            op = all_opinions[idx]
            if not op.get("needs_last_page_redaction"):
                continue

            next_cite = all_opinions[idx + 1]["citation"]
            output_path = args.output_dir / op["source_file"]
            with pdfplumber.open(output_path) as pdf:
                last_page = pdf.pages[-1]
                text = (
                    last_page.extract_text(**EXTRACT_TEXT_KWARGS) or ""
                )
                header_text = "\n".join(text.split("\n")[:3])
                if next_cite in header_text:
                    foreign_header_issues.append(
                        f"{op['source_file']} last page: "
                        f"header still has {next_cite}"
                    )

        if foreign_header_issues:
            logger.warning(
                "Foreign last-page header citations (%d):",
                len(foreign_header_issues),
            )
            for issue in foreign_header_issues:
                logger.warning("  %s", issue)
        else:
            logger.info(
                "Last-page header check passed for all redacted PDFs"
            )

    # Write metadata
    args.metadata_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.metadata_out, "w") as f:
        json.dump(all_opinions, f, indent=2)
    logger.info("Wrote metadata to %s", args.metadata_out)


if __name__ == "__main__":
    main()
