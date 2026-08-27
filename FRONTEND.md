# Frontend Guide

For the full design rationale and migration plan, see the [New Frontend Architecture wiki][wiki].

Rules here are enforced by CI (`frontend_checks.py`). If this doc and the script disagree, the script is the source of truth.

[wiki]: https://github.com/freelawproject/courtlistener/wiki/New-Frontend-Architecture

## Two stacks

CourtListener is migrating from Bootstrap 3 / jQuery to Tailwind v3 / Alpine.js / Cotton. Both stacks coexist.

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

Sync notice format:
```html
{% comment %}
╔══════════════════════════════════════════════════════════════════════════╗
║                               ATTENTION!                                ║
║ This template has a new version behind the use_new_design waffle flag.  ║
║                                                                         ║
║ When modifying this template, please also update the new version at:    ║
║ <path to v2_ template>                                                  ║
╚══════════════════════════════════════════════════════════════════════════╝
{% endcomment %}
```

## Cotton components

- Live in `templates/cotton/`, snake_case filenames
- Called with `<c-kebab-case />` (e.g., `templates/cotton/alert_banner.html` → `<c-alert-banner />`)
- Use `<c-vars />` to declare attributes; undeclared attributes are available via `{{ attrs }}` (useful for passing through to a child element)
- Named slots: `<c-slot name="slot_name">content</c-slot>`
- Check existing components before creating new ones — component library at `cl/simple_pages/templates/v2_components.html`
- New components MUST have a corresponding entry in `v2_components.html` with four sections: Demo, Props, Slots, Code (even if some are empty)
- Avoid hardcoded `id` attributes in components — they create duplicate IDs when a component is reused on the same page

**Dynamic attributes** — prefix with `:` to pass Django context variables:
- Correct: `:items="nav_items"`
- Wrong: `:items="{{ nav_items }}"` (do NOT use DTL `{{ }}` inside Cotton's `:` syntax)

## Tailwind CSS

- Classes MUST be written as complete strings — never dynamically constructed (e.g., `` `text-greyscale-${val}` `` will silently break because Tailwind can't detect dynamically constructed class names at build time)
- `input.css` (`cl/assets/tailwind/input.css`): prefer `@apply` with Tailwind classes over raw CSS properties
- Don't create single-use utility classes — use inline Tailwind classes instead
- Branding values (colors, spacing, fonts) go in `tailwind.config.js`, not as custom classes in `input.css`

## Alpine.js

CourtListener uses the CSP-friendly Alpine build. Nearly all Alpine documentation examples use inline JS that will NOT work here.

- No `@` shorthand — use `x-on:click`, not `@click`
- No `:` shorthand — use `x-bind:class`, not `:class` (`:` is Cotton's attribute syntax; Cotton uses `::` for Alpine bind pass-through, but we avoid that and use explicit `x-bind:` instead)
- No inline `x-data` logic — use `x-data="componentName"` and define the component in an external script
- `x-model` and `x-modelable` are NOT supported (require `unsafe-eval`) — use `data-` attributes and events instead
- Only `x-` directives, no inline JS expressions

When adding `x-data` to a template, there MUST be a corresponding `{% require_script %}` tag loading the component's script.

### `{% require_script %}`

```html
{% load component_tags %}
{% require_script "js/alpine/components/my_component.js" %}
```

Omit the extension only for scripts that have minified versions (the tag resolves `.min.js` in production):
```html
{% require_script "js/alpine/plugins/intersect" defer=True %}
```

Plugins MUST be deferred (`defer=True`).

### File organization

| Type | Location |
|---|---|
| Component scripts | `cl/assets/static-global/js/alpine/components/` |
| Composables | `cl/assets/static-global/js/alpine/composables/` |
| Plugins | `cl/assets/static-global/js/alpine/plugins/` |

Component JS files match their Cotton template name: `cotton/my_component.html` → `alpine/components/my_component.js`.

### Passing Django data to Alpine

- Preferred: HTML `data-` attributes, accessed via `this.$el.dataset` in JS
- Complex data: DTL `json_script` filter

Examples:
- Allowed: `x-data="components.filters"`, `x-on:click="filters.apply"`
- Not allowed: `x-data="{ open: true }"`, `x-on:click="count++"`

## Icons

- Use the `{% svg %}` template tag (defined in `cl/custom_filters/templatetags/svg_tags.py`)
- Icons live in `cl/assets/static-global/svg/`
- New templates MUST NOT use Font Awesome classes

## Semantic HTML

- Use `<dl>` for key-value and metadata pairs, not `<table>` or `<ol>`
- `<ul>` nests inside `<li>`, never directly inside another `<ul>`
- Prefer `<details>/<summary>` for collapsible content (progressive enhancement)

## Links

- All `<a>` tags in new templates MUST have a `class` attribute
- Internal links: `text-primary-600`
- External links: `underline`
- `target="_blank"` MUST include `rel="noopener"` or `rel="noreferrer"` (`noreferrer` alone is sufficient — it implies `noopener`)
- Do NOT add `nofollow` to editorial links — `nofollow` is only for user-generated content

## Accessibility

- WCAG 2.2 AA minimum, AAA whenever practical
- No `tabindex` > 0 — use `0` (focusable) or `-1` (programmatic focus only)
- Prefer native semantic HTML over ARIA; complement with ARIA where needed
- When rewriting jQuery/React to Alpine, preserve keyboard navigation (arrow keys, Escape, focus management)
- Dynamic content updates (search results, form validation) need `aria-live` regions

## CI enforcement

The rules in this doc are enforced as hard errors that block merge. See `frontend_checks.py` for the full list. Additional CI checks not covered above:

**Warnings** (annotated on PR, doesn't block):
- `{% include %}` in v2 templates (use Cotton components; known exceptions exist)
- New cotton component without a component library entry
- `x-data` without a corresponding `{% require_script %}`
- Placeholder text (TODO, TBD, FIXME, Lorem ipsum)
