"""301 redirects from old API and help pages to wiki.free.law.

API documentation and general help pages have permanently moved to the
wiki. These redirects preserve external links and bookmarks. Internal
links point directly to wiki URLs to avoid double-hops.
"""

from collections.abc import Callable

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

# Help pages that moved to the wiki. Same shape as _PATH_REDIRECTS, but
# these use settings.WIKI_HELP_BASE_URL. Started: 2026-07-26
# (old_path, wiki_suffix, url_name | "")
_HELP_PATH_REDIRECTS: list[tuple[str, str, str]] = [
    (
        "feeds/",
        "general/using-atom-and-rss-feeds-for-the-latest-updates",
        "feeds_info",
    ),
    (
        "podcasts/",
        "general/custom-podcasts-of-oral-argument-audio-recordings",
        "podcasts",
    ),
    (
        "help/markdown/",
        "general/markdown-guide-for-courtlistener",
        "markdown_help",
    ),
    ("help/alerts/", "alerts/", "alert_help"),
    (
        "help/delete-account/",
        "general/how-do-i-delete-my-courtlistener-account",
        "delete_help",
    ),
    (
        "help/tags-notes/",
        "general/using-tags-to-organize-docket-collections",
        "tag_notes_help",
    ),
    (
        "help/search-operators/",
        "search/advanced-search-and-query-techniques",
        "advanced_search",
    ),
    (
        "help/citegeist/",
        "search/the-citegeist-relevancy-engine",
        "citegeist_help",
    ),
    (
        "help/relative-dates/",
        "search/use-relative-date-queries-to-keep-alerts-fresh",
        "relative_dates",
    ),
    (
        "help/pray-and-pay/",
        "recap/help-with-pray-and-pay-project",
        "pray_and_pay_help",
    ),
    (
        "help/recap/email/",
        "recap/recap-email/recapemail-overview",
        "recap_email_help",
    ),
    # Added 2018-10-23
    (
        "search/advanced-techniques/",
        "search/advanced-search-and-query-techniques",
        "",
    ),
]

# Coverage help pages moved to the wiki (#7766). Unlike the tables above,
# these point at the WIKI_COVERAGE_*_URL settings directly by name rather
# than a wiki_suffix, since those settings are also the single source of
# truth consumed by inject_settings() for direct internal links — this
# avoids encoding the same wiki slugs in two places.
# Started: 2026-08-11
# (old_path, settings_name, url_name | "")
_COVERAGE_REDIRECTS: list[tuple[str, str, str]] = [
    ("help/coverage/", "WIKI_COVERAGE_URL", "coverage"),
    (
        "help/coverage/financial-disclosures/",
        "WIKI_COVERAGE_FDS_URL",
        "coverage_fds",
    ),
    ("help/coverage/oral-arguments/", "WIKI_COVERAGE_OA_URL", "coverage_oa"),
    (
        "help/coverage/opinions/",
        "WIKI_COVERAGE_OPINIONS_URL",
        "coverage_opinions",
    ),
    ("help/coverage/recap/", "WIKI_COVERAGE_RECAP_URL", "coverage_recap"),
    # Pre-2023 aliases (started 2023-01-17). Point straight at the wiki
    # rather than bouncing through /help/coverage/'s own redirect.
    ("coverage/", "WIKI_COVERAGE_URL", ""),
    ("coverage/financial-disclosures/", "WIKI_COVERAGE_FDS_URL", ""),
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


def _add_redirects(
    patterns: list,
    table: list[tuple[str, str, str]],
    url_resolver: Callable[[str], str],
) -> None:
    """Append path() redirects built from a redirect table.

    Every table above shares this exact shape — the only thing that
    differs between them is how a row's middle column resolves to a
    destination URL, so that's the one piece each call site supplies.

    :param patterns: The patterns list to append the built redirects to.
    :param table: Rows of (old_path, url_key, url_name | "").
    :param url_resolver: Converts a row's url_key into the destination
        URL, e.g. a wiki_suffix appended to a base URL, or a settings
        attribute name looked up via getattr.
    """
    for old_path, url_key, name in table:
        patterns.append(
            path(
                old_path,
                RedirectView.as_view(
                    url=url_resolver(url_key), permanent=True
                ),
                name=name or None,
            )
        )


def _build_patterns() -> list:
    """Build URL patterns from the redirect tables above."""
    patterns: list = []

    _add_redirects(
        patterns,
        _PATH_REDIRECTS,
        lambda wiki_suffix: (
            f"{settings.WIKI_API_BASE_URL}/{wiki_suffix}"
            if wiki_suffix
            else settings.WIKI_API_BASE_URL
        ),
    )

    _add_redirects(
        patterns,
        _HELP_PATH_REDIRECTS,
        lambda wiki_suffix: f"{settings.WIKI_HELP_BASE_URL}/{wiki_suffix}",
    )

    # Unlike the two tables above, these resolve via a settings attribute
    # name rather than a wiki_suffix — see the settings_name note on
    # _COVERAGE_REDIRECTS.
    _add_redirects(
        patterns,
        _COVERAGE_REDIRECTS,
        lambda settings_name: getattr(settings, settings_name),
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

    # FAQ page removed; content split across free.law and the wiki.
    # Redirect preserves external links and bookmarks. Started: 2026-07-26
    patterns.append(
        path(
            "faq/",
            RedirectView.as_view(pattern_name="help_home", permanent=True),
        )
    )

    return patterns


wiki_redirect_urlpatterns = _build_patterns()
