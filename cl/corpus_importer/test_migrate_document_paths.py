import csv
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from unittest import mock

import time_machine
from botocore.exceptions import ClientError
from django.core.management import CommandError, call_command

from cl.corpus_importer.management.commands import (
    migrate_document_paths as command_module,
)
from cl.corpus_importer.management.commands.migrate_document_paths import (
    MIGRATED,
    PLANNED,
    SPECS,
    S3Target,
    build_new_key,
    compose_redis_key,
    group_rows_by_docket,
)
from cl.lib import recap_utils
from cl.lib.indexing_utils import log_last_document_indexed
from cl.lib.recap_utils import (
    format_path_date,
    make_recap_style_path,
    scotus_document_number_segments,
)
from cl.lib.redis_utils import get_redis_interface
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    SCOTUSDocketEntryFactory,
    ScotusDocketMetadataFactory,
    SCOTUSDocumentFactory,
)
from cl.search.state.florida.factories import (
    FloridaDocketEntryFactory,
    FloridaDocumentFactory,
)
from cl.search.state.florida.models import florida_local_date
from cl.search.state.texas.factories import (
    TexasDocketEntryFactory,
    TexasDocumentFactory,
)
from cl.tests.cases import SimpleTestCase, TestCase


class FakeS3Client:
    """Minimal stand-in for boto3's S3 client: objects are keys mapped to
    ETags, and every copy is recorded for assertions."""

    def __init__(self, objects: dict[str, str]) -> None:
        self.objects = dict(objects)
        self.copies: list[tuple[str, str, dict]] = []

    def head_object(self, Bucket: str, Key: str) -> dict:
        if Key not in self.objects:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
        return {"ETag": self.objects[Key], "ContentLength": 3}

    def copy_object(self, Bucket: str, CopySource: dict, Key: str, **kwargs):
        etag = self.objects[CopySource["Key"]]
        self.objects[Key] = etag
        self.copies.append((CopySource["Key"], Key, kwargs))
        return {"CopyObjectResult": {"ETag": self.copied_etag(etag)}}

    def copied_etag(self, etag: str) -> str:
        """What the copy reports back; overridden to simulate corruption."""
        return etag

    def get_paginator(self, name: str):
        objects = self.objects

        class Paginator:
            def paginate(self, Bucket: str, Prefix: str):
                matches = [k for k in objects if k.startswith(Prefix)]
                yield {"KeyCount": len(matches)}

        return Paginator()


class CorruptingS3Client(FakeS3Client):
    """Reports a different ETag after every copy."""

    def copied_etag(self, etag: str) -> str:
        return f"{etag}-corrupt"


def patch_s3(client: FakeS3Client):
    """Point the command at a fake client instead of the field's storage."""
    return mock.patch.object(
        command_module,
        "get_s3_target",
        return_value=S3Target(
            client=client, bucket="bucket", acl="public-read"
        ),
    )


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


