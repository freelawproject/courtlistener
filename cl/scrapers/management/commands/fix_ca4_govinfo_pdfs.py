"""Replace the wrong GovInfo PDF on historical ca4 opinions.

See https://github.com/freelawproject/courtlistener/issues/8100. Before
juriscraper commit edc14983 (2025-05-22), ca4.py built every download URL as
`.../{package_id}-0.pdf`. A GovInfo package holds one PDF per granule, so when
the search returned a row for a later granule the scraper still stored part 0.
The cluster then carries the later decision's date with the earlier decision's
text.

The scraper also derived precedential_status in `extract_from_text`, by reading
the downloaded PDF for PUBLISHED or UNPUBLISHED. The wrong PDF therefore
produced the wrong status as well. Today's ca4.py has no `extract_from_text`;
it takes the status from the GovInfo search row instead. Re-extraction alone
therefore cannot repair the stored value, so this command re-applies the old
rule to the replacement PDF and checks the result against the audited GovInfo
metadata before writing it.

The CSV is the source of truth and comes from a separate offline audit that
resolves each record against the package's MODS metadata. This command only
applies it, so the mapping can be reviewed before anything is written. Records
whose correct granule is not an opinion are excluded by that audit and are not
repaired here.

Every row records the download_url and sha1 it expects to replace. A row whose
stored values no longer match is skipped rather than overwritten, so a stale CSV
cannot clobber newer data.

The replacement is written as a new file rather than over the existing
local_path key. The superseded PDF stays in storage, which is what makes a
revert possible. Note that reverting the three stored fields does not undo a
version merge; see the pre-flight note below.

PRE-FLIGHT, required before a production run: `extract_opinion_content` chains
`find_and_merge_versions`, which matches other opinions on an exact
`download_url`. Today's ca4.py builds the same URLs this command writes, so a
later scrape may already hold one. A match sets `main_version` and drops the
loser out of Elasticsearch, and restoring the three fields will not undo it.
Query for existing ca4 opinions whose `download_url` appears in the mapping's
`new_download_url` column, and resolve any hit by hand first.

This command is safe to re-run. A record whose file was replaced but whose text
extraction then failed is detected and finished off on the next run.
"""

import csv
import re
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from django.core.files.base import ContentFile
from django.db import transaction

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.crypto import sha1
from cl.lib.string_utils import trunc
from cl.scrapers.tasks import extract_opinion_content
from cl.scrapers.utils import check_duplicate_ingestion
from cl.search.models import PRECEDENTIAL_STATUS, Opinion

CA4_MODULE = "juriscraper.opinions.united_states.federal_appellate.ca4"

REQUIRED_COLUMNS = {
    "opinion_id",
    "expected_download_url",
    "expected_sha1",
    "new_download_url",
    "expected_status",
}

# GovInfo answers a bad granule id with an HTML error page and HTTP 200, so the
# response body has to be checked rather than the status code alone.
PDF_MAGIC = b"%PDF-"

SHA1_RE = re.compile(r"^[0-9a-f]{40}$")

# Every GovInfo granule URL is .../pkg/{package}/pdf/{package}-{part}.pdf. The
# package has to agree on both sides of a row or the row would point an opinion
# at a different case's PDF.
GRANULE_URL_RE = re.compile(
    r"^https://www\.govinfo\.gov/content/pkg/"
    r"(?P<package>[A-Za-z0-9-]+?)/pdf/(?P=package)-(?P<part>\d+)\.pdf$"
)

# CA4 stamps every page with the date the document was filed. Comparing that to
# the cluster's date_filed is how the audit found these records in the first
# place, and it is how a half-finished repair is recognised here.
FILED_RE = re.compile(r"Filed:\s*(\d{2})/(\d{2})/(\d{4})")

# CA4 prints the status as a banner on the opinion's first page. These are the
# patterns the pre-fix ca4.py used; the word boundary keeps PUBLISHED from
# matching inside UNPUBLISHED.
PUBLISHED_RE = re.compile(r"\bPUBLISHED\b")
UNPUBLISHED_RE = re.compile(r"\bUNPUBLISHED\b")

VALID_STATUSES = {
    PRECEDENTIAL_STATUS.PUBLISHED,
    PRECEDENTIAL_STATUS.UNPUBLISHED,
}


def derive_status(text: str) -> str:
    """Read the precedential status off a CA4 opinion's text.

    This reproduces the rule the pre-fix ca4.py used. It scans the whole
    document, so a stray banner word deep in an appendix can mislead it. Callers
    must cross-check the result against the audited GovInfo value rather than
    trust it alone.

    :param text: the extracted text of the replacement PDF.
    :return: a PRECEDENTIAL_STATUS value, or an empty string when the banner is
        absent. Callers must leave the stored value alone in that case rather
        than guess.
    """
    if PUBLISHED_RE.search(text):
        return PRECEDENTIAL_STATUS.PUBLISHED
    if UNPUBLISHED_RE.search(text):
        return PRECEDENTIAL_STATUS.UNPUBLISHED
    return ""


