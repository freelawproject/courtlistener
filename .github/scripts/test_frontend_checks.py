"""Tests for the frontend_checks linter.

Run with pytest from the repo root (no Django or database needed):

    pytest .github/scripts
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import frontend_checks

# The script identifies input.css by exact path; v2 templates only need a v2_ directory.
CSS_FILE = "cl/assets/tailwind/input.css"
V2_TEMPLATE_FILE = "cl/foo/templates/v2_help/index.html"
LEGACY_TEMPLATE_FILE = "cl/foo/templates/help/index.html"
V2_TEMPLATE_BODY = '{% extends "new_base.html" %}'
V2_PARTIAL_FILE = "cl/foo/templates/v2_includes/help/button.html"
WIP_TEMPLATE_FILE = "cl/foo/templates/wip_help/index.html"
WIP_PARTIAL_FILE = "cl/foo/templates/wip_includes/help/button.html"


def _findings_on(
    files: dict[str, str],
    changed: dict[str, str] | None = None,
    linted: list[str] | None = None,
) -> list[frontend_checks.Finding]:
    """Lint a temp repo containing ``files`` (``{repo-relative path: content}``).

    ``changed`` is the ``{path: git status}`` diff, simulating
    ``git diff --name-status``; it defaults to every file as modified. A path
    in ``changed`` that is missing from ``files`` stands for a deleted file.
    ``linted`` is the subset of ``changed`` handed to the checks, the way
    ``main()`` only hands over HTML and input.css; it defaults to all of it.
    Returns the findings in report order. Use it when a test needs a
    finding's severity or message; otherwise use ``_run_checks_on``.
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
        return frontend_checks.run_checks(
            linted if linted is not None else list(changed), root, changed
        )


def _run_checks_on(
    files: dict[str, str],
    changed: dict[str, str] | None = None,
    linted: list[str] | None = None,
) -> list[tuple[str, int, str]]:
    """Like ``_findings_on``, but returns ``(file, line, check)`` per finding."""
    return [
        (f.file, f.line, f.check) for f in _findings_on(files, changed, linted)
    ]


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


class V2PartialTest(unittest.TestCase):
    """Partials under v2_includes/ are v2 templates but not pages."""

    def test_added_partial_skips_the_page_only_checks(self) -> None:
        """No base template and no page URL is expected of a partial."""
        findings = _run_checks_on(
            {V2_PARTIAL_FILE: "<c-button>Pray</c-button>"},
            changed={V2_PARTIAL_FILE: "A"},
        )
        self.assertEqual(findings, [])

    def test_added_page_still_needs_both(self) -> None:
        """The page-only checks keep firing for a v2 page."""
        findings = _run_checks_on(
            {V2_TEMPLATE_FILE: "<c-button>Pray</c-button>"},
            changed={V2_TEMPLATE_FILE: "A"},
        )
        self.assertEqual(
            findings,
            [
                (V2_TEMPLATE_FILE, 1, "check_extends_new_base"),
                (V2_TEMPLATE_FILE, 1, "check_v2_register"),
            ],
        )

    def test_partial_keeps_the_other_v2_checks(self) -> None:
        """A partial is still held to the new stack's rules."""
        findings = _run_checks_on(
            {V2_PARTIAL_FILE: "<script>$('.pray').click();</script>"}
        )
        self.assertEqual(findings, [(V2_PARTIAL_FILE, 1, "check_jquery")])


class V2RegisterTest(unittest.TestCase):
    """A new v2 template must be registered in V2PagesRegisterTest."""

    def test_new_v2_template_without_register_change_warns(self) -> None:
        """An added v2 template with no change to the register test is reported."""
        findings = _run_checks_on(
            {V2_TEMPLATE_FILE: V2_TEMPLATE_BODY},
            changed={V2_TEMPLATE_FILE: "A"},
        )
        self.assertEqual(
            findings, [(V2_TEMPLATE_FILE, 1, "check_v2_register")]
        )

    def test_register_test_is_seen_even_though_it_is_not_linted(self) -> None:
        """main() only lints HTML and CSS, so the Python file is found via statuses."""
        findings = _run_checks_on(
            {V2_TEMPLATE_FILE: V2_TEMPLATE_BODY},
            changed={
                V2_TEMPLATE_FILE: "A",
                frontend_checks.V2_REGISTER_TEST_FILE: "M",
            },
            linted=[V2_TEMPLATE_FILE],
        )
        self.assertEqual(findings, [])

    def test_modified_v2_template_needs_no_registration(self) -> None:
        """Only additions, copies and renames of v2 templates ask for registration."""
        findings = _run_checks_on(
            {V2_TEMPLATE_FILE: V2_TEMPLATE_BODY},
            changed={V2_TEMPLATE_FILE: "M"},
        )
        self.assertEqual(findings, [])

    def test_promoted_template_points_to_v2_registry(self) -> None:
        """A rename into v2_, such as a promotion from wip_, asks for V2_PAGES."""
        findings = _findings_on(
            {V2_TEMPLATE_FILE: V2_TEMPLATE_BODY},
            changed={V2_TEMPLATE_FILE: "R100"},
        )
        self.assertEqual(
            [(f.file, f.check) for f in findings],
            [(V2_TEMPLATE_FILE, "check_v2_register")],
        )
        self.assertIn("V2PagesRegisterTest.V2_PAGES", findings[0].message)


