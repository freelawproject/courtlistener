"""Integration tests for the NYCoA Court-PASS merger driver.

Builds a tiny synthetic kent.db, runs :class:`NYCoAMerger` against the
real ``search`` Django models, and verifies the resulting Docket /
DocketEntry / Document / Party / Attorney rows match expectations.

Hypothesis property test: for any set of (court-id, docket-number,
case-name) tuples, running the merger twice produces the same DB
state as running it once — re-scrape idempotency.
"""

import json
import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from cl.scrapers.mergers import IngestFile
from cl.scrapers.mergers.state.new_york.nycoa.driver import NYCoAMerger
from cl.search.factories import CourtFactory
from cl.search.models import Court, Docket
from cl.search.state.new_york.models import NYCoADocketEntry, NYCoADocument
from cl.people_db.models import (
    Attorney,
    AttorneyOrganization,
    AttorneyOrganizationAssociation,
    Party,
    PartyType,
    Role,
)
from cl.tests.cases import TransactionTestCase


# ---------------------------------------------------------------------------
# kent.db builder
# ---------------------------------------------------------------------------


def _build_kent_db(rows: list[tuple[str, dict]], tmp_dir: Path) -> Path:
    """Synthesize a tiny kent.db with the supplied ``(result_type,
    data_json)`` rows. Returns the path."""
    path = tmp_dir / f"kent_{uuid.uuid4().hex}.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE results (
            id INTEGER NOT NULL PRIMARY KEY,
            request_id INTEGER,
            result_type VARCHAR NOT NULL,
            data_json VARCHAR NOT NULL,
            is_valid BOOLEAN DEFAULT 1 NOT NULL,
            validation_errors_json VARCHAR,
            created_at VARCHAR DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for rtype, payload in rows:
        conn.execute(
            "INSERT INTO results (result_type, data_json, is_valid) VALUES (?, ?, 1)",
            (rtype, json.dumps(payload)),
        )
    conn.commit()
    conn.close()
    return path


def _make_docket(
    tcid: str,
    *,
    docket_number: str,
    case_name: str = "Smith v Jones",
    case_short_name: str = "Smith v Jones",
    argument_date: str | None = "2025-01-15",
    decision_date: str | None = "2025-02-20",
    docket_entries: list[dict] | None = None,
    attorneys: list[dict] | None = None,
) -> tuple[str, dict]:
    return (
        "NYCourtPassDocket",
        {
            "temp_case_id": tcid,
            "docket_number": docket_number,
            "court_id": "ny",
            "case_name": case_name,
            "case_short_name": case_short_name,
            "argument_date": argument_date,
            "decision_date": decision_date,
            "docket_entries": docket_entries or [],
            "attorneys": attorneys or [],
            "files": [],
            "issues": [],
            "issue_details": [],
            "no_files_for_case": False,
        },
    )


