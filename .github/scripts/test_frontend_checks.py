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


def _run_checks_on(files: dict[str, str]) -> list[tuple[str, int, str]]:
    """Write ``{repo-relative path: content}`` into a temp repo and lint them all as modified.

    Simulates the output of ``git diff --name-status`` as required by frontend_checks.
    Returns ``(file, line, check)`` per finding, in report order.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel_path, content in files.items():
            path = root / rel_path
            path.parent.mkdir(parents=True)
            path.write_text(
                textwrap.dedent(content).lstrip("\n"), encoding="utf-8"
            )
        changed = list(files)
        findings = frontend_checks.run_checks(
            changed, root, dict.fromkeys(changed, "M")
        )
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


if __name__ == "__main__":
    unittest.main()