class WipTemplateTest(unittest.TestCase):
    """wip_ templates are held to the same checks as v2_ ones."""

    def test_wip_page_gets_the_v2_checks(self) -> None:
        """New-stack rules apply to an unfinished page too."""
        findings = _run_checks_on(
            {
                WIP_TEMPLATE_FILE: """
                    {% extends "new_base.html" %}
                    <script>$('.pray').click();</script>
                    """
            }
        )
        self.assertEqual(findings, [(WIP_TEMPLATE_FILE, 2, "check_jquery")])

    def test_wip_page_is_not_a_legacy_template(self) -> None:
        """Cotton in a wip_ template is not reported as new-stack leakage."""
        findings = _run_checks_on(
            {
                WIP_TEMPLATE_FILE: """
                    {% extends "new_base.html" %}
                    <c-button>Pray</c-button>
                    """
            }
        )
        self.assertEqual(findings, [])

    def test_added_wip_page_needs_base_and_registration(self) -> None:
        """The page-only checks fire for a WIP page, registered in WIP_PAGES."""
        findings = _findings_on(
            {WIP_TEMPLATE_FILE: "<c-button>Pray</c-button>"},
            changed={WIP_TEMPLATE_FILE: "A"},
        )
        self.assertEqual(
            [(f.file, f.line, f.check) for f in findings],
            [
                (WIP_TEMPLATE_FILE, 1, "check_extends_new_base"),
                (WIP_TEMPLATE_FILE, 1, "check_v2_register"),
            ],
        )
        self.assertIn("V2PagesRegisterTest.WIP_PAGES", findings[1].message)

    def test_added_wip_partial_skips_the_page_only_checks(self) -> None:
        """A partial under wip_includes/ needs no base template or registration."""
        findings = _run_checks_on(
            {WIP_PARTIAL_FILE: "<c-button>Pray</c-button>"},
            changed={WIP_PARTIAL_FILE: "A"},
        )
        self.assertEqual(findings, [])

    def test_wip_page_may_extend_wip_or_v2(self) -> None:
        """Unfinished pages may build on other unfinished or finished ones."""
        for parent in ("wip_help/base.html", "v2_help/base.html"):
            with self.subTest(parent):
                findings = _run_checks_on(
                    {WIP_TEMPLATE_FILE: f'{{% extends "{parent}" %}}'}
                )
                self.assertEqual(findings, [])


