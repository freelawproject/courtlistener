# Frontend Guide

> For the full design rationale and migration plan, see the
> [New Frontend Architecture wiki](https://github.com/freelawproject/courtlistener/wiki/New-Frontend-Architecture).
>
> Rules here are enforced by CI (`frontend_checks.py`). If this doc and the
> script disagree, the script is the source of truth.

## Two stacks

CourtListener is migrating from Bootstrap 3 / jQuery to Tailwind / Alpine.js / Cotton. Both stacks coexist.

**Before writing any frontend code, determine which stack you're working in.** Check whether the template extends `base.html` (legacy) or `new_base.html` (new), or whether a `v2_` counterpart exists. If unclear, ask. The two stacks use different technologies and conventions — mixing them causes subtle, hard-to-debug breakage.

| | Legacy | New (redesign) |
|---|---|---|
| Base template | `base.html` | `new_base.html` |
| CSS framework | Bootstrap 3 | Tailwind CSS |
| JS framework | jQuery | Alpine.js |
| Reusable fragments | `{% include %}` | Cotton components (`<c-...>`) |
| Template prefix | `templates/<app>/` | `templates/v2_<app>/` |

**Do not mix stacks.** Legacy templates stay on Bootstrap/jQuery. New templates stay on Tailwind/Alpine/Cotton.

## Template conventions

### Naming & middleware

`IncrementalNewTemplateMiddleware` swaps templates by prepending `v2_` to the view's template name when the `use_new_design` waffle flag is active. New templates MUST be named accordingly (e.g., `v2_help/index.html`).

### Base template

New templates MUST extend `new_base.html` (or another `v2_` template). Only `new_base.html` loads Tailwind, Alpine, and Cotton.

### Legacy ↔ v2 sync

When a legacy template has a `v2_` counterpart:
- The legacy template MUST have a sync-notice comment at the top referencing the waffle flag
- Changes to either version MUST be mirrored in the other for content/behavior parity (implementation details can differ by stack)

## Cotton components

- Live in `templates/cotton/`, snake_case filenames
- Called with `<c-kebab-case />` (e.g., `templates/cotton/alert_banner.html` → `<c-alert-banner />`)
- Use `<c-vars />` to declare attributes
- Check existing components before creating new ones — component library at `cl/simple_pages/templates/v2_components.html`
- New components MUST have a corresponding entry in `v2_components.html`
- Avoid hardcoded `id` attributes in components — they create duplicate IDs when a component is reused on the same page

## Tailwind CSS

- Classes MUST be written as complete strings — never dynamically constructed (e.g., `` `text-greyscale-${val}` `` will silently break because Tailwind can't detect dynamically constructed class names at build time)
- `input.css` (`cl/assets/tailwind/input.css`): prefer `@apply` with Tailwind classes over raw CSS properties
- `@apply` MUST only appear in CSS files, never in templates

## Alpine.js

CourtListener uses the CSP-friendly Alpine build. This means:

- No `@` shorthand — use `x-on:click`, not `@click`
- No `:` shorthand — use `x-bind:class`, not `:class` (`:` is Cotton's attribute syntax; Cotton uses `::` for Alpine bind pass-through, but we avoid that and use explicit `x-bind:` instead)
- No inline `x-data` logic — use `x-data="componentName"` and define the component in an external script
- External scripts loaded via `{% require_script %}` tag
- Only `x-` directives, no inline JS expressions

When adding `x-data` to a template, there MUST be a corresponding `{% require_script %}` tag loading the component's script.

Examples:
- Allowed: `x-data="components.filters"`, `x-on:click="filters.apply"`
- Not allowed: `x-data="{ open: true }"`, `x-on:click="count++"`

## Icons

- Use the `{% svg %}` template tag (defined in `cl/custom_filters/templatetags/svg_tags.py`)
- Icons live in `cl/assets/static-global/svg/`
- MUST NOT use Font Awesome classes

## Accessibility

- WCAG 2.2 AA minimum, AAA whenever practical
- No `tabindex` > 0 — use `0` (focusable) or `-1` (programmatic focus only)
- `target="_blank"` MUST include `rel="noopener"` or `rel="noreferrer"`
- All `<a>` tags in new templates MUST have a `class` attribute (enforced by CI)

## Banned in new templates

These are hard errors in CI:
See the CI rule script `frontend_checks.py` for details.

- jQuery (`$(` / `jQuery(`)
- Bootstrap classes
- Font Awesome (`fa-*` classes)
- React
- `{% include %}` (use Cotton components)
- `@click` / `@change` and other Alpine `@` shortcuts
- Inline `x-data` logic (`x-data="{ ... }"`)
- `@apply` in templates (only valid in CSS files)
