## Updates (2026-04-24)
- Renamed `authority_count` to `has_authorities` in `views.py` and `utils.py` to accurately reflect that it's a bool (from `aexists()`), not a count. Corrected the type hint from `int` to `bool` in `build_docket_tabs()`.
- URL-encoded all query string values in `utils.py` metadata builders using `django.utils.http.urlencode` to prevent special characters from breaking URLs.
- Consolidated `sync_to_async` lambda wrappers for bankruptcy/originating court metadata into a single `_get_related` helper that isolates DB access, then calls the pure-Python builders directly.
- Extracted citation-building logic from `templatetags/extras.py` into `build_citation_string()` in `utils.py`. The template tag now calls the helper, inverting the dependency.
- Fixed merge regression in `v2_components.html`: restored `'variant'` keys (were incorrectly changed to `'style': 'btn-*'`) and restored the `buttons` prop description.
- Moved inline imports in new tests to the top of the file.
