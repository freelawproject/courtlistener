#!/usr/bin/env python3
"""Automated frontend checks for CourtListener PR reviews.

Runs checks on changed template and CSS files to enforce frontend
conventions. Called by the frontend-lint GitHub Actions workflow.

Input file must be in git --name-status format (STATUS\\tPATH per line).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------
FAIL = "error"
WARN = "warning"

# ---------------------------------------------------------------------------
# File classification helpers
# ---------------------------------------------------------------------------


def is_v2_template(path: str) -> bool:
    return "templates/v2_" in path and path.endswith(".html")


def is_cotton_component(path: str) -> bool:
    return "templates/cotton/" in path and path.endswith(".html")


def is_legacy_template(path: str) -> bool:
    if not path.endswith(".html"):
        return False
    if "templates/" not in path:
        return False
    if is_v2_template(path) or is_cotton_component(path):
        return False
    if path.endswith("new_base.html"):
        return False
    return True


def is_input_css(path: str) -> bool:
    return path == "cl/assets/tailwind/input.css"


# ---------------------------------------------------------------------------
# Multiline tag helper
# ---------------------------------------------------------------------------


def _get_full_tag(lines: list[str], line_idx: int) -> str:
    """Reconstruct the full opening HTML tag surrounding a given line.

    Given a 0-based line index where a match was found, searches backward
    for the ``<`` that opens the tag and forward for the closing ``>``.
    Returns the concatenated content of all lines that make up the tag.
    """
    # Search backward for the opening <
    start = line_idx
    for j in range(line_idx, -1, -1):
        if "<" in lines[j]:
            start = j
            break

    # Search forward for the closing >
    end = line_idx
    for j in range(line_idx, len(lines)):
        if ">" in lines[j]:
            end = j
            break

    return " ".join(lines[start : end + 1])


# ---------------------------------------------------------------------------
# Individual check functions
#
# Each returns a list of (line_number, message) tuples.
# line_number is 1-indexed.
# ---------------------------------------------------------------------------


def check_tabnabbing(lines: list[str]) -> list[tuple[int, str]]:
    """target="_blank" must have rel with noopener or noreferrer."""
    results = []
    target_blank_re = re.compile(r'target\s*=\s*["\']_blank["\']')
    rel_safe_re = re.compile(
        r'rel\s*=\s*["\'][^"\']*(?:noopener|noreferrer)[^"\']*["\']'
    )

    for i, line in enumerate(lines, 1):
        if target_blank_re.search(line):
            full_tag = _get_full_tag(lines, i - 1)
            if not rel_safe_re.search(full_tag):
                results.append(
                    (
                        i,
                        'target="_blank" without rel containing "noopener" or '
                        '"noreferrer" — tabnabbing risk',
                    )
                )
    return results


def check_tabindex(lines: list[str]) -> list[tuple[int, str]]:
    """No tabindex > 0."""
    results = []
    pattern = re.compile(r'tabindex\s*=\s*["\']([1-9]\d*)["\']')
    for i, line in enumerate(lines, 1):
        m = pattern.search(line)
        if m:
            results.append(
                (
                    i,
                    f'tabindex="{m.group(1)}" — never use tabindex > 0; '
                    f"use 0 (focusable) or -1 (programmatic only)",
                )
            )
    return results


def check_jquery(lines: list[str]) -> list[tuple[int, str]]:
    """No jQuery in v2_ templates."""
    results = []
    pattern = re.compile(r"(?:\$\(|jQuery\()")
    for i, line in enumerate(lines, 1):
        if pattern.search(line):
            results.append(
                (i, "jQuery detected — use Alpine.js in new templates")
            )
    return results


def check_alpine_shortcuts(
    lines: list[str], *, allow_apply: bool = False
) -> list[tuple[int, str]]:
    """No @ Alpine shortcuts (must use x-on: prefix).

    @apply is only valid in CSS files. In templates, flag it too unless
    allow_apply is True (for input.css).
    """
    results = []
    # Match @event but not @apply (conditionally), and not email addresses
    events = (
        "click",
        "change",
        "submit",
        "input",
        "keyup",
        "keydown",
        "focus",
        "blur",
        "mouseover",
        "mouseenter",
        "mouseleave",
        "scroll",
        "resize",
        "load",
        "reset",
    )
    if not allow_apply:
        events = (*events, "apply")

    pattern = re.compile(r"(?<!\w)@(" + "|".join(events) + r")\b")
    for i, line in enumerate(lines, 1):
        m = pattern.search(line)
        if m:
            shortcut = m.group(0)
            if shortcut == "@apply":
                msg = "@apply detected in template — only valid in CSS files"
            else:
                msg = (
                    f'"{shortcut}" — use "x-on:{m.group(1)}" instead '
                    f"(CSP-safe Alpine prefix)"
                )
            results.append((i, msg))
    return results


def check_font_awesome(lines: list[str]) -> list[tuple[int, str]]:
    """No Font Awesome classes in v2_ templates."""
    results = []
    # Matches class attributes containing the "fa" base class used by FA
    pattern = re.compile(r'class\s*=\s*["\'][^"\']*\bfa\b')
    for i, line in enumerate(lines, 1):
        if pattern.search(line):
            results.append(
                (
                    i,
                    "Font Awesome class detected — use SVG icons in new templates",
                )
            )
    return results


def check_inline_xdata(lines: list[str]) -> list[tuple[int, str]]:
    """x-data should not contain inline logic (curly braces)."""
    results = []
    pattern = re.compile(r"""x-data\s*=\s*['\"]\{""")
    for i, line in enumerate(lines, 1):
        if pattern.search(line):
            results.append(
                (
                    i,
                    "x-data contains inline logic — move to external Alpine "
                    "script via {% require_script %}",
                )
            )
    return results


def check_extends_new_base(lines: list[str]) -> list[tuple[int, str]]:
    """v2_ templates must extend new_base.html or another v2_ template."""
    results = []
    extends_re = re.compile(r'{%\s*extends\s+["\']([^"\']+)["\']\s*%}')

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip empty lines, comments, and load tags
        if (
            not stripped
            or stripped.startswith("{#")
            or stripped.startswith("{%")
            and "load" in stripped
        ):
            continue

        m = extends_re.search(stripped)
        if m:
            parent = m.group(1)
            if parent != "new_base.html" and "v2_" not in parent:
                results.append(
                    (
                        i,
                        f'extends "{parent}" — v2_ templates must extend '
                        f'"new_base.html" or another v2_ template',
                    )
                )
        else:
            results.append(
                (
                    i,
                    "v2_ template does not have {% extends %} as first "
                    "directive — must extend new_base.html or a v2_ template",
                )
            )
        # Only check the first meaningful line
        break
    return results


def check_sync_notice(lines: list[str]) -> list[tuple[int, str]]:
    """Legacy template must have sync notice if v2_ counterpart exists."""
    content = "\n".join(lines)
    if "use_new_design waffle flag" not in content:
        return [
            (
                1,
                "Legacy template missing sync notice — a v2_ counterpart "
                "exists. Add the standard ATTENTION comment block.",
            )
        ]
    return []


def check_bare_links(lines: list[str]) -> list[tuple[int, str]]:
    """Flag <a> tags without class attribute (heuristic)."""
    results = []
    # Match <a that doesn't have class= before the closing >
    # Simple heuristic: look for <a followed by attributes but no class=
    a_tag_re = re.compile(r"<a\s(?=[^>]*>)")
    class_re = re.compile(r"\bclass\s*=")
    for i, line in enumerate(lines, 1):
        for m in a_tag_re.finditer(line):
            full_tag = _get_full_tag(lines, i - 1)
            if not class_re.search(full_tag):
                results.append(
                    (
                        i,
                        "Unstyled <a> tag — links should have appropriate "
                        "styling classes (or styling may come from parent/child)",
                    )
                )
    return results


def check_placeholder_text(lines: list[str]) -> list[tuple[int, str]]:
    """Flag TODO, TBD, FIXME, Lorem ipsum outside of comments."""
    results = []
    pattern = re.compile(
        r"\bTODO\b|\bTBD\b|\bFIXME\b|Lorem ipsum", re.IGNORECASE
    )
    # Only strips single-line inline comments; multiline <!-- --> blocks
    # are handled by the in_html_comment state tracker below.
    inline_comment_re = re.compile(r"(<!--.*?-->|\{#.*?#\})")

    in_html_comment = False
    in_django_comment = False
    for i, line in enumerate(lines, 1):
        # Track multiline HTML comments (<!-- ... -->)
        if "<!--" in line and "-->" not in line:
            in_html_comment = True
            continue
        if in_html_comment:
            if "-->" in line:
                in_html_comment = False
            continue

        # Track Django block comments ({% comment %} ... {% endcomment %})
        if "{% comment %}" in line:
            in_django_comment = True
            continue
        if in_django_comment:
            if "{% endcomment %}" in line:
                in_django_comment = False
            continue

        # Strip single-line comments before checking
        cleaned = inline_comment_re.sub("", line)
        m = pattern.search(cleaned)
        if m:
            results.append(
                (
                    i,
                    f'Placeholder text "{m.group()}" found — remove before merging',
                )
            )
    return results


def check_hardcoded_ids(lines: list[str]) -> list[tuple[int, str]]:
    """Flag hardcoded id= in cotton components."""
    results = []
    # Match id="something" but not x-bind:id, :id, or x-id
    # Also skip id="{{ variable }}" or id="{% ... %}"
    id_re = re.compile(r'(?<![x-])\bid\s*=\s*["\']([^"\']*)["\']')
    dynamic_re = re.compile(r"[{%{]")
    xbind_re = re.compile(r"(?:x-bind:id|:id|x-id)\s*=")

    for i, line in enumerate(lines, 1):
        # Skip lines with x-bind:id or :id
        if xbind_re.search(line):
            continue
        for m in id_re.finditer(line):
            value = m.group(1)
            if not dynamic_re.search(value):
                # Check the full tag for x-bind:id on a different line
                full_tag = _get_full_tag(lines, i - 1)
                if xbind_re.search(full_tag):
                    continue
                results.append(
                    (
                        i,
                        f'Hardcoded id="{value}" — consider using dynamic IDs '
                        f"(x-bind:id or template variables) for reusable components",
                    )
                )
    return results


def check_include_in_v2(lines: list[str]) -> list[tuple[int, str]]:
    """Flag {% include %} in v2_ templates."""
    results = []
    pattern = re.compile(r"{%\s*include\s")
    for i, line in enumerate(lines, 1):
        if pattern.search(line):
            results.append(
                (
                    i,
                    "{% include %} in v2_ template — prefer Cotton components (<c-...>)",
                )
            )
    return results


def check_new_stack_leakage(lines: list[str]) -> list[tuple[int, str]]:
    """Flag Alpine/Cotton usage in legacy templates."""
    results = []
    patterns = [
        (re.compile(r"\bx-data\b"), "x-data (Alpine)"),
        (re.compile(r"\bx-on:"), "x-on: (Alpine)"),
        (re.compile(r"\bx-bind:"), "x-bind: (Alpine)"),
        (re.compile(r"<c-"), "<c-... (Cotton component)"),
    ]
    for i, line in enumerate(lines, 1):
        for pat, name in patterns:
            if pat.search(line):
                results.append(
                    (
                        i,
                        f"New-stack pattern {name} in legacy template — "
                        f"this may be intentional, but verify it's not mixing stacks",
                    )
                )
                break  # One warning per line is enough
    return results


def check_xdata_without_require_script(
    lines: list[str],
) -> list[tuple[int, str]]:
    """x-data="name" without {% require_script %} in same file."""
    content = "\n".join(lines)
    xdata_re = re.compile(r'x-data\s*=\s*["\'](\w+)["\']')
    has_require_script = "require_script" in content

    if not has_require_script:
        results = []
        for i, line in enumerate(lines, 1):
            m = xdata_re.search(line)
            if m:
                results.append(
                    (
                        i,
                        f'x-data="{m.group(1)}" but no {{% require_script %}} '
                        f"found — Alpine component script may not be loaded "
                        f"(could be loaded by a parent template)",
                    )
                )
        return results
    return []


def check_raw_css(lines: list[str]) -> list[tuple[int, str]]:
    """Flag raw CSS in input.css that doesn't use @apply.

    Allows: @apply, @tailwind, @import, @layer, CSS custom properties,
    mask, content, display, and properties inside ::before/::after.
    """
    results = []
    # Lines that are clearly OK
    ok_patterns = re.compile(
        r"^\s*(?:"
        r"@apply\b|@tailwind\b|@import\b|@layer\b|"  # Tailwind directives
        r"/\*|/\*\*|\*/|\*\s|"  # Comments
        r"[{}]|"  # Braces only
        r"\.|#|&|:|"  # Selectors
        r"--[\w-]+\s*:|"  # CSS custom properties
        r"mask\b|content\b|display\b"  # Allowlisted properties
        r")"
    )
    # Looks like a CSS property declaration
    prop_re = re.compile(r"^\s*[\w-]+\s*:")

    in_comment = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Track block comments
        if "/*" in stripped:
            in_comment = True
        if "*/" in stripped:
            in_comment = False
            continue
        if in_comment:
            continue

        # Skip empty lines and lines that are just closing braces
        if not stripped or stripped in ("{", "}", ");"):
            continue

        # Skip lines that match OK patterns
        if ok_patterns.match(stripped):
            continue

        # Flag lines that look like raw CSS property declarations
        if prop_re.match(stripped):
            results.append(
                (
                    i,
                    "Raw CSS property — prefer @apply with Tailwind classes "
                    "when possible",
                )
            )
    return results


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    file: str
    line: int
    check: str
    severity: str
    message: str


# Check registries: (check_function, severity) per file category.
# The check name in output is derived from fn.__name__.
HTML_CHECKS = [
    (check_tabnabbing, FAIL),
    (check_tabindex, FAIL),
    (check_placeholder_text, WARN),
]

V2_CHECKS = [
    (check_jquery, FAIL),
    (check_alpine_shortcuts, FAIL),
    (check_font_awesome, FAIL),
    (check_inline_xdata, FAIL),
    (check_extends_new_base, FAIL),
    (check_bare_links, FAIL),
    (check_include_in_v2, WARN),
    (check_xdata_without_require_script, WARN),
]

COTTON_CHECKS = [
    (check_alpine_shortcuts, FAIL),
    (check_inline_xdata, FAIL),
    (check_bare_links, FAIL),
    (check_hardcoded_ids, WARN),
]

LEGACY_CHECKS = [
    (check_new_stack_leakage, WARN),
]

CSS_CHECKS = [
    (check_raw_css, WARN),
]


def _apply_checks(
    checks: list[tuple],
    lines: list[str],
    filepath: str,
    findings: list[Finding],
) -> None:
    """Run a list of (check_fn, severity) pairs and collect findings."""
    for fn, severity in checks:
        for line_no, msg in fn(lines):
            findings.append(
                Finding(filepath, line_no, fn.__name__, severity, msg)
            )


def run_checks(
    changed_files: list[str],
    repo_root: Path,
    file_statuses: dict[str, str],
) -> list[Finding]:
    """Run all applicable checks on the given files."""
    findings: list[Finding] = []

    # Collect v2_ templates changed in this PR (for sync notice check)
    changed_v2_templates = {f for f in changed_files if is_v2_template(f)}

    # Check if v2_components.html is modified (for component library check)
    components_library_modified = any(
        f.endswith("v2_components.html") for f in changed_files
    )

    for filepath in changed_files:
        abs_path = repo_root / filepath
        if not abs_path.is_file():
            continue

        try:
            lines = abs_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        if filepath.endswith(".html"):
            _apply_checks(HTML_CHECKS, lines, filepath, findings)

        if is_v2_template(filepath):
            _apply_checks(V2_CHECKS, lines, filepath, findings)

        if is_cotton_component(filepath):
            _apply_checks(COTTON_CHECKS, lines, filepath, findings)

            status = file_statuses.get(filepath, "")
            if (
                status == "A" or status.startswith("C")
            ) and not components_library_modified:
                findings.append(
                    Finding(
                        filepath,
                        1,
                        "check_new_component",
                        WARN,
                        "New Cotton component added but v2_components.html "
                        "not modified — update Component Library",
                    )
                )

        if is_legacy_template(filepath):
            _apply_checks(LEGACY_CHECKS, lines, filepath, findings)

        if is_input_css(filepath):
            _apply_checks(CSS_CHECKS, lines, filepath, findings)

    # Check sync notices: for each v2_ template in the PR, make sure
    # the legacy counterpart (if it exists on disk) has the sync notice.
    # This runs outside the per-file loop because the legacy file may
    # not be in the PR's changed files at all.
    for v2_path in changed_v2_templates:
        legacy_path = _swap_template_prefix(v2_path, add_v2=False)
        if legacy_path is None:
            continue
        abs_legacy = repo_root / legacy_path
        if not abs_legacy.is_file():
            continue
        try:
            lines = abs_legacy.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line_no, msg in check_sync_notice(lines):
            findings.append(
                Finding(
                    legacy_path,
                    line_no,
                    "check_sync_notice",
                    FAIL,
                    msg,
                )
            )

    # Reverse sync check: if a legacy template with sync notice is
    # modified, the v2_ counterpart should also be modified.
    changed_legacy_templates = {
        f for f in changed_files if is_legacy_template(f)
    }
    for legacy_path in changed_legacy_templates:
        v2_path = _swap_template_prefix(legacy_path, add_v2=True)
        if v2_path is None or v2_path in changed_v2_templates:
            continue
        abs_v2 = repo_root / v2_path
        if not abs_v2.is_file():
            continue
        abs_legacy = repo_root / legacy_path
        try:
            content = abs_legacy.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "use_new_design waffle flag" not in content:
            continue
        findings.append(
            Finding(
                legacy_path,
                1,
                "check_v2_counterpart_updated",
                WARN,
                f"Legacy template with sync notice was modified but "
                f"v2_ counterpart ({v2_path}) was not — ensure both "
                f"templates stay in sync",
            )
        )

    return findings


def _swap_template_prefix(path: str, *, add_v2: bool) -> str | None:
    """Swap between legacy and v2_ template paths.

    Examples:
        add_v2=True:  templates/help/foo.html → templates/v2_help/foo.html
        add_v2=False: templates/v2_help/foo.html → templates/help/foo.html
    """
    p = Path(path)
    parts = list(p.parts)
    try:
        idx = parts.index("templates")
    except ValueError:
        return None
    if idx + 1 >= len(parts):
        return None
    subdir = parts[idx + 1]
    if add_v2:
        parts[idx + 1] = f"v2_{subdir}"
    else:
        if not subdir.startswith("v2_"):
            return None
        parts[idx + 1] = subdir.removeprefix("v2_")
    return str(Path(*parts))


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_github(findings: list[Finding]) -> str:
    """Format findings as GitHub Actions annotations."""
    output_lines = []
    for f in findings:
        level = f.severity  # "error" or "warning"
        output_lines.append(
            f"::{level} file={f.file},line={f.line}::"
            f"{f.file}:{f.line} [{f.check}] {f.message}"
        )
    return "\n".join(output_lines)


def format_text(findings: list[Finding]) -> str:
    """Format findings as human-readable text."""
    output_lines = []
    for f in findings:
        icon = "ERROR" if f.severity == FAIL else "WARN "
        output_lines.append(
            f"  {icon}  {f.file}:{f.line}  [{f.check}] {f.message}"
        )
    return "\n".join(output_lines)


def format_summary_markdown(findings: list[Finding]) -> str:
    """Format findings as a markdown summary for PR comments.

    Groups findings by severity (errors first, then warnings) and
    renders them in a table. Includes a hidden marker comment so the
    workflow can identify and minimize previous bot comments.
    """
    lines = ["<!-- frontend-checks-summary -->"]
    lines.append("## Frontend Checks Summary")
    lines.append("")

    errors = [f for f in findings if f.severity == FAIL]
    warnings = [f for f in findings if f.severity == WARN]

    counts = []
    if errors:
        counts.append(f"{len(errors)} error(s)")
    if warnings:
        counts.append(f"{len(warnings)} warning(s)")
    lines.append(f"Found {', '.join(counts)}.")
    lines.append("")

    for label, group in [("Errors", errors), ("Warnings", warnings)]:
        if not group:
            continue
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| File | Line | Check | Message |")
        lines.append("|------|------|-------|---------|")
        for f in group:
            # Escape pipe characters in message
            msg = f.message.replace("|", "\\|")
            lines.append(f"| `{f.file}` | {f.line} | {f.check} | {msg} |")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Frontend checks for CourtListener templates"
    )
    parser.add_argument(
        "--changed-files",
        required=True,
        help="File containing changed files in --name-status format (STATUS\\tPATH per line)",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root directory (default: current directory)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "github"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--summary-file",
        default=None,
        help="Write markdown summary to this file (only if findings exist)",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()

    raw = Path(args.changed_files).read_text()

    changed_files = []
    file_statuses: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            parser.error(
                f"Expected --name-status format (STATUS\\tPATH), got: {line!r}"
            )
        status = parts[0]
        # Last field is always the destination path — handles renames
        # and copies (e.g. "R100\told\tnew") as well as simple entries
        path = parts[-1]
        file_statuses[path] = status
        changed_files.append(path)

    # Filter to relevant files
    relevant = [
        f for f in changed_files if f.endswith(".html") or is_input_css(f)
    ]

    if not relevant:
        return 0

    findings = run_checks(relevant, repo_root, file_statuses)

    if not findings:
        print("All frontend checks passed.")
        return 0

    # Sort by severity (errors first), then file, then line
    findings.sort(key=lambda f: (f.severity != FAIL, f.file, f.line))

    # Write markdown summary file if requested
    if args.summary_file:
        Path(args.summary_file).write_text(
            format_summary_markdown(findings), encoding="utf-8"
        )

    if args.format == "github":
        print(format_github(findings))
    else:
        errors = [f for f in findings if f.severity == FAIL]
        warnings = [f for f in findings if f.severity == WARN]
        if errors:
            print(f"\n{len(errors)} error(s):")
            print(format_text(errors))
        if warnings:
            print(f"\n{len(warnings)} warning(s):")
            print(format_text(warnings))

    has_errors = any(f.severity == FAIL for f in findings)
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
