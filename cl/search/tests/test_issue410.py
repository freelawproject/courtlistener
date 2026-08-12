# pylint: disable=C0103
"""
Test Issue 410: Lawbox content contains CP1252 characters encoded using ISO-8859
(which fails).

The Lawbox importer (removed in commit 805877a36) decoded the corpus's HTML files
under the files' self-declared ISO-8859-1 charset. Bytes in the 0x80-0x9F range are
actually CP1252 code points (em-dash, ellipsis, Euro, smart quotes, ...), so they
were stored as the C1 control characters (U+0080-U+009F) or the replacement
character (U+FFFD). See https://github.com/freelawproject/courtlistener/issues/410

This module exercises both the pure-Python repair helpers in
``cl.lib.string_utils`` and the ``repair_lawbox_encoding`` management command in
``cl.corpus_importer``.
"""

from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from cl.lib.string_utils import (
    looks_like_lawbox_cp1252_corruption,
    repair_lawbox_cp1252,
    repair_lawbox_content_if_needed,
)


class LawboxCorruptionDetectionTest(TestCase):
    """Unit tests for ``looks_like_lawbox_cp1252_corruption``."""

    def test_detects_c1_control_block_characters(self) -> None:
        # The precise failure from the issue: byte 0x97 (CP1252 em-dash) was
        # decoded under ISO-8859-1 into U+0097 (a C1 control char).
        self.assertTrue(looks_like_lawbox_cp1252_corruption("MHL \u0097 and"))
        # 0x85 -> U+0085 (NEL, a C1 control char)
        self.assertTrue(looks_like_lawbox_cp1252_corruption("foo \u0085 bar"))
        # The bottom of the C1 block
        self.assertTrue(looks_like_lawbox_cp1252_corruption("a\u009Fb"))

    def test_detects_replacement_character(self) -> None:
        # U+FFFD is what lxml inserts when it cannot map a byte at all.
        self.assertTrue(looks_like_lawbox_cp1252_corruption("an \ufffd square"))

    def test_clean_text_is_not_flagged(self) -> None:
        self.assertFalse(looks_like_lawbox_cp1252_corruption(""))
        self.assertFalse(looks_like_lawbox_cp1252_corruption("A perfectly normal opinion."))
        # The correctly-encoded versions of the characters we are trying to
        # recover must NOT be treated as corruption.
        self.assertFalse(looks_like_lawbox_cp1252_corruption("an \u2014 em-dash"))
        self.assertFalse(looks_like_lawbox_cp1252_corruption("an \u2026 ellipsis"))
        self.assertFalse(looks_like_lawbox_cp1252_corruption("smart \u201cquotes\u201d"))
        # Accented Latin-1 characters that are valid in both ISO-8859-1 and
        # CP1252 must not be flagged.
        self.assertFalse(looks_like_lawbox_cp1252_corruption("caf\u00e9 r\u00e9sum\u00e9 na\u00efve"))

    def test_non_string_input_is_safe(self) -> None:
        self.assertFalse(looks_like_lawbox_cp1252_corruption(None))  # type: ignore[arg-type]
        self.assertFalse(looks_like_lawbox_cp1252_corruption(123))  # type: ignore[arg-type]