def text_filing_date(text: str) -> date | None:
    """Read the filing date CA4 stamps on every page of a document.

    :param text: extracted opinion text.
    :return: the stamped date, or None when there is no stamp to read.
    """
    match = FILED_RE.search(text or "")
    if not match:
        return None
    month, day, year = (int(g) for g in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        # A garbled stamp is no better than a missing one.
        return None


def text_is_stale(opinion: Opinion) -> bool:
    """Does this opinion's stored text belong to a different decision?

    Used to recognise a record whose file was replaced but whose extraction then
    failed, leaving the earlier decision's text in place.

    :param opinion: an opinion with its cluster loaded.
    :return: True when the text is missing, or stamped with a date other than
        the cluster's. An unstamped text cannot be judged, so it counts as
        current rather than forcing a pointless re-extraction.
    """
    if not opinion.plain_text:
        return True
    stamped = text_filing_date(opinion.plain_text)
    if stamped is None:
        return False
    return stamped != opinion.cluster.date_filed


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Read and validate the mapping.

    :param path: CSV produced by the offline audit.
    :return: rows as dicts.
    :raises ValueError: if the file is malformed. Validation happens up front so
        a bad file fails before any row is written.
    """
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        if missing := REQUIRED_COLUMNS - set(reader.fieldnames or []):
            raise ValueError(f"CSV is missing columns: {sorted(missing)}")

        rows = []
        seen: set[int] = set()
        for n, raw in enumerate(reader, start=2):
            if any(raw.get(column) is None for column in REQUIRED_COLUMNS):
                raise ValueError(f"line {n}: row is short of columns")
            try:
                rows.append(parse_row(raw))
            except ValueError as e:
                raise ValueError(f"line {n}: {e}") from e
            if (opinion_id := rows[-1]["opinion_id"]) in seen:
                raise ValueError(
                    f"line {n}: opinion {opinion_id} appears twice"
                )
            seen.add(opinion_id)
    if not rows:
        raise ValueError(f"{path} has no rows")
    return rows


def parse_row(raw: dict[str, str]) -> dict[str, Any]:
    """Validate one mapping row.

    :param raw: the row as read from the CSV.
    :return: the row with its values cleaned.
    :raises ValueError: with a message that does not name the line; load_rows
        adds that.
    """
    try:
        opinion_id = int(raw["opinion_id"])
    except ValueError:
        raise ValueError(
            f"{raw['opinion_id']!r} is not an opinion id"
        ) from None

    expected_sha1 = raw["expected_sha1"].strip()
    if not SHA1_RE.match(expected_sha1):
        raise ValueError(f"{expected_sha1!r} is not a sha1 hash")

    old_url = raw["expected_download_url"].strip()
    new_url = raw["new_download_url"].strip()
    old_match = GRANULE_URL_RE.match(old_url)
    new_match = GRANULE_URL_RE.match(new_url)
    if not new_match:
        raise ValueError(f"{new_url!r} is not a GovInfo granule URL")
    if not old_match:
        raise ValueError(f"{old_url!r} is not a GovInfo granule URL")
    if old_match["package"] != new_match["package"]:
        raise ValueError(
            f"{old_match['package']} and {new_match['package']} are different "
            f"packages, so this row would point at another case"
        )
    if new_match["part"] == "0":
        raise ValueError(
            f"{new_url!r} is still part 0, which is the value this command "
            f"exists to replace"
        )
    if old_url == new_url:
        raise ValueError("old and new URL are the same")

    expected_status = raw["expected_status"].strip()
    if expected_status and expected_status not in VALID_STATUSES:
        raise ValueError(f"{expected_status!r} is not a precedential status")

    return {
        "opinion_id": opinion_id,
        "expected_download_url": old_url,
        "expected_sha1": expected_sha1,
        "new_download_url": new_url,
        "expected_status": expected_status,
    }


def fetch_pdf(client: httpx.Client, url: str) -> bytes:
    """Download a GovInfo PDF.

    :param client: an open httpx client.
    :param url: the granule's PDF URL.
    :return: the file's bytes.
    :raises ValueError: if the response is not a PDF. GovInfo serves an HTML
        error page with HTTP 200 for a granule that does not exist, so a 200
        alone does not mean the body is usable.
    """
    response = client.get(url, follow_redirects=True, timeout=60)
    response.raise_for_status()
    content = response.content
    if not content.startswith(PDF_MAGIC):
        raise ValueError(
            f"{url} returned {len(content)} bytes that are not a PDF"
        )
    return content


class Command(VerboseCommand):
    help = (
        "Replace wrong GovInfo PDFs on historical ca4 opinions (issue 8100)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            required=True,
            type=Path,
            help=(
                "Mapping file with opinion_id, expected_download_url, "
                "expected_sha1, new_download_url, expected_status."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop after this many rows. 0 processes all of them.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        dry_run = options["dry_run"]
        rows = load_rows(options["csv"])
        if options["limit"]:
            rows = rows[: options["limit"]]

        logger.info(
            "%s %s rows from %s",
            "Checking" if dry_run else "Applying",
            len(rows),
            options["csv"],
        )

        stats = dict.fromkeys(
            [
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
            ],
            0,
        )
        with httpx.Client() as client:
            for i, row in enumerate(rows, start=1):
                self.process_row(row, client, dry_run, stats)
                if i % 25 == 0:
                    logger.info("Processed %s of %s", i, len(rows))

        prefix = "Would have " if dry_run else ""
        logger.info(
            "Done. %s%s replaced, %s had only their text finished, "
            "%s had only their URL corrected, %s already correct, "
            "%s skipped on mismatch, %s missing, %s failed to download, "
            "%s failed to extract.",
            prefix,
            stats["replaced"],
            stats["text_finished"],
            stats["url_corrected"],
            stats["already_correct"],
            stats["skipped_mismatch"],
            stats["missing"],
            stats["download_failed"],
            stats["extraction_failed"],
        )
        logger.info(
            "precedential_status: %s%s corrected, %s undetermined, "
            "%s disputed by the mapping and left alone.",
            prefix,
            stats["status_corrected"],
            stats["status_undetermined"],
            stats["status_disputed"],
        )

    def process_row(
        self,
        row: dict[str, Any],
        client: httpx.Client,
        dry_run: bool,
        stats: dict[str, int],
    ) -> None:
        """Repair one opinion, or explain why it was left alone.

        Guards run before the download so a stale CSV costs no bandwidth.

        :param row: one validated row from the mapping.
        :param client: an open httpx client.
        :param dry_run: report instead of writing.
        :param stats: counters for the final report. Modified in place.
        :return: None
        """
        opinion_id = row["opinion_id"]
        try:
            opinion = Opinion.objects.select_related("cluster").get(
                pk=opinion_id
            )
        except Opinion.DoesNotExist:
            stats["missing"] += 1
            logger.warning("Opinion %s no longer exists", opinion_id)
            return

        if opinion.download_url == row["new_download_url"]:
            self.finish_partial_repair(opinion, row, dry_run, stats)
            return

        if (
            opinion.download_url != row["expected_download_url"]
            or opinion.sha1 != row["expected_sha1"]
        ):
            # The database moved on since the audit. Leave it alone and report
            # it; the CSV needs regenerating before this row runs.
            stats["skipped_mismatch"] += 1
            logger.warning(
                "Opinion %s: expected %s / %s, found %s / %s. Skipped.",
                opinion_id,
                row["expected_download_url"],
                row["expected_sha1"],
                opinion.download_url,
                opinion.sha1,
            )
            return

        if dry_run:
            stats["replaced"] += 1
            logger.info(
                "Would replace opinion %s with %s",
                opinion_id,
                row["new_download_url"],
            )
            return

        try:
            content = fetch_pdf(client, row["new_download_url"])
        except (httpx.HTTPError, ValueError) as e:
            stats["download_failed"] += 1
            logger.warning(
                "Opinion %s: could not fetch %s: %s",
                opinion_id,
                row["new_download_url"],
                e,
            )
            return

        if sha1(content) == opinion.sha1:
            # GovInfo serves identical bytes at both granules. The stored file
            # is already right, so only the URL is wrong. Do not write a second
            # copy of the same bytes.
            logger.info(
                "Opinion %s: %s has the same content as the stored file, "
                "correcting the URL only",
                opinion_id,
                row["new_download_url"],
            )
            opinion.download_url = row["new_download_url"]
            opinion.save(update_fields=["download_url", "date_modified"])
            stats["url_corrected"] += 1
            self.correct_status(opinion_id, row, stats)
            return

        file_name = f"{trunc(opinion.cluster.case_name.lower(), 75)}.pdf"
        with transaction.atomic():
            opinion.local_path.save(
                file_name, ContentFile(content), save=False
            )
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

        # Logged before extraction, so a crash still leaves a record of which
        # rows committed. Until extraction succeeds the opinion holds the old
        # decision's text; a second run finds that and finishes it.
        logger.info(
            "Opinion %s now points at %s, stored as %s",
            opinion_id,
            row["new_download_url"],
            opinion.local_path.name,
        )
        stats["replaced"] += 1
        self.extract_and_set_status(opinion_id, row, stats)

    def finish_partial_repair(
        self,
        opinion: Opinion,
        row: dict[str, Any],
        dry_run: bool,
        stats: dict[str, int],
    ) -> None:
        """Handle a record that already points at the replacement PDF.

        The file swap commits before extraction runs, and
        `extract_opinion_content` swallows a doctor failure rather than raising,
        so a record can be left pointing at the new PDF while still holding the
        old decision's text. Re-extract when that is what the text looks like.

        :param opinion: the opinion, with its cluster loaded.
        :param row: the mapping row.
        :param dry_run: report instead of writing.
        :param stats: counters for the final report. Modified in place.
        :return: None
        """
        if not text_is_stale(opinion):
            stats["already_correct"] += 1
            return

        if dry_run:
            stats["text_finished"] += 1
            logger.info(
                "Opinion %s points at %s but holds text stamped %s; would "
                "re-extract",
                opinion.pk,
                opinion.download_url,
                text_filing_date(opinion.plain_text) or "nothing",
            )
            return

        logger.warning(
            "Opinion %s points at %s but holds text stamped %s. Finishing an "
            "interrupted repair.",
            opinion.pk,
            opinion.download_url,
            text_filing_date(opinion.plain_text) or "nothing",
        )
        stats["text_finished"] += 1
        self.extract_and_set_status(opinion.pk, row, stats)

    def extract_and_set_status(
        self, opinion_id: int, row: dict[str, Any], stats: dict[str, int]
    ) -> None:
        """Re-extract an opinion's text, then reset its status from it.

        Extraction rewrites plain_text and page_count and chains citation
        finding. A failure here leaves the record pointing at the new PDF with
        the old text, which the next run recognises, so it is reported and the
        run carries on.

        :param opinion_id: the opinion whose file was just replaced.
        :param row: the mapping row, for its audited status.
        :param stats: counters for the final report. Modified in place.
        :return: None
        """
        try:
            extract_opinion_content(
                pk=opinion_id,
                juriscraper_module=CA4_MODULE,
                ocr_available=True,
            )
        except Exception:
            # The file is committed and the text is not. Report it and move on;
            # a later run will finish this record.
            stats["extraction_failed"] += 1
            logger.exception(
                "Opinion %s: extraction failed after the file was replaced. "
                "Re-run this command to finish it.",
                opinion_id,
            )
            return

        self.correct_status(opinion_id, row, stats)

    def correct_status(
        self, opinion_id: int, row: dict[str, Any], stats: dict[str, int]
    ) -> None:
        """Reset precedential_status from the replacement PDF's own banner.

        Must run after extraction, since it reads the newly stored text. The
        opinion is reloaded because extraction saved its own copy of the row.

        The text-derived value is cross-checked against the status the audit
        read from GovInfo's MODS metadata. They agreed on every record in the
        audit, so a disagreement means one of the two is reading the wrong
        document. The stored value is then left alone and reported.

        :param opinion_id: the repaired opinion.
        :param row: the mapping row, for its audited status.
        :param stats: counters for the final report. Modified in place.
        :return: None
        """
        opinion = Opinion.objects.select_related("cluster").get(pk=opinion_id)
        stored = opinion.cluster.precedential_status

        # plain_text only: html on these records comes from a merged corpus and
        # describes a different document.
        if text_is_stale(opinion):
            stats["status_undetermined"] += 1
            logger.warning(
                "Opinion %s: text is still not the replacement PDF's, leaving "
                "precedential_status as %s",
                opinion_id,
                stored,
            )
            return

        status = derive_status(opinion.plain_text)
        if not status:
            stats["status_undetermined"] += 1
            logger.info(
                "Opinion %s: replacement PDF has no status banner, leaving "
                "precedential_status as %s",
                opinion_id,
                stored,
            )
            return

        expected = row["expected_status"]
        if expected and status != expected:
            stats["status_disputed"] += 1
            logger.error(
                "Opinion %s: PDF text says %s but the mapping says GovInfo "
                "says %s. Leaving precedential_status as %s.",
                opinion_id,
                status,
                expected,
                stored,
            )
            return

        if status == stored:
            return

        logger.info(
            "Opinion %s: precedential_status %s -> %s",
            opinion_id,
            stored,
            status,
        )
        opinion.cluster.precedential_status = status
        # save() rather than update(): post_save drives the Elasticsearch
        # status update.
        opinion.cluster.save(
            update_fields=["precedential_status", "date_modified"]
        )
        stats["status_corrected"] += 1
