"""301 redirects from old API help pages to wiki.free.law.

API documentation has permanently moved to the wiki. These redirects
preserve external links and bookmarks. Internal links point directly
to wiki URLs to avoid double-hops.
"""

from django.conf import settings
from django.urls import path, re_path
from django.views.generic import RedirectView

# Simple path() redirects: (old_path, wiki_suffix, url_name | "")
_PATH_REDIRECTS: list[tuple[str, str, str]] = [
    ("help/api/", "", "api_index"),
    ("help/api/rest/", "rest/v4/overview", "rest_docs"),
    ("help/api/rest/v4/", "rest/v4/overview", ""),
    ("help/api/rest/v3/", "rest/v3/overview", ""),
    ("help/api/rest/v2/", "rest/v2/overview", ""),
    ("help/api/rest/v1/", "rest/v1/overview", ""),
    ("help/api/rest/changes/", "rest/change-log", "rest_change_log"),
    (
        "help/api/rest/v4/migration-guide/",
        "rest/v4/migration-guide",
        "migration_guide",
    ),
    ("help/api/bulk-data/", "bulk-data/bulk-legal-data", "bulk_data_index"),
    (
        "help/api/replication/",
        "replication/database-replication-for-organizations-and-researchers",
        "replication_docs",
    ),
    (
        "help/api/webhooks/getting-started/",
        "webhooks/getting-started",
        "webhooks_getting_started",
    ),
    # Legacy /api/* redirects (started 2022-12-05, no url names needed)
    ("api/", "", ""),
    ("api/bulk-info/", "bulk-data/bulk-legal-data", ""),
    (
        "api/replication/",
        "replication/database-replication-for-organizations-and-researchers",
        "",
    ),
]

# REST endpoint redirects using re_path for optional version prefix.
# Pattern: ^help/api/rest/(?:v[34]/)?{slug}/$
# All redirect to: settings.WIKI_API_BASE_URL/rest/v4/{wiki_slug}
# (url_slug, wiki_slug, url_name)
_REST_ENDPOINT_REDIRECTS: list[tuple[str, str, str]] = [
    ("citation-lookup", "citation-lookup", "citation_lookup_api"),
    ("case-law", "case-law", "case_law_api_help"),
    ("citations", "citations", "citation_api_help"),
    ("pacer", "pacer-data", "pacer_api_help"),
    ("recap", "recap", "recap_api_help"),
    ("judges", "judges", "judge_api_help"),
    ("oral-arguments", "oral-arguments", "oral_argument_api_help"),
    ("visualizations", "visualizations", "visualization_api_help"),
    (
        "financial-disclosures",
        "financial-disclosures",
        "financial_disclosures_api_help",
    ),
    ("search", "search", "search_api_help"),
    ("alerts", "alerts", "alert_api_help"),
    ("tags", "tags", "tag_api_help"),
    ("fields", "field-help", "field_api_help"),
]


def _build_patterns() -> list:
    """Build URL patterns from the redirect tables above."""
    patterns: list = []

    for old_path, wiki_suffix, name in _PATH_REDIRECTS:
        url = (
            f"{settings.WIKI_API_BASE_URL}/{wiki_suffix}"
            if wiki_suffix
            else settings.WIKI_API_BASE_URL
        )
        patterns.append(
            path(
                old_path,
                RedirectView.as_view(url=url, permanent=True),
                name=name or None,
            )
        )

    for slug, wiki_slug, name in _REST_ENDPOINT_REDIRECTS:
        patterns.append(
            re_path(
                rf"^help/api/rest/(?:v[34]/)?{slug}/$",
                RedirectView.as_view(
                    url=f"{settings.WIKI_API_BASE_URL}/rest/v4/{wiki_slug}",
                    permanent=True,
                ),
                name=name,
            )
        )

    # Webhooks overview (odd pattern: optional version, no trailing slug)
    patterns.append(
        re_path(
            r"^help/api/webhooks/(?:v[123])?/?$",
            RedirectView.as_view(
                url=f"{settings.WIKI_API_BASE_URL}/webhooks/about",
                permanent=True,
            ),
            name="webhooks_docs",
        )
    )

    # Legacy /api/rest-info/ redirect
    patterns.append(
        re_path(
            r"^api/rest-info/(?:v[123])?/?$",
            RedirectView.as_view(
                url=f"{settings.WIKI_API_BASE_URL}/rest/v4/overview",
                permanent=True,
            ),
        )
    )

    return patterns


wiki_redirect_urlpatterns = _build_patterns()