class LawboxCorruptionRepairTest(TestCase):
    """Unit tests for ``repair_lawbox_cp1252``."""

    def test_repairs_c1_em_dash_to_real_em_dash(self) -> None:
        # The exact corruption from the issue's footnote four:
        # "...the interpretation of the MHL \u0097 and the amount of discretion..."
        corrupt = "the MHL \u0097 and the amount of discretion"
        self.assertEqual(
            repair_lawbox_cp1252(corrupt),
            "the MHL \u2014 and the amount of discretion",
        )

    def test_repairs_c1_ellipsis(self) -> None:
        # 0x85 (CP1252 ellipsis) -> U+0085 (C1 NEL) -> \u2026 (real ellipsis)
        self.assertEqual(repair_lawbox_cp1252("and so on\u0085"), "and so on\u2026")

    def test_repairs_multiple_markers(self) -> None:
        corrupt = "MHL \u0097 discretion \u0086 and \u0091quotes\u0092"
        repaired = repair_lawbox_cp1252(corrupt)
        # Every C1 marker should have been re-mapped through CP1252.
        self.assertNotIn("\u0097", repaired)
        self.assertNotIn("\u0086", repaired)
        self.assertNotIn("\u0091", repaired)
        self.assertNotIn("\u0092", repaired)
        # The em-dash should now be the real character.
        self.assertIn("\u2014", repaired)

    def test_clean_text_is_returned_unchanged(self) -> None:
        clean = "An em-dash \u2014 and ellipsis \u2026 and caf\u00e9."
        self.assertEqual(repair_lawbox_cp1252(clean), clean)
        # Identical object, not a fresh copy, for the genuine no-op case.
        clean_unique = "no corruption here at all"
        self.assertIs(repair_lawbox_cp1252(clean_unique), clean_unique)

    def test_mixed_content_is_left_unchanged(self) -> None:
        # A document that already contains a genuine high-codepoint character
        # (a real em-dash U+2014) alongside a corruption marker is mixed
        # content: the latin-1 re-encode would destroy the good character, so
        # the repair must refuse and return the input verbatim.
        mixed = "real \u2014 dash but corrupt \u0097 marker"
        self.assertEqual(repair_lawbox_cp1252(mixed), mixed)

    def test_idempotent(self) -> None:
        corrupt = "the MHL \u0097 and discretion"
        once = repair_lawbox_cp1252(corrupt)
        twice = repair_lawbox_cp1252(once)
        self.assertEqual(once, twice)
        # Once repaired, the text is clean so a second pass is a true no-op.
        self.assertFalse(looks_like_lawbox_cp1252_corruption(twice))

    def test_empty_and_non_string_inputs_are_safe(self) -> None:
        self.assertEqual(repair_lawbox_cp1252(""), "")
        self.assertIsNone(repair_lawbox_cp1252(None))  # type: ignore[arg-type]

    def test_repair_wrapper_reports_changed_flag(self) -> None:
        corrupt = "MHL \u0097 discretion"
        repaired, changed = repair_lawbox_content_if_needed(corrupt)
        self.assertTrue(changed)
        self.assertEqual(repaired, "MHL \u2014 discretion")

        clean = "already clean text"
        same, changed = repair_lawbox_content_if_needed(clean)
        self.assertFalse(changed)
        self.assertEqual(same, clean)


