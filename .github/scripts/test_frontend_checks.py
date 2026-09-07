"""Tests for the frontend_checks linter.

Run with pytest from the repo root (no Django or database needed):

    pytest .github/scripts
"""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

import frontend_checks as fc


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
            fc._parse_line_skips(lines),
            {1: {"check_raw_css"}, 3: {"check_include_in_v2"}},
        )

    def test_raw_css_ignores_plain_comments(self) -> None:
        """A comment that is not a directive does not hide a declaration."""
        for snippet in ("color: red; /* note */", "/* note */ color: red;"):
            with self.subTest(snippet):
                self.assertEqual(
                    [line for line, _ in fc.check_raw_css([snippet])], [1]
                )
        for snippet in ("/* color: blue; */", "/*\n  color: red;\n*/"):
            with self.subTest(snippet):
                self.assertEqual(fc.check_raw_css(snippet.splitlines()), [])

    def test_directive_applies_to_its_own_line_only(self) -> None:
        """A directive silences an allowlisted check on its line and nothing else."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            css = "cl/assets/tailwind/input.css"
            v2 = "cl/foo/templates/v2_help/index.html"
            files = {
                css: """
                    .scrollbar-none {
                      scrollbar-width: none; /* frontend-checks-skip-line: check_raw_css */
                      -ms-overflow-style: none;
                    }
                    """,
                v2: """
                    {% extends "new_base.html" %}
                    {% include "x.html" %} {# frontend-checks-skip-line: check_include_in_v2 #}
                    <script>$(".x")</script> {# frontend-checks-skip-line: check_jquery #}
                    """,
            }
            for rel_path, content in files.items():
                path = root / rel_path
                path.parent.mkdir(parents=True)
                path.write_text(
                    textwrap.dedent(content).lstrip("\n"), encoding="utf-8"
                )
            findings = fc.run_checks([css, v2], root, {css: "M", v2: "M"})
        self.assertEqual(
            [(f.file, f.line, f.check) for f in findings],
            [(css, 3, "check_raw_css"), (v2, 3, "check_jquery")],
        )


if __name__ == "__main__":
    unittest.main()