def _make_file(
    tcid: str,
    *,
    file_index: int,
    file_name: str,
    local_path: str,
    available: bool = True,
) -> tuple[str, dict]:
    return (
        "NYCourtPassFile",
        {
            "temp_case_id": tcid,
            "file_name": file_name,
            "file_index": file_index,
            "local_path": local_path,
            "available": available,
        },
    )


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class NYCoAMergerIntegrationTest(TransactionTestCase):
    """End-to-end merger runs against synthetic kent.db files."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="nycoa_int_"))
        # Ensure the 'ny' court exists. The factory has
        # ``django_get_or_create=('id',)`` so this is idempotent.
        self.court = CourtFactory.create(
            id="ny",
            short_name="N.Y. Ct. App.",
            full_name="New York Court of Appeals",
        )

    def test_create_one_docket_with_filings_and_files(self) -> None:
        """One docket + 1 FILINGS entry + 1 file → 1 Docket, 2
        DocketEntries (FILINGS-derived + file-only), 1 Document."""
        tcid = str(uuid.uuid4())
        kent = _build_kent_db(
            [
                _make_docket(
                    tcid,
                    docket_number="APL-2024-00001",
                    docket_entries=[
                        {
                            "filing_type": "Appellant Brief",
                            "party": "Smith",
                            "date_due": "2024-12-01",
                            "date_received": "2024-12-15",
                        }
                    ],
                    attorneys=[
                        {
                            "party_name": "Smith",
                            "party_role": "Appellant",
                            "firm": "Smith Firm LLP",
                            "attorney_name": "Jane Doe",
                            "address": "123 Main\nNew York NY 10001",
                            "phone": "(212) 555-1212",
                        }
                    ],
                ),
                _make_file(
                    tcid,
                    file_index=0,
                    file_name="smith-brief.pdf",
                    local_path="runs/NYApp-files/ab/cd/smith.pdf",
                ),
            ],
            self.tmp,
        )
        merger = NYCoAMerger(kent)
        outcome = merger.run()

        self.assertEqual(Docket.objects.filter(court=self.court).count(), 1)
        docket = Docket.objects.get(docket_number="APL-2024-00001")
        # Two entries: 1 from FILINGS, 1 synthesized for the file.
        entries = NYCoADocketEntry.objects.filter(docket=docket)
        self.assertEqual(entries.count(), 2)
        # Disjoint sequence-number prefixes.
        seqs = sorted(e.sequence_number for e in entries)
        self.assertTrue(any(s.startswith("file.") for s in seqs))
        self.assertTrue(any(not s.startswith("file.") for s in seqs))
        # Exactly one Document, on the file-only entry.
        self.assertEqual(NYCoADocument.objects.filter(docket_entry__docket=docket).count(), 1)
        # One Party + one Attorney + Role + Org association.
        self.assertEqual(Party.objects.filter(name="Smith").count(), 1)
        self.assertEqual(Attorney.objects.filter(name="Jane Doe").count(), 1)
        self.assertEqual(
            PartyType.objects.filter(docket=docket, name="Appellant").count(), 1
        )
        self.assertEqual(
            Role.objects.filter(docket=docket, role_raw="Appellant").count(), 1
        )

    def test_collapses_whitespace_in_case_name(self) -> None:
        """Court-PASS embeds newlines and runs of spaces in case names;
        the normalize pass collapses them to single spaces."""
        tcid = str(uuid.uuid4())
        messy = "Smith\n    v.\n          Jones"
        kent = _build_kent_db(
            [
                _make_docket(tcid, docket_number="APL-2024-00002", case_name=messy),
            ],
            self.tmp,
        )
        NYCoAMerger(kent).run()
        docket = Docket.objects.get(docket_number="APL-2024-00002")
        self.assertEqual(docket.case_name, "Smith v. Jones")

    def test_idempotent_rerun(self) -> None:
        """Running the merger twice produces the same DB state — no
        duplicated rows, no new Document inserts."""
        tcid = str(uuid.uuid4())
        rows = [
            _make_docket(
                tcid,
                docket_number="APL-2024-00003",
                attorneys=[
                    {
                        "party_name": "Smith",
                        "party_role": "Appellant",
                        "firm": "Smith Firm",
                        "attorney_name": "Jane Doe",
                        "address": "123 Main\nNY NY 10001",
                        "phone": "(212) 555-1212",
                    }
                ],
            ),
            _make_file(
                tcid,
                file_index=0,
                file_name="brief.pdf",
                local_path="runs/NYApp-files/aa/bb/brief.pdf",
            ),
        ]
        kent = _build_kent_db(rows, self.tmp)

        merger = NYCoAMerger(kent)
        merger.run()
        # Snapshot post-first-run counts.
        counts = {
            "dockets": Docket.objects.count(),
            "entries": NYCoADocketEntry.objects.count(),
            "documents": NYCoADocument.objects.count(),
            "parties": Party.objects.count(),
            "attorneys": Attorney.objects.count(),
            "roles": Role.objects.count(),
        }

        NYCoAMerger(kent).run()
        self.assertEqual(Docket.objects.count(), counts["dockets"])
        self.assertEqual(NYCoADocketEntry.objects.count(), counts["entries"])
        self.assertEqual(NYCoADocument.objects.count(), counts["documents"])
        self.assertEqual(Party.objects.count(), counts["parties"])
        self.assertEqual(Attorney.objects.count(), counts["attorneys"])
        self.assertEqual(Role.objects.count(), counts["roles"])

    def test_emits_ingest_file_followup_for_each_document(self) -> None:
        """Every NYCoADocument insert should produce one IngestFile in
        the outcome's follow_ups."""
        tcid = str(uuid.uuid4())
        kent = _build_kent_db(
            [
                _make_docket(tcid, docket_number="APL-2024-00004"),
                _make_file(
                    tcid,
                    file_index=0,
                    file_name="a.pdf",
                    local_path="runs/NYApp-files/aa/a.pdf",
                ),
                _make_file(
                    tcid,
                    file_index=1,
                    file_name="b.pdf",
                    local_path="runs/NYApp-files/bb/b.pdf",
                ),
            ],
            self.tmp,
        )
        merger = NYCoAMerger(kent)
        outcome = merger.run()
        ingests = [f for f in outcome.follow_ups if isinstance(f, IngestFile)]
        self.assertEqual(len(ingests), 2)
        # Both records target the new Documents on this run.
        for ingest in ingests:
            self.assertEqual(ingest.model_label, "search.NYCoADocument")
            self.assertTrue(
                ingest.storage_url.startswith("s3://"),
                f"Expected s3:// URL, got {ingest.storage_url!r}",
            )

    def test_skips_unavailable_files(self) -> None:
        """``available=0`` rows are filtered out by the SQL — no
        Document is created for them."""
        tcid = str(uuid.uuid4())
        kent = _build_kent_db(
            [
                _make_docket(tcid, docket_number="APL-2024-00005"),
                _make_file(
                    tcid,
                    file_index=0,
                    file_name="sealed.pdf",
                    local_path="runs/NYApp-files/zz/sealed.pdf",
                    available=False,
                ),
            ],
            self.tmp,
        )
        NYCoAMerger(kent).run()
        docket = Docket.objects.get(docket_number="APL-2024-00005")
        self.assertEqual(
            NYCoADocument.objects.filter(docket_entry__docket=docket).count(),
            0,
        )

    def test_party_dedupes_across_dockets(self) -> None:
        """Same party name across two dockets resolves to a single
        Party row (SCOTUS-style global ExternalNodeRef)."""
        tcid1, tcid2 = str(uuid.uuid4()), str(uuid.uuid4())
        rows = [
            _make_docket(
                tcid1,
                docket_number="APL-2024-00006",
                attorneys=[
                    {
                        "party_name": "Acme Corp",
                        "party_role": "Appellant",
                        "firm": None,
                        "attorney_name": "Jane Doe",
                        "address": None,
                        "phone": None,
                    }
                ],
            ),
            _make_docket(
                tcid2,
                docket_number="APL-2024-00007",
                attorneys=[
                    {
                        "party_name": "Acme Corp",
                        "party_role": "Respondent",
                        "firm": None,
                        "attorney_name": "John Roe",
                        "address": None,
                        "phone": None,
                    }
                ],
            ),
        ]
        kent = _build_kent_db(rows, self.tmp)
        NYCoAMerger(kent).run()
        # One shared Party row used on both dockets.
        self.assertEqual(Party.objects.filter(name="Acme Corp").count(), 1)
        # But two PartyType joins (Appellant + Respondent).
        self.assertEqual(
            PartyType.objects.filter(name__in=["Appellant", "Respondent"]).count(),
            2,
        )


