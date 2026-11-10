# Issue #8100. Paste this whole file into `python manage.py shell`.
# The paste only runs a dry run. It writes nothing and downloads only the CSV.
# If the dry run output matches the expected line, type: apply()
# apply() needs Celery workers: it queues version merging and citation tasks.
import csv
import io
import re
from datetime import date
from typing import Any

import httpx
from django.core.files.base import ContentFile
from django.db import transaction

from cl.lib.crypto import sha1
from cl.lib.string_utils import trunc
from cl.scrapers.tasks import extract_opinion_content
from cl.scrapers.utils import check_duplicate_ingestion
from cl.search.models import PRECEDENTIAL_STATUS, Opinion

CSV_URL = "https://github.com/user-attachments/files/34002436/repair_input.csv"
CA4_MODULE = "juriscraper.opinions.united_states.federal_appellate.ca4"
COLUMNS = {
    "opinion_id",
    "expected_download_url",
    "expected_sha1",
    "new_download_url",
    "expected_status",
}
# GovInfo answers a bad granule with an HTML page and HTTP 200.
PDF_MAGIC = b"%PDF-"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
GRANULE_URL_RE = re.compile(
    r"^https://www\.govinfo\.gov/content/pkg/"
    r"(?P<package>[A-Za-z0-9-]+?)/pdf/(?P=package)-(?P<part>\d+)\.pdf$"
)
FILED_RE = re.compile(r"Filed:\s*(\d{2})/(\d{2})/(\d{4})")
PUBLISHED_RE = re.compile(r"\bPUBLISHED\b")
UNPUBLISHED_RE = re.compile(r"\bUNPUBLISHED\b")
STATUSES = {PRECEDENTIAL_STATUS.PUBLISHED, PRECEDENTIAL_STATUS.UNPUBLISHED}
STAT_KEYS = [
    "replaced",
    "text_finished",
    "url_corrected",
    "already_correct",
    "skipped_mismatch",
    "missing",
    "download_failed",
    "extraction_failed",
    "status_corrected",
    "status_undetermined",
    "status_disputed",
]


def derive_status(text: str) -> str:
    """Read the status banner the way the pre-fix ca4.py did, or ''."""
    if PUBLISHED_RE.search(text):
        return PRECEDENTIAL_STATUS.PUBLISHED
    if UNPUBLISHED_RE.search(text):
        return PRECEDENTIAL_STATUS.UNPUBLISHED
    return ""


def text_filing_date(text: str) -> date | None:
    """Return the "Filed:" date CA4 stamps on each page, if readable."""
    if not (match := FILED_RE.search(text or "")):
        return None
    month, day, year = (int(g) for g in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def text_is_stale(opinion: Opinion) -> bool:
    """Whether the stored text belongs to another decision.

    This finds a record whose file was swapped but whose extraction failed.
    """
    if not opinion.plain_text:
        return True
    stamped = text_filing_date(opinion.plain_text)
    return stamped is not None and stamped != opinion.cluster.date_filed


def parse_row(raw: dict[str, str]) -> dict[str, Any]:
    """Validate one CSV row. Raises ValueError on a bad row."""
    old_url = raw["expected_download_url"].strip()
    new_url = raw["new_download_url"].strip()
    old_match = GRANULE_URL_RE.match(old_url)
    new_match = GRANULE_URL_RE.match(new_url)
    status = raw["expected_status"].strip()
    if not old_match or not new_match:
        raise ValueError("not a GovInfo granule URL")
    if old_match["package"] != new_match["package"]:
        raise ValueError("old and new URL are different packages")
    if new_match["part"] == "0" or old_url == new_url:
        raise ValueError("new URL is part 0 or equal to the old URL")
    if not SHA1_RE.match(raw["expected_sha1"].strip()):
        raise ValueError("bad sha1")
    if status and status not in STATUSES:
        raise ValueError(f"bad status {status!r}")
    return {
        "opinion_id": int(raw["opinion_id"]),
        "expected_download_url": old_url,
        "expected_sha1": raw["expected_sha1"].strip(),
        "new_download_url": new_url,
        "expected_status": status,
    }


def load_rows() -> list[dict[str, Any]]:
    """Download and validate the whole CSV before any row runs."""
    response = httpx.get(CSV_URL, follow_redirects=True, timeout=60)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text))
    if missing := COLUMNS - set(reader.fieldnames or []):
        raise ValueError(f"CSV is missing columns: {sorted(missing)}")
    rows = []
    for n, raw in enumerate(reader, start=2):
        try:
            rows.append(parse_row(raw))
        except (ValueError, KeyError, AttributeError) as e:
            raise ValueError(f"CSV line {n}: {e}") from e
    ids = [r["opinion_id"] for r in rows]
    if not rows or len(ids) != len(set(ids)):
        raise ValueError("CSV is empty or has a duplicate opinion_id")
    return rows


def find_merge_conflicts(rows: list[dict[str, Any]]) -> list[tuple]:
    """Find other opinions that already hold a replacement URL.

    Extraction merges opinions with the same download_url, and a merge
    cannot be undone, so run() stops if this is not empty.
    """
    return list(
        Opinion.objects.filter(
            download_url__in=[r["new_download_url"] for r in rows]
        )
        .exclude(pk__in=[r["opinion_id"] for r in rows])
        .values_list("pk", "download_url")
    )


