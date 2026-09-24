# Third-Party Dependencies For New Templates

This directory contains JavaScript needed for the new templates that is **not related to Alpine**.
For Alpine core, official plugins, or our own Alpine components/composables, see `/js/alpine/`.

- All files here are **upstream code**.
- They should **never be edited directly**.
- Keep both the unminified (`.js`) and minified (`.min.js`) versions so our `{% require_script %}` tag can automatically pick the right one depending on `DEBUG`. Simply omit the file extension and the template tag will do its magic.
- If any JS library requires its own stylesheet, all upstream CSS should live under `/css/third_party/` (see its README),
and any customizations should be in the form of overrides in Tailwind's input file (e.g. flatpickr).

## htmx

Current version: **2.0.10**

| File | CDN URL |
|------|---------|
| `htmx.js` | https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.js |
| `htmx.min.js` | https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js |

Legacy templates run htmx 1.7.0 from `/js/` and are not to be upgraded; that copy retires with legacy.