# ---------------------------------------------------------------------------
# Hypothesis property test
# ---------------------------------------------------------------------------


_DOCKET_NUMBER_STRATEGY = st.from_regex(
    r"^APL-20[12][0-9]-[0-9]{5}$", fullmatch=True
)
_CASE_NAME_STRATEGY = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=3,
    max_size=40,
).filter(lambda s: s.strip())


@st.composite
def _docket_batch(draw):
    """Generate a small batch of distinct dockets to merge."""
    n = draw(st.integers(min_value=1, max_value=5))
    out: list[dict] = []
    seen: set[str] = set()
    for _ in range(n):
        dn = draw(_DOCKET_NUMBER_STRATEGY)
        if dn in seen:
            continue
        seen.add(dn)
        out.append(
            {
                "docket_number": dn,
                "case_name": draw(_CASE_NAME_STRATEGY),
                "temp_case_id": str(uuid.uuid4()),
            }
        )
    return out


class NYCoAMergerPropertyTest(HypothesisTestCase):
    """Property: re-running the merger against the same kent.db never
    creates or deletes rows on the second pass.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create(
            id="ny",
            short_name="N.Y. Ct. App.",
            full_name="New York Court of Appeals",
        )

    @given(batch=_docket_batch())
    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_rerun_is_idempotent(self, batch: list[dict]) -> None:
        with tempfile.TemporaryDirectory(prefix="nycoa_prop_") as td:
            rows: list[tuple[str, dict]] = []
            for item in batch:
                rows.append(
                    _make_docket(
                        item["temp_case_id"],
                        docket_number=item["docket_number"],
                        case_name=item["case_name"],
                    )
                )
            kent = _build_kent_db(rows, Path(td))

            first = NYCoAMerger(kent).run()
            # First run should have created exactly len(batch) dockets
            # under this court (modulo any earlier examples in the
            # transaction).
            created_dockets = first.creates.get(Docket, set())
            self.assertEqual(len(created_dockets), len(batch))

            counts = {
                "dockets": Docket.objects.count(),
                "entries": NYCoADocketEntry.objects.count(),
            }

            second = NYCoAMerger(kent).run()
            # Second run: no new dockets created.
            self.assertEqual(second.creates.get(Docket, set()), set())
            # Counts unchanged.
            self.assertEqual(Docket.objects.count(), counts["dockets"])
            self.assertEqual(
                NYCoADocketEntry.objects.count(), counts["entries"]
            )
