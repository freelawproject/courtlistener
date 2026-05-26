"""Query-count comparison: legacy SCOTUS merger vs new framework driver.

Asserts that the new merger uses no more SQL queries than the legacy
``merge_scotus_docket`` on the same input, across two scenarios:

1. **First merge** (empty DB) — measures the create-path query cost.
2. **Re-merge** (docket + children already in DB) — measures the
   match-and-update-path cost. This is where the framework's batched
   prefetch should significantly out-perform the legacy N+1 lookups.

The comparison runs both mergers against a fresh savepoint baseline so
each side starts from the same DB state. Celery dispatch is mocked
(same patches as the parity tests) so the count measures pure DB work.

These tests are deterministic — hand-crafted docket shapes rather than
Hypothesis-generated. The point isn't to find edge cases but to guard
against the framework regressing to N+1 query patterns.
"""

from datetime import date
from unittest.mock import patch

from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from cl.corpus_importer.tasks import (
    merge_scotus_docket as legacy_merge_scotus_docket,
)
from cl.scrapers.mergers.federal.scotus.driver import (
    merge_scotus_docket as new_merge_scotus_docket,
)
from cl.search.factories import CourtFactory
from cl.tests.cases import TestCase


# ---------------------------------------------------------------------------
# Representative SCOTUS docket — non-trivial children so the prefetch
# advantage is measurable.
# ---------------------------------------------------------------------------


_DOCKET: dict = {
    "docket_number": "22-100",
    "case_name": "Smith v. Jones",
    "date_filed": date(2022, 5, 1),
    "lower_court": "United States Court of Appeals for the Second Circuit",
    "lower_court_case_numbers": ["21-5678"],
    "lower_court_case_numbers_raw": "21-5678",
    "lower_court_decision_date": date(2021, 11, 15),
    "lower_court_rehearing_denied_date": None,
    "questions_presented": "/qp/22-100qp.pdf",
    "capital_case": False,
    "links": "Linked-with: 22-101",
    "discretionary_court_decision": None,
    "docket_entries": [
        {
            "document_number": 1,
            "description": "Petition for a writ of certiorari filed.",
            "date_filed": date(2022, 5, 1),
            # Each attachment carries the parent entry's
            # ``document_number`` (legacy ``enrich_scotus_attachments``
            # sets this; we inline the same value here for consistency).
            "attachments": [
                {
                    "document_number": 1,
                    "description": "Petition",
                    "document_url": "https://www.supremecourt.gov/DocketPDF/22/22-100/petition.pdf",
                },
                {
                    "document_number": 1,
                    "description": "Appendix",
                    "document_url": "https://www.supremecourt.gov/DocketPDF/22/22-100/appendix.pdf",
                },
            ],
        },
        {
            "document_number": 2,
            "description": "Brief of respondent in opposition.",
            "date_filed": date(2022, 6, 15),
            "attachments": [
                {
                    "document_number": 2,
                    "description": "Brief in opposition",
                    "document_url": "https://www.supremecourt.gov/DocketPDF/22/22-100/bio.pdf",
                },
            ],
        },
        {
            "document_number": 3,
            "description": "Reply of petitioner filed.",
            "date_filed": date(2022, 7, 1),
            "attachments": [],
        },
    ],
    "parties": [
        {
            "name": "John Smith",
            "type": "Petitioner",
            "attorneys": [
                {
                    "name": "Jane Doe",
                    "is_counsel_of_record": True,
                    "title": "Esq.",
                    "phone": "(202) 555-1234",
                    "address": "1234 K Street NW",
                    "city": "Washington",
                    "state": "DC",
                    "zip": "20001",
                    "email": "jane@example.com",
                },
                {
                    "name": "Bob Roe",
                    "is_counsel_of_record": False,
                    "title": None,
                    "phone": None,
                    "address": "5678 L Street NW",
                    "city": "Washington",
                    "state": "DC",
                    "zip": "20002",
                    "email": "bob@example.com",
                },
            ],
        },
        {
            "name": "Acme Corp.",
            "type": "Respondent",
            "attorneys": [
                {
                    "name": "Carol West",
                    "is_counsel_of_record": True,
                    "title": "Esq.",
                    "phone": "(212) 555-9876",
                    "address": "9 Wall Street",
                    "city": "New York",
                    "state": "NY",
                    "zip": "10001",
                    "email": "carol@example.com",
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class ScotusMergerQueryCountTest(TestCase):
    """Compare query counts between legacy and new SCOTUS mergers.

    Two scenarios per test method: a first-merge (empty DB) and a
    re-merge (DB already has the docket). The new merger should be
    ``<=`` the legacy in both, and meaningfully ``<`` on re-merge
    thanks to batched prefetch.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        # SCOTUS court must exist before either merger runs.
        CourtFactory.create(
            id="scotus",
            short_name="SCOTUS",
            full_name="Supreme Court of the United States",
        )

    def setUp(self) -> None:
        # Suppress Celery dispatch on both sides so the comparison
        # focuses on row work, not on download side-effects.
        self._patches = [
            patch("cl.corpus_importer.tasks.chain"),
            patch(
                "cl.corpus_importer.tasks.download_scotus_document_pdf"
            ),
            patch("cl.corpus_importer.tasks.extract_pdf_document"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _count_in_savepoint(self, fn) -> int:
        """Run ``fn`` inside a savepoint with query counting, then roll
        back. Returns the number of queries fired *inside* the with
        block — the SAVEPOINT / ROLLBACK TO SAVEPOINT statements
        themselves run outside the capture context and don't inflate
        the count.
        """
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
        should be no worse than the legacy's. Mostly INSERTs on both
        sides, so the framework's prefetch advantage is muted here."""
        legacy_count = self._count_in_savepoint(
            lambda: legacy_merge_scotus_docket(_DOCKET, download_file=False)
        )
        new_count = self._count_in_savepoint(
            lambda: new_merge_scotus_docket(_DOCKET, download_file=False)
        )
        self.assertLessEqual(
            new_count,
            legacy_count,
            msg=(
                f"SCOTUS first-merge: new framework used more queries "
                f"({new_count}) than legacy ({legacy_count})."
            ),
        )

    # ------------------------------------------------------------------
    # Re-merge scenario: docket already in DB
    # ------------------------------------------------------------------

    def test_re_merge_query_count_is_at_most_legacy(self) -> None:
        """With the docket already in the DB, the framework's batched
        prefetch should beat the legacy's N+1 lookup pattern. This is
        the scenario where the new merger's design advantage shows up."""
        # Prime the DB outside any savepoint — these writes persist
        # so the two test runs both see the docket as pre-existing.
        legacy_merge_scotus_docket(_DOCKET, download_file=False)

        legacy_count = self._count_in_savepoint(
            lambda: legacy_merge_scotus_docket(_DOCKET, download_file=False)
        )
        new_count = self._count_in_savepoint(
            lambda: new_merge_scotus_docket(_DOCKET, download_file=False)
        )
        self.assertLessEqual(
            new_count,
            legacy_count,
            msg=(
                f"SCOTUS re-merge: new framework used more queries "
                f"({new_count}) than legacy ({legacy_count}). The "
                f"prefetch advantage should make new strictly less than "
                f"legacy in this scenario; if they're equal a slow N+1 "
                f"path may have crept in."
            ),
        )
