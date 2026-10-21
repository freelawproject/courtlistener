"""
Tests for the ``repair_lawbox_encoding`` management command and its helpers.

The Lawbox importer (removed in commit 805877a36) decoded the corpus's HTML
files under the files' self-declared ISO-8859-1 charset. Bytes in the 0x80-0x9F
range are actually CP1252 code points (em-dash, ellipsis, Euro, smart quotes,
...), so they were stored as the C1 control characters (U+0080-U+009F) or the
replacement character (U+FFFD). GitHub issue:
https://github.com/freelawproject/courtlistener/issues/410

This module exercises both the pure-Python repair helpers in
``cl.lib.string_utils`` and the ``repair_lawbox_encoding`` management command in
``cl.corpus_importer``, plus the source-priority rule that decides which
repaired opinions need their citations re-annotated.
"""

from unittest.mock import patch

from django.core.management import call_command

from cl.citations.utils import (
    lawbox_is_citation_source,
    lawbox_is_citation_source_filter,
)
from cl.lib.string_utils import (
    looks_like_lawbox_cp1252_corruption,
    repair_lawbox_content_if_needed,
    repair_lawbox_cp1252,
)
from cl.search.cluster_sources import ClusterSources
from cl.search.factories import OpinionWithParentsFactory
from cl.search.models import Opinion, OpinionContent
from cl.tests.cases import TestCase

# The markers from issue #410, named so the tests read as prose.
C1_EM_DASH = "\u0097"  # byte 0x97, which CP1252 defines as an em-dash
C1_ELLIPSIS = "\u0085"  # byte 0x85, which CP1252 defines as an ellipsis
C1_LEFT_QUOTE = "\u0091"  # byte 0x91, a left single quotation mark
REAL_EM_DASH = "\u2014"
REAL_ELLIPSIS = "\u2026"
REAL_LEFT_QUOTE = "\u201c"
REAL_RIGHT_QUOTE = "\u201d"
REPLACEMENT_CHAR = "\ufffd"

# The five C1 bytes CP1252 leaves undefined. They are detectable, but there is
# no character to recover for them.
UNDEFINED_C1 = ("\u0081", "\u008d", "\u008f", "\u0090", "\u009d")


