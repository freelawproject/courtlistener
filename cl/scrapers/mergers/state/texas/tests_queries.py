"""Query-count comparison: legacy Texas merger vs new framework driver.

Same shape as :mod:`cl.scrapers.mergers.federal.scotus.tests_queries` —
asserts that the new merger uses no more SQL queries than the legacy
``merge_texas_docket`` on the same input, across first-merge and
re-merge scenarios. The re-merge scenario is where the framework's
batched prefetch should significantly out-perform legacy's per-row
SELECTs.

Deterministic hand-crafted docket (Court of Appeals shape, matching the
parity-test fixtures). Celery dispatch is mocked so the count measures
pure DB work.
"""

from datetime import date
from unittest.mock import patch
from uuid import uuid4

from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from juriscraper.state.texas.common import CourtID, CourtType

from cl.corpus_importer.tasks import (
    merge_texas_docket as legacy_merge_texas_docket,
)
from cl.scrapers.mergers.state.texas.driver import (
    merge_texas_docket as new_merge_texas_docket,
)
from cl.search.factories import CourtFactory
from cl.tests.cases import TestCase


# ---------------------------------------------------------------------------
# Representative Texas COA docket — non-trivial children so the
# prefetch advantage is measurable.
# ---------------------------------------------------------------------------


def _attachment(description: str) -> dict:
    """Build a single TexasCaseDocument-shaped attachment. UUIDs are
    drawn fresh per dict so the docket is unique per build, but the
    same docket fixture instance reused across runs in one test gives
    identical merge inputs (legacy and new see the same media_ids)."""
    return {
        "document_url": f"https://example.com/{description.lower()}.pdf",
        "media_id": str(uuid4()),
        "media_version_id": str(uuid4()),
        "description": description,
        "file_size_bytes": 12345,
        "file_size_str": "12 KB",
    }


def _build_docket() -> dict:
    return {
        "court_id": CourtID.FIRST_COURT_OF_APPEALS.value,
        "court_type": CourtType.APPELLATE.value,
        "docket_number": "01-22-00100-CV",
        "case_name": "Smith v. Jones",
        "case_name_full": "John Smith v. Acme Corporation",
        "date_filed": date(2022, 5, 1),
        "case_type": "Civil",
        "parties": [
            {
                "name": "John Smith",
                "type": "APPELLANT",
                "representatives": ["Jane Doe Esq.", "Bob Roe Esq."],
            },
            {
                "name": "Acme Corporation",
                "type": "APPELLEE",
                "representatives": ["Carol West Esq."],
            },
        ],
        "originating_court": {
            "name": "215th District Court",
            "court_type": CourtType.DISTRICT.value,
            "case": "2021-12345",
            "county": "Harris",
            "judge": "Hon. Pat Roberts",
            "reporter": "Jane Reporter",
            "punishment": "",
            "district": 5,
        },
        "case_events": [
            {
                "date": date(2022, 5, 1),
                "type": "Notice of appeal filed",
                "disposition": "",
                "remarks": "",
                "attachments": [_attachment("Notice")],
            },
            {
                "date": date(2022, 6, 15),
                "type": "Appellant brief filed",
                "disposition": "",
                "remarks": "",
                "attachments": [
                    _attachment("Brief"),
                    _attachment("Appendix"),
                ],
            },
            {
                "date": date(2022, 7, 30),
                "type": "Appellee brief filed",
                "disposition": "",
                "remarks": "",
                "attachments": [_attachment("Brief")],
            },
        ],
        "appellate_briefs": [],
        "transfer_from": None,
        "transfer_to": None,
    }


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TexasMergerQueryCountTest(TestCase):
    """Compare query counts between legacy and new Texas mergers.

    Two scenarios per test: a first-merge (empty DB) and a re-merge
    (DB already has the docket). The new merger should be ``<=`` the
    legacy in both, and meaningfully ``<`` on re-merge thanks to the
    framework's batched prefetch."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Courts referenced by the docket fixture. Same shape as the
        # parity test's setUpTestData.
        cls.texas_coa1 = CourtFactory.create(id="txctapp1")
        cls.texas_district = CourtFactory.create(id="texdistct6")

    def setUp(self) -> None:
        # Suppress Celery dispatch so the comparison focuses on row
        # work, not download side-effects.
        self._patches = [
            patch("cl.corpus_importer.tasks.download_texas_document.si"),
            patch(
                "cl.corpus_importer.tasks.extract_formatted_text_document.s"
            ),
            patch("cl.corpus_importer.tasks.download_document_in_stream"),
        ]
        for p in self._patches:
            p.start()
        # Build a fresh docket per test so the UUIDs are stable inside
        # a single test method (legacy and new see identical input).
        self.docket = _build_docket()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _count_in_savepoint(self, fn) -> int:
        """Run ``fn`` inside a savepoint with query counting, then roll
        back. SAVEPOINT / ROLLBACK TO SAVEPOINT run outside the
        capture context and don't inflate the count."""
        sid = transaction.savepoint()
        try:
            with CaptureQueriesContext(connection) as ctx:
                with self.captureOnCommitCallbacks(execute=False):
                    fn()
            return len(ctx.captured_queries)
        finally:
            transaction.savepoint_rollback(sid)

    # ------------------------------------------------------------------
    # First-merge scenario: empty DB
    # ------------------------------------------------------------------

    def test_first_merge_query_count_is_at_most_legacy(self) -> None:
        """On an empty DB, the new merger's create-path query count
        should be no worse than the legacy's."""
        legacy_count = self._count_in_savepoint(
            lambda: legacy_merge_texas_docket(
                self.docket, download_attachments=False
            )
        )
        new_count = self._count_in_savepoint(
            lambda: new_merge_texas_docket(
                self.docket, download_attachments=False
            )
        )
        self.assertLessEqual(
            new_count,
            legacy_count,
            msg=(
                f"Texas first-merge: new framework used more queries "
                f"({new_count}) than legacy ({legacy_count})."
            ),
        )

    # ------------------------------------------------------------------
    # Re-merge scenario: docket already in DB
    # ------------------------------------------------------------------

    def test_re_merge_query_count_is_at_most_legacy(self) -> None:
        """With the docket already in the DB, the framework's batched
        prefetch should beat the legacy's per-row SELECT pattern.
        This is the scenario where the new merger's design advantage
        shows up most clearly."""
        # Prime the DB outside any savepoint — these writes persist
        # for the test method.
        legacy_merge_texas_docket(self.docket, download_attachments=False)

        legacy_count = self._count_in_savepoint(
            lambda: legacy_merge_texas_docket(
                self.docket, download_attachments=False
            )
        )
        new_count = self._count_in_savepoint(
            lambda: new_merge_texas_docket(
                self.docket, download_attachments=False
            )
        )
        self.assertLessEqual(
            new_count,
            legacy_count,
            msg=(
                f"Texas re-merge: new framework used more queries "
                f"({new_count}) than legacy ({legacy_count}). The "
                f"prefetch advantage should make new strictly less "
                f"than legacy here; equality suggests a slow N+1 "
                f"path may have crept in."
            ),
        )