def fetch_pdf(client: httpx.Client, url: str) -> bytes:
    """Download a GovInfo PDF. Raises ValueError if the body is not a PDF."""
    response = client.get(url, follow_redirects=True, timeout=60)
    response.raise_for_status()
    if not response.content.startswith(PDF_MAGIC):
        raise ValueError(f"{url} did not return a PDF")
    return response.content


def correct_status(
    opinion_id: int, row: dict[str, Any], stats: dict[str, int]
) -> None:
    """Set precedential_status from the new text, if GovInfo agrees."""
    # Reload, because extraction saved its own copy of the row.
    opinion = Opinion.objects.select_related("cluster").get(pk=opinion_id)
    stored = opinion.cluster.precedential_status
    if text_is_stale(opinion) or not (
        status := derive_status(opinion.plain_text)
    ):
        stats["status_undetermined"] += 1
        return
    if row["expected_status"] and status != row["expected_status"]:
        stats["status_disputed"] += 1
        print(
            f"Opinion {opinion_id}: PDF says {status}, GovInfo says "
            f"{row['expected_status']}. Status left alone."
        )
        return
    if status == stored:
        return
    opinion.cluster.precedential_status = status
    # save(), not update(), so post_save updates Elasticsearch.
    opinion.cluster.save(
        update_fields=["precedential_status", "date_modified"]
    )
    stats["status_corrected"] += 1


def extract_and_set_status(
    opinion_id: int, row: dict[str, Any], stats: dict[str, int]
) -> None:
    """Re-extract the text, then correct the status."""
    try:
        extract_opinion_content(
            pk=opinion_id, juriscraper_module=CA4_MODULE, ocr_available=True
        )
    except Exception as e:
        # The file is saved but the text is not. Another apply() finishes it.
        stats["extraction_failed"] += 1
        print(f"Opinion {opinion_id}: extraction failed: {e}")
        return
    correct_status(opinion_id, row, stats)


def process_row(
    row: dict[str, Any],
    client: httpx.Client,
    dry_run: bool,
    stats: dict[str, int],
) -> None:
    """Repair one opinion, or count why it was left alone."""
    opinion_id = row["opinion_id"]
    opinion = (
        Opinion.objects.select_related("cluster").filter(pk=opinion_id).first()
    )
    if not opinion:
        stats["missing"] += 1
        return
    if opinion.download_url == row["new_download_url"]:
        if not text_is_stale(opinion):
            stats["already_correct"] += 1
            return
        stats["text_finished"] += 1
        if not dry_run:
            extract_and_set_status(opinion_id, row, stats)
        return
    if (
        opinion.download_url != row["expected_download_url"]
        or opinion.sha1 != row["expected_sha1"]
    ):
        # The database changed since the audit, so the CSV row is stale.
        stats["skipped_mismatch"] += 1
        print(f"Opinion {opinion_id}: changed since the audit. Skipped.")
        return
    if dry_run:
        stats["replaced"] += 1
        return
    try:
        content = fetch_pdf(client, row["new_download_url"])
    except (httpx.HTTPError, ValueError) as e:
        stats["download_failed"] += 1
        print(f"Opinion {opinion_id}: download failed: {e}")
        return
    if sha1(content) == opinion.sha1:
        # Same bytes at both granules, so only the URL is wrong.
        opinion.download_url = row["new_download_url"]
        opinion.save(update_fields=["download_url", "date_modified"])
        stats["url_corrected"] += 1
        correct_status(opinion_id, row, stats)
        return
    file_name = f"{trunc(opinion.cluster.case_name.lower(), 75)}.pdf"
    with transaction.atomic():
        # A new file keeps the old PDF in storage, so a revert stays possible.
        opinion.local_path.save(file_name, ContentFile(content), save=False)
        check_duplicate_ingestion(opinion.local_path.name)
        opinion.download_url = row["new_download_url"]
        opinion.sha1 = sha1(content)
        opinion.save(
            update_fields=[
                "local_path",
                "download_url",
                "sha1",
                "date_modified",
            ]
        )
    stats["replaced"] += 1
    extract_and_set_status(opinion_id, row, stats)


def run(dry_run: bool) -> dict[str, int] | None:
    """Process every CSV row. Stops before any row if there are conflicts."""
    rows = load_rows()
    if conflicts := find_merge_conflicts(rows):
        print(f"STOP. {len(conflicts)} merge conflicts: {conflicts}")
        return None
    stats = dict.fromkeys(STAT_KEYS, 0)
    with httpx.Client() as client:
        for i, row in enumerate(rows, start=1):
            process_row(row, client, dry_run, stats)
            if i % 25 == 0:
                print(f"{i} of {len(rows)}")
    print("DRY RUN, nothing written." if dry_run else "DONE.")
    print(stats)
    return stats


def apply() -> dict[str, int] | None:
    """Run the repair for real."""
    return run(dry_run=False)


stats = run(dry_run=True)
print("Expected: replaced=112, all else 0. If so, type: apply()")