class WipDependencyTest(unittest.TestCase):
    """Finished v2_ templates must not pull in unfinished wip_ ones."""

    def test_check_wip_dependency(self) -> None:
        """Only extends/include of a template named with the wip_ prefix is reported."""
        cases = {
            '{% extends "wip_help/base.html" %}': [1],
            "{% include 'wip_includes/card.html' %}": [1],
            '{% include "help/wip_card.html" %}': [],
            '{% extends "new_base.html" %}': [],
            '{% include "v2_includes/swip_card.html" %}': [],
            '<a href="/wip_help/">Help</a>': [],
        }
        for line, expected in cases.items():
            with self.subTest(line):
                self.assertEqual(
                    [
                        n
                        for n, _ in frontend_checks.check_wip_dependency(
                            [line]
                        )
                    ],
                    expected,
                )

    def test_wip_flag_block_gates_wip_references(self) -> None:
        """A wip_ include is allowed only in the WIP flag's opted-in branch."""
        cases = {
            "gated": (
                """
                {% flag "use_wip_design" %}
                  {% include "wip_includes/card.html" %}
                {% endflag %}
                """,
                [],
            ),
            "single-quoted flag name": (
                """
                {% flag 'use_wip_design' %}{% include "wip_includes/card.html" %}{% endflag %}
                """,
                [],
            ),
            "else branch is ungated": (
                """
                {% flag "use_wip_design" %}
                  {% include "wip_includes/card.html" %}
                {% else %}
                  {% include "wip_includes/card.html" %}
                {% endflag %}
                """,
                [4],
            ),
            "after the block ends": (
                """
                {% flag "use_wip_design" %}{% endflag %}
                {% include "wip_includes/card.html" %}
                """,
                [2],
            ),
            "another flag does not gate": (
                """
                {% flag "use_new_design" %}
                  {% include "wip_includes/card.html" %}
                {% endflag %}
                """,
                [2],
            ),
            "an inner waffle switch's else stays gated": (
                """
                {% flag "use_wip_design" %}
                  {% switch "some_switch" %}{% else %}
                    {% include "wip_includes/card.html" %}
                  {% endswitch %}
                {% endflag %}
                """,
                [],
            ),
            "an inner if's else stays gated": (
                """
                {% flag "use_wip_design" %}
                  {% if user.is_staff %}
                    {% include "wip_includes/card.html" %}
                  {% else %}
                    {% include "wip_includes/card.html" %}
                  {% endif %}
                {% endflag %}
                """,
                [],
            ),
        }
        for label, (template, expected) in cases.items():
            with self.subTest(label):
                lines = textwrap.dedent(template).strip("\n").splitlines()
                self.assertEqual(
                    [
                        n
                        for n, _ in frontend_checks.check_wip_dependency(lines)
                    ],
                    expected,
                )

    def test_v2_page_extending_wip_fails(self) -> None:
        """A wip_ parent passes the base check but fails the dependency check."""
        findings = _findings_on(
            {V2_TEMPLATE_FILE: '{% extends "wip_help/base.html" %}'}
        )
        self.assertEqual(
            [(f.file, f.line, f.check, f.severity) for f in findings],
            [
                (
                    V2_TEMPLATE_FILE,
                    1,
                    "check_wip_dependency",
                    frontend_checks.FAIL,
                )
            ],
        )

    def test_shared_templates_including_wip_fail(self) -> None:
        """new_base.html and Cotton components render inside finished pages."""
        for path in (
            "cl/assets/templates/new_base.html",
            "cl/assets/templates/cotton/header.html",
        ):
            with self.subTest(path):
                findings = _run_checks_on(
                    {path: '{% include "wip_includes/header.html" %}'}
                )
                self.assertEqual(findings, [(path, 1, "check_wip_dependency")])


class WipCounterpartTest(unittest.TestCase):
    """Legacy templates and their wip_ counterparts stay in sync."""

    def test_wip_counterpart_needs_sync_notice(self) -> None:
        """A changed WIP template asks for the notice on its legacy twin."""
        findings = _run_checks_on(
            {
                LEGACY_TEMPLATE_FILE: "<div></div>",
                WIP_TEMPLATE_FILE: V2_TEMPLATE_BODY,
            },
            changed={WIP_TEMPLATE_FILE: "M"},
        )
        self.assertEqual(
            findings, [(LEGACY_TEMPLATE_FILE, 1, "check_sync_notice")]
        )

    def test_legacy_change_asks_for_every_counterpart(self) -> None:
        """Each unchanged v2_ and wip_ twin of a legacy template is reported."""
        findings = _findings_on(
            {
                LEGACY_TEMPLATE_FILE: "behind the use_new_design waffle flag.",
                V2_TEMPLATE_FILE: V2_TEMPLATE_BODY,
                WIP_TEMPLATE_FILE: V2_TEMPLATE_BODY,
            },
            changed={LEGACY_TEMPLATE_FILE: "M"},
        )
        self.assertEqual(
            [(f.file, f.check) for f in findings],
            [(LEGACY_TEMPLATE_FILE, "check_v2_counterpart_updated")] * 2,
        )
        self.assertIn(V2_TEMPLATE_FILE, findings[0].message)
        self.assertIn(WIP_TEMPLATE_FILE, findings[1].message)

    def test_deleted_legacy_with_only_wip_counterpart_fails(self) -> None:
        """The page would be a 404 for everyone not opted into the WIP flag."""
        findings = _findings_on(
            {WIP_TEMPLATE_FILE: V2_TEMPLATE_BODY},
            changed={LEGACY_TEMPLATE_FILE: "D"},
        )
        self.assertEqual(
            [(f.file, f.check, f.severity) for f in findings],
            [
                (
                    LEGACY_TEMPLATE_FILE,
                    "check_legacy_template_deleted",
                    frontend_checks.FAIL,
                )
            ],
        )

    def test_deleted_legacy_with_v2_and_wip_only_warns(self) -> None:
        """v2_ takes over for everyone else, so it's the usual release warning."""
        findings = _findings_on(
            {
                V2_TEMPLATE_FILE: V2_TEMPLATE_BODY,
                WIP_TEMPLATE_FILE: V2_TEMPLATE_BODY,
            },
            changed={LEGACY_TEMPLATE_FILE: "D"},
        )
        self.assertEqual(
            [(f.file, f.check, f.severity) for f in findings],
            [
                (
                    LEGACY_TEMPLATE_FILE,
                    "check_legacy_template_deleted",
                    frontend_checks.WARN,
                )
            ],
        )