class RecapStylePathHelpersTest(SimpleTestCase):
    """The pure path-building helpers shared by the models and the command."""

    def test_format_path_date(self) -> None:
        self.assertEqual(format_path_date(date(2024, 3, 5)), "2024-03-05")
        self.assertEqual(format_path_date(None), "undated")

    def test_make_recap_style_path(self) -> None:
        self.assertEqual(
            make_recap_style_path(
                "scotus", 12, ["2024-03-05", "3", "1"], ".pdf"
            ),
            "recap/gov.uscourts.scotus.12/gov.uscourts.scotus.12.2024-03-05.3.1.pdf",
        )
        self.assertEqual(
            make_recap_style_path(
                "tex", 7, ["undated", "99"], ".html", thumbs=True
            ),
            "recap-thumbnails/gov.uscourts.tex.7/gov.uscourts.tex.7.undated.99.html",
        )

    def test_scotus_number_segments_follow_recap_convention(self) -> None:
        self.assertEqual(scotus_document_number_segments(3, 1, 1), ["3", "1"])
        # The test runner disables logging, so assert on the logger itself.
        with mock.patch.object(recap_utils.logger, "error") as mock_error:
            self.assertEqual(
                scotus_document_number_segments(None, None, 5), ["", "0"]
            )
        self.assertEqual(mock_error.call_count, 2)
        self.assertIn("no document_number", mock_error.call_args_list[0][0][0])
        self.assertIn(
            "no attachment_number", mock_error.call_args_list[1][0][0]
        )

    def test_florida_local_date_uses_court_timezone(self) -> None:
        """The UTC-to-local offset is 5 hours under standard time and 4 under
        daylight saving time, so the day boundary moves with the season."""
        cases = {
            "EST, last minute of the previous day": (
                datetime(2024, 1, 2, 4, 59, tzinfo=UTC),
                date(2024, 1, 1),
            ),
            "EST, first minute of the day": (
                datetime(2024, 1, 2, 5, 0, tzinfo=UTC),
                date(2024, 1, 2),
            ),
            "EDT, last minute of the previous day": (
                datetime(2024, 7, 2, 3, 59, tzinfo=UTC),
                date(2024, 7, 1),
            ),
            "EDT, first minute of the day": (
                datetime(2024, 7, 2, 4, 0, tzinfo=UTC),
                date(2024, 7, 2),
            ),
            # DST starts 2024-03-10 at 07:00 UTC; 06:59 UTC is still EST.
            "spring forward, before the switch": (
                datetime(2024, 3, 10, 6, 59, tzinfo=UTC),
                date(2024, 3, 10),
            ),
            "spring forward, after the switch": (
                datetime(2024, 3, 11, 3, 59, tzinfo=UTC),
                date(2024, 3, 10),
            ),
        }
        for label, (value, expected) in cases.items():
            with self.subTest(label):
                self.assertEqual(florida_local_date(value), expected)
        self.assertIsNone(florida_local_date(None))

    def test_build_new_key_per_spec(self) -> None:
        """Each spec builds its key from the right row fields, with the
        entry date (or the docket date for QP files) rendered as `undated`
        when missing."""
        scotus_row = {
            "pk": 1,
            "filepath_local": "scotus/documents/gov.scotus.x.pdf",
            "docket_entry__docket_id": 12,
            "docket_entry__docket__court_id": "scotus",
            "docket_entry__date_filed": date(2024, 3, 5),
            "document_number": 3,
            "attachment_number": 1,
        }
        qp_row = {
            "pk": 1,
            "questions_presented_file": "scotus/qp/gov.scotus.12-qp.pdf",
            "docket_id": 12,
            "docket__court_id": "scotus",
            "docket__date_filed": date(2024, 1, 15),
        }
        texas_row = {
            "pk": 44,
            "filepath_local": "us/state/tx/tex/gov.tx.tex.abc.html",
            "docket_entry__docket_id": 7,
            "docket_entry__docket__court_id": "tex",
            "docket_entry__date_filed": date(2023, 12, 31),
        }
        florida_row = {
            "pk": 45,
            "filepath_local": "us/state/fl/fla/gov.fl.fla.abc.tiff",
            "docket_entry__docket_id": 8,
            "docket_entry__docket__court_id": "fla",
            "docket_entry__date_filed": datetime(2024, 1, 2, 3, tzinfo=UTC),
        }
        cases = [
            (
                "scotus",
                scotus_row,
                "recap/gov.uscourts.scotus.12/gov.uscourts.scotus.12.2024-03-05.3.1.pdf",
            ),
            (
                "scotus",
                {**scotus_row, "docket_entry__date_filed": None},
                "recap/gov.uscourts.scotus.12/gov.uscourts.scotus.12.undated.3.1.pdf",
            ),
            (
                "scotus-qp",
                qp_row,
                "recap/gov.uscourts.scotus.12/gov.uscourts.scotus.12.2024-01-15.qp.pdf",
            ),
            (
                "scotus-qp",
                {**qp_row, "docket__date_filed": None},
                "recap/gov.uscourts.scotus.12/gov.uscourts.scotus.12.undated.qp.pdf",
            ),
            (
                "texas",
                texas_row,
                "recap/gov.uscourts.tex.7/gov.uscourts.tex.7.2023-12-31.44.html",
            ),
            (
                "texas",
                {**texas_row, "docket_entry__date_filed": None},
                "recap/gov.uscourts.tex.7/gov.uscourts.tex.7.undated.44.html",
            ),
            (
                "florida",
                florida_row,
                "recap/gov.uscourts.fla.8/gov.uscourts.fla.8.2024-01-01.45.tiff",
            ),
            (
                "florida",
                {**florida_row, "docket_entry__date_filed": None},
                "recap/gov.uscourts.fla.8/gov.uscourts.fla.8.undated.45.tiff",
            ),
        ]
        for spec_name, row, expected in cases:
            with self.subTest(spec=spec_name, expected=expected):
                self.assertEqual(
                    build_new_key(SPECS[spec_name], row), expected
                )

    def test_group_rows_by_docket_preserves_order(self) -> None:
        rows = [
            {"pk": 1, "d": 10},
            {"pk": 2, "d": 20},
            {"pk": 3, "d": 10},
        ]
        self.assertEqual(
            group_rows_by_docket(rows, "d"),
            [[rows[0], rows[2]], [rows[1]]],
        )