class RepairLawboxEncodingCommandTest(TestCase):
    """End-to-end tests for the ``repair_lawbox_encoding`` management command.

    Elasticsearch indexing is disabled by patching
    ``cl.lib.es_signal_processor.update_es_documents``, the same pattern used
    elsewhere in the test suite (see cl/search/tests/tests_es_recap.py). The
    citation annotation celery task is mocked so we can assert on its dispatch
    without running the full citation pipeline.
    """

    # The corruption marker from issue #410 (byte 0x97 mis-decoded as U+0097).
    MARKER = "\u0097"
    REPAIRED = "\u2014"

    def _make_corrupt_opinion(self) -> "Opinion":
        from cl.search.factories import OpinionWithParentsFactory
        from cl.search.models import Opinion

        html = f"<p>the MHL {self.MARKER} and discretion</p>"
        return OpinionWithParentsFactory(html_lawbox=html, plain_text="")

    @patch("cl.lib.es_signal_processor.update_es_documents")
    @patch(
        "cl.corpus_importer.management.commands.repair_lawbox_encoding."
        "find_citations_and_parentheticals_for_opinion_by_pks"
    )
    def test_repairs_corrupt_html_lawbox(
        self, mock_annotate, mock_update_es
    ) -> None:
        opinion = self._make_corrupt_opinion()
        call_command("repair_lawbox_encoding", doc_id=[opinion.pk])
        opinion.refresh_from_db()
        self.assertIn(self.REPAIRED, opinion.html_lawbox)
        self.assertNotIn(self.MARKER, opinion.html_lawbox)
        # The corruption repair should have dispatched the annotation task so
        # that html_with_citations (which is derived from html_lawbox) is
        # regenerated from the now-clean source.
        mock_annotate.apply_async.assert_called_once()
        # The command dispatches with apply_async(args=(pks, ...), queue=...),
        # i.e. via the ``args`` keyword, so read it through ``call_args.kwargs``
        # (the repository convention for keyword-argument mock inspection, see
        # e.g. cl/simple_pages/tests.py). ``kwargs["args"][0]`` is the list of
        # repaired opinion PKs passed to the annotation task.
        self.assertEqual(
            mock_annotate.apply_async.call_args.kwargs["args"][0],
            [opinion.pk],
        )

    @patch("cl.lib.es_signal_processor.update_es_documents")
    @patch(
        "cl.corpus_importer.management.commands.repair_lawbox_encoding."
        "find_citations_and_parentheticals_for_opinion_by_pks"
    )
    def test_dry_run_leaves_db_unchanged(
        self, mock_annotate, mock_update_es
    ) -> None:
        opinion = self._make_corrupt_opinion()
        original = opinion.html_lawbox
        call_command("repair_lawbox_encoding", doc_id=[opinion.pk], dry_run=True)
        opinion.refresh_from_db()
        self.assertEqual(opinion.html_lawbox, original)
        # Dry-run never mutates the DB, so there is nothing to re-annotate.
        mock_annotate.apply_async.assert_not_called()

    @patch("cl.lib.es_signal_processor.update_es_documents")
    @patch(
        "cl.corpus_importer.management.commands.repair_lawbox_encoding."
        "find_citations_and_parentheticals_for_opinion_by_pks"
    )
    def test_skip_annotate_suppresses_dispatch(
        self, mock_annotate, mock_update_es
    ) -> None:
        opinion = self._make_corrupt_opinion()
        call_command(
            "repair_lawbox_encoding",
            doc_id=[opinion.pk],
            skip_annotate=True,
        )
        opinion.refresh_from_db()
        # The DB row still got repaired ...
        self.assertIn(self.REPAIRED, opinion.html_lawbox)
        self.assertNotIn(self.MARKER, opinion.html_lawbox)
        # ... but the annotation task was NOT dispatched.
        mock_annotate.apply_async.assert_not_called()

    @patch("cl.lib.es_signal_processor.update_es_documents")
    @patch(
        "cl.corpus_importer.management.commands.repair_lawbox_encoding."
        "find_citations_and_parentheticals_for_opinion_by_pks"
    )
    def test_clean_opinion_not_modified_nor_annotated(
        self, mock_annotate, mock_update_es
    ) -> None:
        # An opinion with no corruption markers is a no-op for the command:
        # the row is not modified and nothing is dispatched.
        from cl.search.factories import OpinionWithParentsFactory

        clean_html = "<p>an em-dash \u2014 and ellipsis \u2026</p>"
        opinion = OpinionWithParentsFactory(
            html_lawbox=clean_html, plain_text=""
        )
        call_command("repair_lawbox_encoding", doc_id=[opinion.pk])
        opinion.refresh_from_db()
        self.assertEqual(opinion.html_lawbox, clean_html)
        mock_annotate.apply_async.assert_not_called()

    @patch("cl.lib.es_signal_processor.update_es_documents")
    @patch(
        "cl.corpus_importer.management.commands.repair_lawbox_encoding."
        "find_citations_and_parentheticals_for_opinion_by_pks"
    )
    def test_id_range_filters_queryset(
        self, mock_annotate, mock_update_es
    ) -> None:
        corrupt_a = self._make_corrupt_opinion()
        # A second corrupt opinion deliberately outside the requested range.
        corrupt_b = self._make_corrupt_opinion()
        call_command(
            "repair_lawbox_encoding",
            start_id=corrupt_a.pk,
            end_id=corrupt_a.pk,
        )
        corrupt_a.refresh_from_db()
        corrupt_b.refresh_from_db()
        self.assertNotIn(self.MARKER, corrupt_a.html_lawbox)
        # corrupt_b was outside the [start_id, end_id] window, so it is
        # untouched and still contains the corruption marker.
        self.assertIn(self.MARKER, corrupt_b.html_lawbox)
        # Only corrupt_a (the in-range opinion) should be re-annotated. The
        # command dispatches with apply_async(args=(pks, ...), queue=...), so
        # the repaired-PK list is call_args.kwargs["args"][0].
        self.assertEqual(
            mock_annotate.apply_async.call_args.kwargs["args"][0],
            [corrupt_a.pk],
        )

    @patch("cl.lib.es_signal_processor.update_es_documents")
    @patch(
        "cl.corpus_importer.management.commands.repair_lawbox_encoding."
        "find_citations_and_parentheticals_for_opinion_by_pks"
    )
    def test_repairs_opinioncontent_lawbox_rows(
        self, mock_annotate, mock_update_es
    ) -> None:
        # OpinionContent (migration 0055) is the normalized successor of the
        # html_lawbox field. If a LAWBOX-sourced OpinionContent row shares the
        # corruption, the command repairs it in the same pass.
        from cl.search.models import OpinionContent

        opinion = self._make_corrupt_opinion()
        OpinionContent.objects.create(
            opinion=opinion,
            content=f"content {self.MARKER} here",
            source=OpinionContent.LAWBOX,
            extraction_type=OpinionContent.DEFAULT,
            is_main_version=True,
        )
        call_command("repair_lawbox_encoding", doc_id=[opinion.pk])
        content = OpinionContent.objects.get(opinion=opinion)
        self.assertNotIn(self.MARKER, content.content)
        self.assertIn(self.REPAIRED, content.content)