class LawboxCorruptionDetectionTest(TestCase):
    """Unit tests for ``looks_like_lawbox_cp1252_corruption``."""

    def test_detects_c1_control_block_characters(self) -> None:
        # The precise failure from the issue: byte 0x97 (CP1252 em-dash) was
        # decoded under ISO-8859-1 into U+0097 (a C1 control char).
        self.assertTrue(
            looks_like_lawbox_cp1252_corruption("MHL \u0097 and")
        )
        # 0x85 -> U+0085 (NEL, a C1 control char)
        self.assertTrue(looks_like_lawbox_cp1252_corruption("foo \u0085 bar"))
        # The bottom of the C1 block
        self.assertTrue(looks_like_lawbox_cp1252_corruption("a\u009fb"))

    def test_detects_replacement_character(self) -> None:
        # U+FFFD is what lxml inserts when it cannot map a byte at all.
        self.assertTrue(
            looks_like_lawbox_cp1252_corruption("an \ufffd square")
        )

    def test_detects_undefined_c1_bytes(self) -> None:
        # CP1252 leaves these five bytes undefined, so there is nothing to
        # recover for them, but they still mark the row as suspect.
        for marker in UNDEFINED_C1:
            with self.subTest(marker=hex(ord(marker))):
                self.assertTrue(
                    looks_like_lawbox_cp1252_corruption(f"a {marker} b")
                )

    def test_clean_text_is_not_flagged(self) -> None:
        self.assertFalse(looks_like_lawbox_cp1252_corruption(""))
        self.assertFalse(
            looks_like_lawbox_cp1252_corruption("A perfectly normal opinion.")
        )
        # The correctly-encoded versions of the characters we are trying to
        # recover must NOT be treated as corruption.
        self.assertFalse(
            looks_like_lawbox_cp1252_corruption("an \u2014 em-dash")
        )
        self.assertFalse(
            looks_like_lawbox_cp1252_corruption("an \u2026 ellipsis")
        )
        self.assertFalse(
            looks_like_lawbox_cp1252_corruption("smart \u201cquotes\u201d")
        )
        # Accented Latin-1 characters that are valid in both ISO-8859-1 and
        # CP1252 must not be flagged.
        self.assertFalse(
            looks_like_lawbox_cp1252_corruption(
                "caf\u00e9 r\u00e9sum\u00e9 na\u00efve"
            )
        )

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
        # 0x85 (CP1252 ellipsis) -> U+0085 (C1 NEL) -> U+2026 (real ellipsis)
        self.assertEqual(
            repair_lawbox_cp1252("and so on\u0085"), "and so on\u2026"
        )

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

    def test_latin1_supplement_characters_are_preserved(self) -> None:
        # U+00E9 and U+00FF are the top of latin-1, so they round-trip safely
        # and must survive the repair alongside a marker.
        self.assertEqual(
            repair_lawbox_cp1252("caf\u00e9 r\u00e9sum\u00e9 \u0097"),
            "caf\u00e9 r\u00e9sum\u00e9 \u2014",
        )

    def test_genuine_high_codepoints_survive_a_marker(self) -> None:
        # Regression: a latin-1 re-encode would destroy these, which used to
        # make the whole row unrecoverable.
        mixed = (
            f"a real {REAL_EM_DASH} dash, {REAL_LEFT_QUOTE}smart"
            f"{REAL_RIGHT_QUOTE} quotes, a {REAL_ELLIPSIS} ellipsis, and "
            f"\u6cd5\u9662 CJK next to a {C1_EM_DASH} marker"
        )
        repaired = repair_lawbox_cp1252(mixed)
        self.assertNotIn(C1_EM_DASH, repaired)
        # Every genuine character is still there, and the marker became one.
        self.assertIn(REAL_EM_DASH, repaired)
        self.assertIn(REAL_LEFT_QUOTE, repaired)
        self.assertIn(REAL_RIGHT_QUOTE, repaired)
        self.assertIn(REAL_ELLIPSIS, repaired)
        self.assertIn("\u6cd5\u9662", repaired)
        # The original em-dash plus the repaired one.
        self.assertEqual(repaired.count(REAL_EM_DASH), 2)

    def test_replacement_character_is_detected_but_not_repaired(self) -> None:
        # U+FFFD cannot be encoded to latin-1, so it can never be mapped back
        # to the byte it came from. It still flags the row as suspect.
        only_marker = "an \ufffd square"
        self.assertTrue(looks_like_lawbox_cp1252_corruption(only_marker))
        self.assertEqual(repair_lawbox_cp1252(only_marker), only_marker)

    def test_undefined_c1_bytes_are_detected_but_not_repaired(self) -> None:
        for marker in UNDEFINED_C1:
            with self.subTest(marker=hex(ord(marker))):
                text = f"a {marker} b"
                self.assertEqual(repair_lawbox_cp1252(text), text)

    def test_repairs_markers_next_to_unrecoverable_ones(self) -> None:
        # Regression: the old latin-1 round-trip raised on the U+FFFD and
        # returned the row untouched, so the recoverable em-dash beside it was
        # silently lost too.
        self.assertEqual(
            repair_lawbox_cp1252("an \ufffd square and \u0097 more"),
            "an \ufffd square and \u2014 more",
        )
        self.assertEqual(
            repair_lawbox_cp1252("a \u0081 b and \u0097 c"),
            "a \u0081 b and \u2014 c",
        )

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

        # Markers that cannot be repaired are reported as "not changed", so
        # the command can tell the two situations apart.
        unrecoverable = "an \ufffd square"
        same, changed = repair_lawbox_content_if_needed(unrecoverable)
        self.assertFalse(changed)
        self.assertEqual(same, unrecoverable)