class DanglingReferenceTest(unittest.TestCase):
    """Templates must not keep using a template the diff removes."""

    # A promotion as main() reports it: the new path renamed, the old deleted.
    PROMOTION = {V2_TEMPLATE_FILE: "R100", WIP_TEMPLATE_FILE: "D"}
    OTHER_PAGE = "cl/foo/templates/wip_other/index.html"

    def _dangling(
        self, files: dict[str, str], changed: dict[str, str]
    ) -> list[tuple[str, int, str]]:
        """Run the checks and keep only the dangling-reference findings."""
        return [
            (f.file, f.line, f.severity)
            for f in _findings_on(files, changed, linted=list(files))
            if f.check == "check_dangling_template_reference"
        ]

    def test_reference_to_promoted_template_fails(self) -> None:
        """An include of the old wip_ name breaks once the page is promoted."""
        findings = self._dangling(
            {
                V2_TEMPLATE_FILE: V2_TEMPLATE_BODY,
                self.OTHER_PAGE: """
                    {% extends "new_base.html" %}
                    {% include "wip_help/index.html" %}
                    """,
            },
            self.PROMOTION,
        )
        self.assertEqual(
            findings, [(self.OTHER_PAGE, 2, frontend_checks.FAIL)]
        )

    def test_updated_reference_passes(self) -> None:
        """Pointing the include at the new v2_ name fixes it."""
        findings = self._dangling(
            {
                V2_TEMPLATE_FILE: V2_TEMPLATE_BODY,
                self.OTHER_PAGE: """
                    {% extends "new_base.html" %}
                    {% include "v2_help/index.html" %}
                    """,
            },
            self.PROMOTION,
        )
        self.assertEqual(findings, [])

    def test_name_still_provided_elsewhere_passes(self) -> None:
        """Django still finds the name in another app's templates/ directory."""
        findings = self._dangling(
            {
                V2_TEMPLATE_FILE: V2_TEMPLATE_BODY,
                "cl/bar/templates/wip_help/index.html": V2_TEMPLATE_BODY,
                self.OTHER_PAGE: '{% include "wip_help/index.html" %}',
            },
            self.PROMOTION,
        )
        self.assertEqual(findings, [])


