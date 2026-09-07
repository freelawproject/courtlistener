"""Tests for the frontend_checks linter.

Run with pytest from the repo root (no Django or database needed):

    pytest .github/scripts
"""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

import frontend_checks

# The script identifies input.css by exact path; v2 templates only need a v2_ directory.
CSS_FILE = "cl/assets/tailwind/input.css"
V2_TEMPLATE_FILE = "cl/foo/templates/v2_help/index.html"
LEGACY_TEMPLATE_FILE = "cl/foo/templates/help/index.html"
V2_TEMPLATE_BODY = '{% extends "new_base.html" %}'


def _run_checks_on(
    files: dict[str, str], changed: dict[str, str] | None = None
) -> list[tuple[str, int, str]]:
    """Lint a temp repo containing ``files`` (``{repo-relative path: content}``).

    ``changed`` is the ``{path: git status}`` diff to lint, simulating
    ``git diff --name-status``; it defaults to every file as modified. A path
    in ``changed`` that is missing from ``files`` stands for a deleted file.
    Returns ``(file, line, check)`` per finding, in report order.
    """
    changed = changed or dict.fromkeys(files, "M")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel_path, content in files.items():
            path = root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                textwrap.dedent(content).lstrip("\n"), encoding="utf-8"
            )
        findings = frontend_checks.run_checks(list(changed), root, changed)
    return [(f.file, f.line, f.check) for f in findings]


class SkipFileDirectiveTest(unittest.TestCase):
    """``frontend-checks-skip`` accepts Django and CSS comment syntax."""

    def test_parse_skip_checks(self) -> None:
        """Both comment syntaxes are parsed and capped to SKIPPABLE_CHECKS."""
        cases = {
            "{# frontend-checks-skip: check_include_in_v2, check_jquery #}": {
                "check_include_in_v2"
            },
            "/* frontend-checks-skip: check_raw_css */": {"check_raw_css"},
        }
        for directive, expected in cases.items():
            with self.subTest(directive):
                self.assertEqual(
                    frontend_checks._parse_skip_checks([directive]), expected
                )

    def test_directive_silences_whole_css_file(self) -> None:
        """A file-level directive in input.css drops every raw CSS finding."""
        findings = _run_checks_on(
            {
                CSS_FILE: """
                    /* frontend-checks-skip: check_raw_css */
                    .foo {
                      color: red;
                      margin: 0;
                    }
                    """
            }
        )
        self.assertEqual(findings, [])

    def test_directive_only_silences_the_named_check(self) -> None:
        """Other checks on the same file keep reporting."""
        findings = _run_checks_on(
            {
                V2_TEMPLATE_FILE: """
                    {% extends "new_base.html" %}
                    {# frontend-checks-skip: check_include_in_v2 #}
                    {% include "x.html" %}
                    <div x-data="dropdown"></div>
                    """
            }
        )
        self.assertEqual(
            findings,
            [(V2_TEMPLATE_FILE, 4, "check_xdata_without_require_script")],
        )


class SkipLineDirectiveTest(unittest.TestCase):
    """``frontend-checks-skip-line`` parsing and application."""

    def test_parse_line_skips(self) -> None:
        """Skips are keyed by line number, accept both comment syntaxes, and are capped to SKIPPABLE_CHECKS."""
        lines = [
            "color: red; /* frontend-checks-skip-line: check_raw_css */",
            "color: red;",
            # check_jquery is not currently skippable and must be dropped
            "{% include 'x' %} {# frontend-checks-skip-line: check_include_in_v2, check_jquery #}",
        ]
        self.assertEqual(
            frontend_checks._parse_line_skips(lines),
            {1: {"check_raw_css"}, 3: {"check_include_in_v2"}},
        )

    def test_raw_css_ignores_plain_comments(self) -> None:
        """A comment that is not a directive does not hide a declaration."""
        for snippet in ("color: red; /* note */", "/* note */ color: red;"):
            with self.subTest(snippet):
                self.assertEqual(
                    [
                        line
                        for line, _ in frontend_checks.check_raw_css([snippet])
                    ],
                    [1],
                )
        for snippet in ("/* color: blue; */", "/*\n  color: red;\n*/"):
            with self.subTest(snippet):
                self.assertEqual(
                    frontend_checks.check_raw_css(snippet.splitlines()), []
                )

    def test_directive_applies_to_its_own_line_only(self) -> None:
        """A directive silences an allowlisted check on its line and nothing else."""
        findings = _run_checks_on(
            {
                CSS_FILE: """
                    .scrollbar-none {
                      scrollbar-width: none; /* frontend-checks-skip-line: check_raw_css */
                      -ms-overflow-style: none;
                    }
                    """,
                V2_TEMPLATE_FILE: """
                    {% extends "new_base.html" %}
                    {% include "x.html" %} {# frontend-checks-skip-line: check_include_in_v2 #}
                    <script>$(".x")</script> {# frontend-checks-skip-line: check_jquery #}
                    """,
            }
        )
        self.assertEqual(
            findings,
            [
                (CSS_FILE, 3, "check_raw_css"),
                (V2_TEMPLATE_FILE, 3, "check_jquery"),
            ],
        )


class LegacyTemplateDeletedTest(unittest.TestCase):
    """Deleting a legacy template makes its v2 counterpart live for everyone."""

    def test_deleted_legacy_with_v2_counterpart_warns(self) -> None:
        """A D status on a legacy template whose v2 twin is on disk is reported."""
        findings = _run_checks_on(
            {V2_TEMPLATE_FILE: V2_TEMPLATE_BODY},
            changed={LEGACY_TEMPLATE_FILE: "D"},
        )
        self.assertEqual(
            findings,
            [(LEGACY_TEMPLATE_FILE, 1, "check_legacy_template_deleted")],
        )

    def test_deleted_legacy_without_v2_counterpart_is_silent(self) -> None:
        """Nothing goes live when there is no v2 twin."""
        findings = _run_checks_on({}, changed={LEGACY_TEMPLATE_FILE: "D"})
        self.assertEqual(findings, [])

    def test_modified_legacy_is_not_a_deletion(self) -> None:
        """Only the D status triggers the check, even with a v2 twin on disk."""
        findings = _run_checks_on(
            {
                LEGACY_TEMPLATE_FILE: "<div></div>",
                V2_TEMPLATE_FILE: V2_TEMPLATE_BODY,
            },
            changed={LEGACY_TEMPLATE_FILE: "M"},
        )
        self.assertEqual(findings, [])

    def test_deleted_v2_is_not_reported(self) -> None:
        """Deleting the v2 side leaves the legacy page as the only one; nothing goes live."""
        findings = _run_checks_on(
            {LEGACY_TEMPLATE_FILE: "behind the use_new_design waffle flag."},
            changed={V2_TEMPLATE_FILE: "D"},
        )
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
