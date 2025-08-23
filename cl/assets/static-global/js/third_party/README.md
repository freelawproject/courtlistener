# Third-Party Dependencies For New Templates

This directory contains JavaScript needed for the new templates that is **not related to Alpine**.
For Alpine core, official plugins, or our own Alpine components/composables, see `/js/alpine/`.

- All files here are **upstream code**.
- They should **never be edited directly**.
- Keep both the unminified (`.js`) and minified (`.min.js`) versions so our `{% require_script %}` tag can automatically pick the right one depending on `DEBUG`.
- If any JS library requires its own stylesheet, all upstream CSS should live under `/css/third_party/` (see its README),
and any customizations should be in the form of overrides in Tailwind's input file (e.g. flatpickr).