class ModelPdfPathTest(TestCase):
    """`get_pdf_path` on each model produces the RECAP layout for new uploads."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scotus = CourtFactory(id="scotus")
        cls.docket = DocketFactory(
            court=cls.scotus, date_filed=date(2024, 1, 15)
        )
        cls.entry = SCOTUSDocketEntryFactory(
            docket=cls.docket, date_filed=date(2024, 3, 5)
        )
        cls.tex = CourtFactory(id="tex")
        cls.fla = CourtFactory(id="fla")

    def test_scotus_document(self) -> None:
        doc = SCOTUSDocumentFactory(
            docket_entry=self.entry, document_number=3, attachment_number=1
        )
        d = self.docket.pk
        self.assertEqual(
            doc.get_pdf_path("scotus.24-123.3.1.pdf"),
            f"recap/gov.uscourts.scotus.{d}/gov.uscourts.scotus.{d}.2024-03-05.3.1.pdf",
        )
        self.assertTrue(
            doc.get_pdf_path("x.pdf", thumbs=True).startswith(
                "recap-thumbnails/"
            )
        )

    def test_questions_presented_file(self) -> None:
        meta = ScotusDocketMetadataFactory(docket=self.docket)
        d = self.docket.pk
        self.assertEqual(
            meta.get_pdf_path(f"{d}-qp.pdf"),
            f"recap/gov.uscourts.scotus.{d}/gov.uscourts.scotus.{d}.2024-01-15.qp.pdf",
        )

    def test_texas_document_keeps_extension(self) -> None:
        docket = DocketFactory(court=self.tex)
        entry = TexasDocketEntryFactory(
            docket=docket, date_filed=None, sequence_number="undated.1"
        )
        doc = TexasDocumentFactory(docket_entry=entry)
        d = docket.pk
        self.assertEqual(
            doc.get_pdf_path("abc.html"),
            f"recap/gov.uscourts.tex.{d}/gov.uscourts.tex.{d}.undated.{doc.pk}.html",
        )

    def test_state_document_path_requires_saved_document(self) -> None:
        entry = TexasDocketEntryFactory(docket=DocketFactory(court=self.tex))
        unsaved = TexasDocumentFactory.build(docket_entry=entry)
        with self.assertRaises(ValueError):
            unsaved.get_pdf_path("abc.pdf")

    def test_florida_document_uses_local_date(self) -> None:
        docket = DocketFactory(court=self.fla)
        entry = FloridaDocketEntryFactory(
            docket=docket, date_filed=datetime(2024, 1, 2, 3, tzinfo=UTC)
        )
        doc = FloridaDocumentFactory(docket_entry=entry)
        d = docket.pk
        self.assertEqual(
            doc.get_pdf_path("abc.tiff"),
            f"recap/gov.uscourts.fla.{d}/gov.uscourts.fla.{d}.2024-01-01.{doc.pk}.tiff",
        )


class MigrateDocumentPathsCommandTest(TestCase):
    """End-to-end runs of the command against a fake S3 client."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory(id="scotus")
        cls.docket = DocketFactory(court=cls.court)
        cls.entry = SCOTUSDocketEntryFactory(
            docket=cls.docket, date_filed=date(2024, 3, 5)
        )
        cls.doc = SCOTUSDocumentFactory(
            docket_entry=cls.entry,
            document_number=3,
            attachment_number=1,
            filepath_local="scotus/documents/gov.scotus.a.pdf",
        )
        # Same docket, date and numbers on another entry: a duplicate key.
        cls.dup_entry = SCOTUSDocketEntryFactory(
            docket=cls.docket, date_filed=date(2024, 3, 5)
        )
        cls.dup = SCOTUSDocumentFactory(
            docket_entry=cls.dup_entry,
            document_number=3,
            attachment_number=1,
            filepath_local="scotus/documents/gov.scotus.b.pdf",
        )
        cls.missing = SCOTUSDocumentFactory(
            docket_entry=cls.entry,
            document_number=4,
            attachment_number=1,
            filepath_local="scotus/documents/gov.scotus.gone.pdf",
        )
        d = cls.docket.pk
        cls.bucket = f"recap/gov.uscourts.scotus.{d}"
        cls.done = SCOTUSDocumentFactory(
            docket_entry=cls.entry,
            document_number=5,
            attachment_number=1,
            filepath_local=f"{cls.bucket}/gov.uscourts.scotus.{d}.2024-03-05.5.1.pdf",
        )
        cls.expected_key = (
            f"{cls.bucket}/gov.uscourts.scotus.{d}.2024-03-05.3.1.pdf"
        )
        cls.expected_dup_key = (
            f"{cls.bucket}/gov.uscourts.scotus.{d}.2024-03-05.3.1_1.pdf"
        )

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manifest = Path(self.tmp.name) / "manifest.csv"
        self.client = FakeS3Client(
            {
                self.doc.filepath_local.name: '"etaga"',
                self.dup.filepath_local.name: '"etagb"',
            }
        )
        self.addCleanup(
            get_redis_interface("CACHE").delete, compose_redis_key("scotus")
        )

    def run_command(self, client: FakeS3Client | None = None, **options):
        with patch_s3(client or self.client):
            call_command(
                "migrate_document_paths",
                model="scotus",
                manifest=self.manifest,
                **options,
            )

    @time_machine.travel(datetime(2026, 9, 17, 12, tzinfo=UTC), tick=False)
    def test_migrates_pending_rows(self) -> None:
        with (
            mock.patch.object(command_module.logger, "warning") as m_warning,
            mock.patch.object(command_module.logger, "error") as m_error,
        ):
            self.run_command()

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.filepath_local.name, self.expected_key)
        self.assertEqual(
            self.doc.date_modified, datetime(2026, 9, 17, 12, tzinfo=UTC)
        )
        # The duplicate got a suffix and a warning naming it.
        self.dup.refresh_from_db()
        self.assertEqual(self.dup.filepath_local.name, self.expected_dup_key)
        m_warning.assert_called_once()
        self.assertIn("already taken", m_warning.call_args[0][0])
        self.assertEqual(m_warning.call_args[0][2], self.dup.pk)
        # Missing source: error logged, row untouched.
        self.missing.refresh_from_db()
        self.assertEqual(
            self.missing.filepath_local.name,
            "scotus/documents/gov.scotus.gone.pdf",
        )
        m_error.assert_called_once()
        self.assertIn("does not exist in S3", m_error.call_args[0][0])
        self.assertEqual(m_error.call_args[0][2], self.missing.pk)
        # Already-migrated rows aren't selected at all.
        self.done.refresh_from_db()
        self.assertNotIn(
            self.done.filepath_local.name,
            [old_key for old_key, _, _ in self.client.copies],
        )

        self.assertEqual(
            self.client.copies,
            [
                (
                    "scotus/documents/gov.scotus.a.pdf",
                    self.expected_key,
                    {"MetadataDirective": "COPY", "ACL": "public-read"},
                ),
                (
                    "scotus/documents/gov.scotus.b.pdf",
                    self.expected_dup_key,
                    {"MetadataDirective": "COPY", "ACL": "public-read"},
                ),
            ],
        )
        self.assertEqual(
            read_manifest(self.manifest),
            [
                {
                    "pk": str(self.doc.pk),
                    "old_key": "scotus/documents/gov.scotus.a.pdf",
                    "new_key": self.expected_key,
                    "status": MIGRATED,
                },
                {
                    "pk": str(self.dup.pk),
                    "old_key": "scotus/documents/gov.scotus.b.pdf",
                    "new_key": self.expected_dup_key,
                    "status": MIGRATED,
                },
            ],
        )

    def test_rerun_only_touches_leftovers(self) -> None:
        self.run_command()
        self.client.copies.clear()
        self.run_command()
        # Only the row whose source is missing is retried; it can't be copied.
        self.assertEqual(self.client.copies, [])
        statuses = [row["status"] for row in read_manifest(self.manifest)]
        self.assertEqual(statuses, [MIGRATED, MIGRATED])

    def test_dry_run_changes_nothing(self) -> None:
        self.run_command(dry_run=True)
        self.assertEqual(self.client.copies, [])
        self.doc.refresh_from_db()
        self.assertEqual(
            self.doc.filepath_local.name, "scotus/documents/gov.scotus.a.pdf"
        )
        manifest = read_manifest(self.manifest)
        self.assertEqual({row["status"] for row in manifest}, {PLANNED})
        # Nothing is updated in a dry run, so the guard can't see the first
        # row's claim: duplicates surface as repeated planned keys instead.
        self.assertEqual(
            [row["new_key"] for row in manifest][:2],
            [self.expected_key, self.expected_key],
        )

    def test_limit(self) -> None:
        self.run_command(limit=1)
        self.assertEqual(len(self.client.copies), 1)
        self.dup.refresh_from_db()
        self.assertEqual(
            self.dup.filepath_local.name, "scotus/documents/gov.scotus.b.pdf"
        )

    def test_etag_mismatch_leaves_row_unchanged(self) -> None:
        client = CorruptingS3Client(self.client.objects)
        with mock.patch.object(command_module.logger, "error") as m_error:
            self.run_command(client=client)
        self.doc.refresh_from_db()
        self.assertEqual(
            self.doc.filepath_local.name, "scotus/documents/gov.scotus.a.pdf"
        )
        self.assertTrue(
            any(
                "ETag mismatch" in call[0][0]
                for call in m_error.call_args_list
            )
        )
        self.assertEqual(read_manifest(self.manifest), [])

    def test_auto_resume_skips_logged_pks(self) -> None:
        log_last_document_indexed(self.doc.pk, compose_redis_key("scotus"))
        self.run_command(auto_resume=True)
        self.doc.refresh_from_db()
        self.assertEqual(
            self.doc.filepath_local.name, "scotus/documents/gov.scotus.a.pdf"
        )
        self.dup.refresh_from_db()
        # With the first row skipped, the duplicate takes the plain key.
        self.assertEqual(self.dup.filepath_local.name, self.expected_key)

    def test_check_destination_counts_objects(self) -> None:
        self.client.objects[f"{self.bucket}/stray.pdf"] = '"x"'
        with mock.patch.object(command_module.logger, "info") as m_info:
            self.run_command(check_destination=True)
        self.assertEqual(self.client.copies, [])
        m_info.assert_called_once_with(
            "%s: %s objects", "recap/gov.uscourts.scotus.", 1
        )

    def test_manifest_is_required(self) -> None:
        with patch_s3(self.client), self.assertRaises(CommandError):
            call_command("migrate_document_paths", model="scotus")