class RepairLawboxEncodingCommandTest(TestCase):
    """End-to-end tests for the ``repair_lawbox_encoding`` management command.

    Elasticsearch indexing is disabled by patching
    ``cl.lib.es_signal_processor.update_es_documents``, the same pattern used
    elsewhere in the test suite (see cl/search/tests/tests_es_recap.py). The
    citation annotation celery task is mocked so we can assert on its dispatch
    without running the full citation pipeline.
    """

    # The corruption marker from issue #410 (byte 0x97 mis-decoded as U+0097).
    MARKER = C1_EM_DASH
    REPAIRED = REAL_EM_DASH

    def setUp(self) -> None:
        super().setUp()
        # CeleryThrottle polls the live Celery queue through Redis. That is
        # not what these tests exercise, and leaving it live would make them
        # depend on a running broker, so replace it with a no-op mock.
        throttle = patch(
            "cl.corpus_importer.management.commands.repair_lawbox_encoding."
            "CeleryThrottle"
        )
        throttle.start()
        self.addCleanup(throttle.stop)

    def _make_corrupt_opinion(self, **fields: str) -> Opinion:
        html = f"<p>the MHL {self.MARKER} and discretion</p>"
        return OpinionWithParentsFactory(
            html_lawbox=html, plain_text="", **fields
        )

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
        self.assertEqual(
            mock_annotate.apply_async.call_args.kwargs["queue"], "batch1"
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
        call_command(
            "repair_lawbox_encoding", doc_id=[opinion.pk], dry_run=True
        )
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
    def test_annotation_is_batched(
        self, mock_annotate, mock_update_es
    ) -> None:
        # A single task loops over its opinions inside one Celery worker, so
        # the command must split the repaired pks into small tasks.
        opinions = [self._make_corrupt_opinion() for _ in range(5)]
        call_command(
            "repair_lawbox_encoding",
            doc_id=[opinion.pk for opinion in opinions],
            opinions_per_task=2,
        )
        # 5 opinions at 2 per task -> 3 tasks.
        self.assertEqual(mock_annotate.apply_async.call_count, 3)
        sent = [
            call.kwargs["args"][0]
            for call in mock_annotate.apply_async.call_args_list
        ]
        self.assertEqual(
            sent,
            [
                [opinions[0].pk, opinions[1].pk],
                [opinions[2].pk, opinions[3].pk],
                [opinions[4].pk],
            ],
        )

    @patch("cl.lib.es_signal_processor.update_es_documents")
    @patch(
        "cl.corpus_importer.management.commands.repair_lawbox_encoding."
        "find_citations_and_parentheticals_for_opinion_by_pks"
    )
    def test_does_not_annotate_opinions_preferring_another_source(
        self, mock_annotate, mock_update_es
    ) -> None:
        # html_lawbox only outranks scraped content. When another corpus also
        # supplied this cluster, its field is what html_with_citations was
        # built from, so re-annotating would not change a thing. xml_scan is
        # included because it was added to the priority list after the
        # original review, and a gate built against a stale checkout missed it.
        for field, value in (
            ("xml_harvard", "<xml/>"),
            ("xml_scan", "<xml/>"),
            ("html_anon_2020", "<p>anon</p>"),
            ("html_columbia", "<p>columbia text \u0097 here</p>"),
        ):
            with self.subTest(field=field):
                opinion = self._make_corrupt_opinion(**{field: value})
                call_command(
                    "repair_lawbox_encoding", doc_id=[opinion.pk]
                )
                opinion.refresh_from_db()
                # The database row was still repaired ...
                self.assertIn(self.REPAIRED, opinion.html_lawbox)
                self.assertNotIn(self.MARKER, opinion.html_lawbox)
                # ... but its html_with_citations never came from html_lawbox.
                mock_annotate.apply_async.assert_not_called()

    @patch("cl.lib.es_signal_processor.update_es_documents")
    @patch(
        "cl.corpus_importer.management.commands.repair_lawbox_encoding."
        "find_citations_and_parentheticals_for_opinion_by_pks"
    )
    def test_repairs_marker_next_to_unrecoverable_one(
        self, mock_annotate, mock_update_es
    ) -> None:
        # U+FFFD flags the row but its original byte is gone for good, so the
        # command must not claim a repair it cannot make. The recoverable
        # marker beside it is still repaired, though.
        html = f"<p>an {REPLACEMENT_CHAR} square and {self.MARKER}</p>"
        opinion = OpinionWithParentsFactory(
            html_lawbox=html, plain_text=""
        )
        call_command("repair_lawbox_encoding", doc_id=[opinion.pk])
        opinion.refresh_from_db()
        # The recoverable marker next to it still gets fixed ...
        self.assertNotIn(self.MARKER, opinion.html_lawbox)
        self.assertIn(self.REPAIRED, opinion.html_lawbox)
        # ... and the row counts as repaired, so it is re-annotated.
        mock_annotate.apply_async.assert_called_once()

    @patch("cl.lib.es_signal_processor.update_es_documents")
    @patch(
        "cl.corpus_importer.management.commands.repair_lawbox_encoding."
        "find_citations_and_parentheticals_for_opinion_by_pks"
    )
    def test_only_unrecoverable_markers_are_not_annotated(
        self, mock_annotate, mock_update_es
    ) -> None:
        html = f"<p>an {REPLACEMENT_CHAR} square</p>"
        opinion = OpinionWithParentsFactory(
            html_lawbox=html, plain_text=""
        )
        call_command("repair_lawbox_encoding", doc_id=[opinion.pk])
        opinion.refresh_from_db()
        self.assertEqual(opinion.html_lawbox, html)
        mock_annotate.apply_async.assert_not_called()

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


class LawboxCitationSourceTest(TestCase):
    """Unit tests for the source-priority rule that gates re-annotation."""

    def _make_opinion(self, **fields: str) -> Opinion:
        return OpinionWithParentsFactory(plain_text="", **fields)

    def test_lawbox_is_the_source_when_nothing_outranks_it(self) -> None:
        opinion = self._make_opinion(html_lawbox="<p>lawbox</p>")
        self.assertTrue(lawbox_is_citation_source(opinion))

    def test_sources_that_outrank_lawbox_win(self) -> None:
        for field, value in (
            ("xml_harvard", "<xml/>"),
            ("xml_scan", "<xml/>"),
            ("html_anon_2020", "<p>anon</p>"),
            ("html_columbia", "<p>columbia</p>"),
        ):
            with self.subTest(field=field):
                opinion = self._make_opinion(
                    html_lawbox="<p>lawbox</p>", **{field: value}
                )
                self.assertFalse(lawbox_is_citation_source(opinion))

    def test_html_ranks_below_lawbox(self) -> None:
        # Scraped content is the one thing html_lawbox beats.
        opinion = self._make_opinion(
            html_lawbox="<p>lawbox</p>", html="<p>scraped</p>"
        )
        self.assertTrue(lawbox_is_citation_source(opinion))

    def test_empty_lawbox_is_never_a_source(self) -> None:
        opinion = self._make_opinion(html_lawbox="")
        self.assertFalse(lawbox_is_citation_source(opinion))

    def test_db_filter_matches_the_python_helper(self) -> None:
        cases = [
            {"html_lawbox": "<p>lawbox</p>"},
            {"html_lawbox": "<p>lawbox</p>", "html_columbia": "<p>c</p>"},
            {"html_lawbox": "<p>lawbox</p>", "xml_harvard": "<x/>"},
            {"html_lawbox": "<p>lawbox</p>", "xml_scan": "<x/>"},
            {"html_lawbox": "<p>lawbox</p>", "html_anon_2020": "<p>a</p>"},
            {"html_lawbox": "<p>lawbox</p>", "html": "<p>h</p>"},
            {"html_lawbox": ""},
            {
                "html_lawbox": "<p>lawbox</p>",
                "html_columbia": "",
                "xml_harvard": "",
            },
        ]
        pks = [self._make_opinion(**case).pk for case in cases]
        expected = {
            pk: lawbox_is_citation_source(Opinion.objects.get(pk=pk))
            for pk in pks
        }
        filtered = set(
            Opinion.objects.filter(pk__in=pks)
            .filter(lawbox_is_citation_source_filter())
            .values_list("pk", flat=True)
        )
        for pk in pks:
            with self.subTest(pk=pk):
                self.assertEqual(pk in filtered, expected[pk])


class ClusterSourcesLawboxSourceTest(TestCase):
    """Unit tests for the cluster-source derivation of the same rule."""

    def test_only_three_known_sources_are_lawbox_preferred(self) -> None:
        self.assertEqual(
            ClusterSources.lawbox_citation_sources(),
            frozenset({"L", "LC", "LR"}),
        )

    def test_lawbox_sources_with_a_higher_priority_corpus_are_excluded(
        self,
    ) -> None:
        for source in (
            "ZL",
            "ZLC",
            "ZLU",
            "ZLCU",
            "LU",
            "LCU",
            "LRU",
            "LCRU",
        ):
            with self.subTest(source=source):
                self.assertFalse(ClusterSources.lawbox_is_best_source(source))

    def test_non_lawbox_sources_are_excluded(self) -> None:
        for code, _ in ClusterSources.NAMES:
            if ClusterSources.LAWBOX in frozenset(code):
                continue
            with self.subTest(source=code):
                self.assertFalse(ClusterSources.lawbox_is_best_source(code))

    def test_dynamic_combinations(self) -> None:
        # Combinations that are not in NAMES are derived the same way. The
        # scanning project ("S") populates xml_scan, which outranks Lawbox.
        self.assertTrue(ClusterSources.lawbox_is_best_source("LG"))
        self.assertFalse(ClusterSources.lawbox_is_best_source("LS"))
        self.assertFalse(ClusterSources.lawbox_is_best_source("LQ"))
        self.assertFalse(ClusterSources.lawbox_is_best_source("LZ"))

    def test_agrees_with_the_per_opinion_gate_for_lawbox_clusters(
        self,
    ) -> None:
        # For a cluster with no Lawbox component at all, html_lawbox can still
        # be the best field on the Opinion; that is a data inconsistency, not a
        # rule, so only Lawbox-bearing clusters are expected to agree.
        for code, _ in ClusterSources.NAMES:
            if ClusterSources.LAWBOX not in frozenset(code):
                continue
            with self.subTest(source=code):
                opinion = OpinionWithParentsFactory(
                    plain_text="",
                    html_lawbox="<p>lawbox</p>",
                    xml_harvard="<x/>" if "U" in code else "",
                    xml_scan="<x/>" if "S" in code else "",
                    html_columbia="<p>c</p>" if "Z" in code else "",
                    html_anon_2020="<p>a</p>" if "Q" in code else "",
                    cluster__source=code,
                )
                self.assertEqual(
                    lawbox_is_citation_source(opinion),
                    ClusterSources.lawbox_is_best_source(code),
                )