class RenamedLegacyTemplateTest(unittest.TestCase):
    """``main()`` treats the old side of a rename as a deleted file."""

    def _main(
        self, name_status: str, files: dict[str, str]
    ) -> tuple[int, str]:
        """Run ``main()`` on a temp repo holding ``files``; return its exit
        code and output."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel_path, content in files.items():
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            changed = root / "changed_files.txt"
            changed.write_text(name_status, encoding="utf-8")
            argv = ["frontend_checks.py", "--repo-root", tmp]
            argv += ["--changed-files", str(changed)]
            out = io.StringIO()
            with mock.patch("sys.argv", argv), contextlib.redirect_stdout(out):
                code = frontend_checks.main()
        return code, out.getvalue()

    def test_legacy_moved_to_wip_fails(self) -> None:
        """The page would be a 404 for everyone not opted into WIP pages."""
        code, out = self._main(
            f"R100\t{LEGACY_TEMPLATE_FILE}\t{WIP_TEMPLATE_FILE}\n",
            {WIP_TEMPLATE_FILE: V2_TEMPLATE_BODY},
        )
        self.assertEqual(code, 1)
        self.assertIn("[check_legacy_template_deleted]", out)

    def test_legacy_moved_to_v2_warns(self) -> None:
        """Moving it to v2_ releases the page, like deleting the legacy file."""
        code, out = self._main(
            f"R100\t{LEGACY_TEMPLATE_FILE}\t{V2_TEMPLATE_FILE}\n",
            {V2_TEMPLATE_FILE: V2_TEMPLATE_BODY},
        )
        self.assertEqual(code, 0)
        self.assertIn("[check_legacy_template_deleted]", out)


THIRD_PARTY = "cl/assets/static-global/js/third_party/"
ALPINE = "cl/assets/static-global/js/alpine/"


def _vendored_findings(diff_paths: list[str]) -> list[tuple[str, str]]:
    """``(file, check)`` per finding from the vendored-README check."""
    return [
        (f.file, f.check)
        for f in frontend_checks.check_vendored_js_readme(diff_paths)
    ]


class VendoredJsReadmeTest(unittest.TestCase):
    """Upstream JS changes must come with an update to that directory's README."""

    def test_upstream_change_without_readme_fails(self) -> None:
        """A changed upstream file with no README change is a FAIL."""
        findings = frontend_checks.check_vendored_js_readme(
            [f"{THIRD_PARTY}htmx.js"]
        )
        self.assertEqual(
            [(f.file, f.severity) for f in findings],
            [(f"{THIRD_PARTY}README.md", frontend_checks.FAIL)],
        )

    def test_upstream_change_with_readme_passes(self) -> None:
        """Touching the same directory's README is enough."""
        self.assertEqual(
            _vendored_findings(
                [f"{THIRD_PARTY}htmx.js", f"{THIRD_PARTY}README.md"]
            ),
            [],
        )

    def test_nested_upstream_file_counts(self) -> None:
        """Files in subdirectories, like flatpickr plugins, count too."""
        self.assertEqual(
            _vendored_findings(
                [f"{THIRD_PARTY}flatpickr/plugins/confirmDate.js"]
            ),
            [(f"{THIRD_PARTY}README.md", "check_vendored_js_readme")],
        )

    def test_each_directory_needs_its_own_readme(self) -> None:
        """The other directory's README doesn't cover a change."""
        self.assertEqual(
            _vendored_findings(
                [f"{ALPINE}alpinejscsp.js", f"{THIRD_PARTY}README.md"]
            ),
            [(f"{ALPINE}README.md", "check_vendored_js_readme")],
        )

    def test_alpine_plugins_are_upstream(self) -> None:
        """Official Alpine plugins live in the vendored directory."""
        self.assertEqual(
            _vendored_findings([f"{ALPINE}plugins/focus.js"]),
            [(f"{ALPINE}README.md", "check_vendored_js_readme")],
        )

    def test_our_alpine_code_is_ignored(self) -> None:
        """components/ and composables/ are our code, not upstream."""
        self.assertEqual(
            _vendored_findings(
                [
                    f"{ALPINE}components/date_selector.js",
                    f"{ALPINE}composables/focus_trap.js",
                ]
            ),
            [],
        )

    def test_readme_only_change_passes(self) -> None:
        """Editing just the README is fine."""
        self.assertEqual(_vendored_findings([f"{ALPINE}README.md"]), [])

    def test_other_js_is_out_of_scope(self) -> None:
        """Legacy scripts outside the two directories are never checked."""
        self.assertEqual(
            _vendored_findings(["cl/assets/static-global/js/base.js"]), []
        )


class VendoredJsReadmeMainTest(unittest.TestCase):
    """``main()`` reads renames from ``--name-status`` and runs the check
    even when no template or CSS file changed."""

    def _main(self, name_status: str) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "changed_files.txt"
            changed.write_text(name_status, encoding="utf-8")
            argv = ["frontend_checks.py", "--repo-root", tmp]
            argv += ["--changed-files", str(changed)]
            with (
                mock.patch("sys.argv", argv),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                return frontend_checks.main()

    def test_rename_inside_vendored_dir_fails(self) -> None:
        """An R100 rename with no README change makes the job fail."""
        old = f"{THIRD_PARTY}flatpickr/flatpickr@4.6.13.js"
        new = f"{THIRD_PARTY}flatpickr/flatpickr.js"
        self.assertEqual(self._main(f"R100\t{old}\t{new}\n"), 1)

    def test_moving_a_file_out_counts_for_the_old_directory(self) -> None:
        """The old side of a rename is checked as well as the new one."""
        old = f"{THIRD_PARTY}htmx.js"
        self.assertEqual(
            self._main(f"R100\t{old}\tcl/assets/static-global/js/htmx.js\n"),
            1,
        )

    def test_rename_with_readme_passes(self) -> None:
        """The same rename plus a README change exits cleanly."""
        old = f"{THIRD_PARTY}flatpickr/flatpickr@4.6.13.js"
        new = f"{THIRD_PARTY}flatpickr/flatpickr.js"
        name_status = f"R100\t{old}\t{new}\nM\t{THIRD_PARTY}README.md\n"
        self.assertEqual(self._main(name_status), 0)


if __name__ == "__main__":
    unittest.main()
