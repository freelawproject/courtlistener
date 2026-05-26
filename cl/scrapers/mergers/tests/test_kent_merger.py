"""Tests for :mod:`cl.scrapers.mergers.kent`.

Covers the base-class plumbing in isolation from any concrete driver:

- SQL path resolution from the subclass module.
- ``normalize`` default identity.
- ``iter_aggregates`` skips rows that fail normalization / validation
  and continues with the rest.
- ``run`` accumulates per-aggregate outcomes via ``|`` (union of
  per-model PK sets, concat of follow-ups), and skips on errors.
- ``dispatch_ingest_files`` invokes every IngestFile and ignores
  plain FollowUps.
- ``IngestFile`` constructs with typed fields and exposes them
  through both attribute access and the inherited ``FollowUp`` shape.
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from cl.scrapers.mergers import FollowUp, IngestFile, KentMerger, MergeOutcome
from cl.scrapers.mergers.tests.testmodels.models import (
    TCourt,
    TDocket,
)
from cl.scrapers.mergers import Aggregate, PreResolvedRef
from cl.tests.cases import SimpleTestCase, TransactionTestCase


# ---------------------------------------------------------------------------
# Schema fixtures (use the existing mergers_test models)
# ---------------------------------------------------------------------------


class _DocketAgg(Aggregate[TDocket]):
    """Aggregate fixture used in the KentMerger unit tests. Mirrors the
    shape any real driver produces — natural key on (court,
    docket_number_core), a PreResolvedRef[TCourt] for the court."""

    natural_key = ("court", "docket_number_core")
    court: PreResolvedRef[TCourt]
    docket_number_core: str


# ---------------------------------------------------------------------------
# Synthetic kent.db helpers
# ---------------------------------------------------------------------------


def _make_kent_db(
    tmp_path: Path, rows: list[tuple[str, str]]
) -> Path:
    """Build a minimal results-table sqlite DB.

    ``rows`` is a list of (sql, raw_text_or_None) — but for KentMerger
    tests we only care about ``scrape_json``, so we'll build a single
    column from a tiny shim table.
    """
    db = tmp_path / f"kent_{abs(hash(tuple(rows)))}.db"
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE scrapes (scrape_json TEXT)"
    )
    for _, blob in rows:
        conn.execute(
            "INSERT INTO scrapes (scrape_json) VALUES (?)", (blob,)
        )
    conn.commit()
    conn.close()
    return db


# ---------------------------------------------------------------------------
# IngestFile
# ---------------------------------------------------------------------------


class IngestFileTest(SimpleTestCase):
    def test_construct_with_typed_fields(self) -> None:
        ingest = IngestFile(
            storage_url="s3://bucket/path/file.pdf",
            model_label="search.NYCoADocument",
            pk=42,
        )
        self.assertEqual(ingest.storage_url, "s3://bucket/path/file.pdf")
        self.assertEqual(ingest.model_label, "search.NYCoADocument")
        self.assertEqual(ingest.pk, 42)
        # Defaults for AbstractPDF-style field names.
        self.assertEqual(ingest.filepath_field, "filepath_local")
        self.assertEqual(ingest.plain_text_field, "plain_text")
        # Inherited FollowUp shape.
        self.assertEqual(ingest.name, "ingest-file")
        self.assertIsInstance(ingest, FollowUp)

    def test_overridable_field_names(self) -> None:
        """Drivers using non-AbstractPDF models can override the field
        names so the dispatcher writes the right columns."""
        ingest = IngestFile(
            storage_url="s3://b/k",
            model_label="search.WhateverModel",
            pk=7,
            plain_text_field="text_body",
            sha1_field="content_hash",
        )
        self.assertEqual(ingest.plain_text_field, "text_body")
        self.assertEqual(ingest.sha1_field, "content_hash")

    def test_call_dispatches_to_celery_task(self) -> None:
        """``IngestFile()`` calls the bound ``fn`` with the
        IngestFile instance as the only positional argument."""
        ingest = IngestFile(
            storage_url="s3://b/k.pdf",
            model_label="search.Foo",
            pk=1,
        )
        with patch(
            "cl.scrapers.tasks.process_scraper_file"
        ) as mock_task:
            ingest()
        mock_task.delay.assert_called_once_with(
            storage_url="s3://b/k.pdf",
            model_label="search.Foo",
            pk=1,
            filepath_field="filepath_local",
            plain_text_field="plain_text",
            sha1_field="sha1",
            page_count_field="page_count",
            file_size_field="file_size",
            ocr_status_field="ocr_status",
        )


# ---------------------------------------------------------------------------
# KentMerger unit tests
# ---------------------------------------------------------------------------


class _SmokeMerger(KentMerger[_DocketAgg]):
    """KentMerger subclass that pulls scrape rows out of a trivial
    ``scrapes (scrape_json)`` table and feeds them straight to
    ``_DocketAgg`` validation.

    Uses ``sql_path`` pointing at a sibling smoke.sql so the
    resolution-from-subclass-module path is exercised.
    """

    aggregate_cls = _DocketAgg
    sql_path = "smoke.sql"


class KentMergerUnitTest(TransactionTestCase):
    """Base-class behavior in isolation — no real driver needed."""

    databases = {"default", "mergers_test"}

    def setUp(self) -> None:
        # Write the SQL file next to this test module so
        # ``_resolve_sql_path`` finds it.
        sql_dir = Path(__file__).parent
        (sql_dir / "smoke.sql").write_text(
            "SELECT scrape_json FROM scrapes ORDER BY rowid"
        )
        # ``TCourt`` lives in the mergers_test sqlite — the smoke
        # merger references PreResolvedRef[TCourt] but never touches
        # the DB in these unit tests (we hand-craft aggregates).
        self.court = TCourt.objects.create(
            id="ny", name="New York Court of Appeals"
        )
        self.tmp = Path(tempfile.mkdtemp(prefix="kent_smoke_"))

    def tearDown(self) -> None:
        sql_path = Path(__file__).parent / "smoke.sql"
        if sql_path.exists():
            sql_path.unlink()

    def test_sql_path_resolves_to_subclass_module_sibling(self) -> None:
        kent_db = _make_kent_db(self.tmp, rows=[("ok", "{}")])
        merger = _SmokeMerger(kent_db)
        resolved = merger._resolve_sql_path()
        self.assertEqual(
            resolved, Path(__file__).parent / "smoke.sql"
        )
        self.assertTrue(resolved.exists())

    def test_iter_scrape_rows_parses_json(self) -> None:
        rows = [
            (
                "1",
                json.dumps({"court": None, "docket_number_core": "X"}),
            ),
            (
                "2",
                json.dumps({"court": None, "docket_number_core": "Y"}),
            ),
        ]
        kent_db = _make_kent_db(self.tmp, rows=rows)
        merger = _SmokeMerger(kent_db)
        parsed = list(merger._iter_scrape_rows())
        self.assertEqual(
            [r["docket_number_core"] for r in parsed], ["X", "Y"]
        )

    def test_iter_scrape_rows_skips_null_scrape_json(self) -> None:
        # An all-NULL row (e.g. a docket with no docket_number) lands
        # as a NULL scrape_json from the SQL; the iterator should
        # silently skip rather than crashing on json.loads(None).
        rows = [("a", None), ("b", json.dumps({"court": None, "docket_number_core": "OK"}))]
        kent_db = _make_kent_db(self.tmp, rows=rows)
        merger = _SmokeMerger(kent_db)
        parsed = list(merger._iter_scrape_rows())
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["docket_number_core"], "OK")

    def test_iter_aggregates_skips_invalid_rows(self) -> None:
        """A row that fails Pydantic validation is logged and skipped;
        the rest of the run continues."""
        # First row is missing docket_number_core (required field).
        rows = [
            ("bad", json.dumps({"court": None})),
            (
                "good",
                json.dumps(
                    {"court": self.court.pk, "docket_number_core": "OK"}
                ),
            ),
        ]
        kent_db = _make_kent_db(self.tmp, rows=rows)

        class _PydMerger(_SmokeMerger):
            """Hydrate ``court`` from the pk in the JSON so the
            aggregate's PreResolvedRef[TCourt] accepts it."""

            def normalize(self, row):
                court_id = row.get("court")
                if court_id:
                    row["court"] = TCourt.objects.using("mergers_test").get(pk=court_id)
                return row

        merger = _PydMerger(kent_db, using="mergers_test")
        aggregates = list(merger.iter_aggregates())
        self.assertEqual(len(aggregates), 1)
        self.assertEqual(aggregates[0].docket_number_core, "OK")

    def test_run_accumulates_per_aggregate_outcomes(self) -> None:
        """``run()`` returns the union (via ``|``) of every
        per-aggregate ``MergeOutcome`` it produces."""
        rows = [
            (
                str(i),
                json.dumps(
                    {
                        "court": self.court.pk,
                        "docket_number_core": f"AA-{i}",
                    }
                ),
            )
            for i in range(3)
        ]
        kent_db = _make_kent_db(self.tmp, rows=rows)

        class _RealMerger(_SmokeMerger):
            def normalize(self, row):
                row["court"] = TCourt.objects.using("mergers_test").get(
                    pk=row["court"]
                )
                return row

        merger = _RealMerger(kent_db, using="mergers_test")
        outcome = merger.run()

        # Three creates, all in the TDocket bucket.
        self.assertEqual(
            len(outcome.creates.get(TDocket, set())), 3
        )

    def test_run_skips_on_per_aggregate_error(self) -> None:
        """If ``merge_one`` raises for one aggregate, the next one
        still runs."""
        rows = [
            (
                "x",
                json.dumps(
                    {"court": self.court.pk, "docket_number_core": "first"}
                ),
            ),
            (
                "y",
                json.dumps(
                    {"court": self.court.pk, "docket_number_core": "second"}
                ),
            ),
        ]
        kent_db = _make_kent_db(self.tmp, rows=rows)

        class _RealMerger(_SmokeMerger):
            def normalize(self, row):
                row["court"] = TCourt.objects.using("mergers_test").get(
                    pk=row["court"]
                )
                return row

        merger = _RealMerger(kent_db, using="mergers_test")

        from cl.scrapers.mergers import orchestrator

        original = orchestrator.merge_one
        calls = {"n": 0}

        def flaky(scrape, *, using="default"):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("simulated per-aggregate failure")
            return original(scrape, using=using)

        # Patch in the *kent* module because that's where the import lives.
        with patch(
            "cl.scrapers.mergers.kent.merge_one", side_effect=flaky
        ):
            outcome = merger.run()

        # The first aggregate's error was swallowed; only the second
        # is reflected in creates.
        self.assertEqual(
            len(outcome.creates.get(TDocket, set())), 1
        )

    def test_dispatch_ingest_files_invokes_only_ingest_records(
        self,
    ) -> None:
        """A mixed outcome with both ``FollowUp`` and ``IngestFile``
        records gets filtered; only the IngestFiles are called."""
        called: list[str] = []

        def regular_fn() -> None:
            called.append("regular")

        plain = FollowUp(name="regular", fn=regular_fn)
        ingests = [
            IngestFile(
                storage_url=f"s3://b/{i}.pdf",
                model_label="search.NYCoADocument",
                pk=i,
            )
            for i in (1, 2)
        ]
        outcome = MergeOutcome(follow_ups=[plain, *ingests])

        merger = _SmokeMerger(self.tmp / "noop.db")
        with patch(
            "cl.scrapers.tasks.process_scraper_file"
        ) as mock_task:
            returned = merger.dispatch_ingest_files(outcome)

        self.assertEqual(len(returned), 2)
        self.assertEqual(mock_task.delay.call_count, 2)
        # The regular FollowUp was not invoked.
        self.assertNotIn("regular", called)
