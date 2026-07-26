from django.conf import settings
from django.urls import path
from django.views.generic import RedirectView
from django.views.generic.base import TemplateView

from cl.simple_pages.views import (
    broken_email_help,
    components,
    contact,
    contact_thanks,
    coverage,
    coverage_fds,
    coverage_oa,
    coverage_opinions,
    coverage_recap,
    faq,
    help_home,
    validate_for_wot,
)

urlpatterns = [
    # Footer stuff
    path("faq/", faq, name="faq"),  # type: ignore[arg-type]
    # Feeds and podcasts help moved to the wiki. These redirects preserve
    # external links and bookmarks; internal links point directly to wiki
    # URLs to avoid double-hops. Started: 2026-07-26
    path(
        "feeds/",
        RedirectView.as_view(
            url=f"{settings.WIKI_HELP_BASE_URL}/general/using-atom-and-rss-feeds-for-the-latest-updates",
            permanent=True,
        ),
        name="feeds_info",
    ),
    path(
        "podcasts/",
        RedirectView.as_view(
            url=f"{settings.WIKI_HELP_BASE_URL}/general/custom-podcasts-of-oral-argument-audio-recordings",
            permanent=True,
        ),
        name="podcasts",
    ),
    path("contact/", contact, name="contact"),  # type: ignore[arg-type]
    path("contact/thanks/", contact_thanks, name="contact_thanks"),  # type: ignore[arg-type]
    # Help pages
    path("help/", help_home, name="help_home"),  # type: ignore[arg-type]
    path("help/coverage/", coverage, name="coverage"),  # type: ignore[arg-type]
    path(
        "help/coverage/financial-disclosures/",
        coverage_fds,  # type: ignore[arg-type]
        name="coverage_fds",
    ),
    path("help/coverage/oral-arguments/", coverage_oa, name="coverage_oa"),  # type: ignore[arg-type]
    path(
        "help/coverage/opinions/",
        coverage_opinions,
        name="coverage_opinions",  # type: ignore[arg-type]
    ),
    path(
        "help/coverage/recap/",
        coverage_recap,  # type: ignore[arg-type]
        name="coverage_recap",
    ),
    # These help pages moved to the wiki. Same redirect convention as
    # above. Started: 2026-07-26
    path(
        "help/markdown/",
        RedirectView.as_view(
            url=f"{settings.WIKI_HELP_BASE_URL}/general/markdown-guide-for-courtlistener",
            permanent=True,
        ),
        name="markdown_help",
    ),
    path(
        "help/alerts/",
        RedirectView.as_view(
            url=f"{settings.WIKI_HELP_BASE_URL}/alerts/",
            permanent=True,
        ),
        name="alert_help",
    ),
    path(
        "help/delete-account/",
        RedirectView.as_view(
            url=f"{settings.WIKI_HELP_BASE_URL}/general/how-do-i-delete-my-courtlistener-account",
            permanent=True,
        ),
        name="delete_help",
    ),
    path(
        "help/tags-notes/",
        RedirectView.as_view(
            url=f"{settings.WIKI_HELP_BASE_URL}/general/using-tags-to-organize-docket-collections",
            permanent=True,
        ),
        name="tag_notes_help",
    ),
    path(
        "help/search-operators/",
        RedirectView.as_view(
            url=f"{settings.WIKI_HELP_BASE_URL}/search/advanced-search-and-query-techniques",
            permanent=True,
        ),
        name="advanced_search",
    ),
    path(
        "help/citegeist/",
        RedirectView.as_view(
            url=f"{settings.WIKI_HELP_BASE_URL}/search/the-citegeist-relevancy-engine",
            permanent=True,
        ),
        name="citegeist_help",
    ),
    path(
        "help/relative-dates/",
        RedirectView.as_view(
            url=f"{settings.WIKI_HELP_BASE_URL}/search/use-relative-date-queries-to-keep-alerts-fresh",
            permanent=True,
        ),
        name="relative_dates",
    ),
    path(
        "help/pray-and-pay/",
        RedirectView.as_view(
            url=f"{settings.WIKI_HELP_BASE_URL}/recap/help-with-pray-and-pay-project",
            permanent=True,
        ),
        name="pray_and_pay_help",
    ),
    path(
        "help/recap/email/",
        RedirectView.as_view(
            url=f"{settings.WIKI_HELP_BASE_URL}/recap/recap-email/recapemail-overview",
            permanent=True,
        ),
        name="recap_email_help",
    ),
    path("help/broken-email/", broken_email_help, name="broken_email_help"),  # type: ignore[arg-type]
    path(
        "help/mcp/",
        RedirectView.as_view(
            url=f"{settings.WIKI_API_BASE_URL}/mcp/model-context-protocol-mcp-server-for-agentic-access",
            permanent=True,
        ),
        name="mcp_help",
    ),
    path(
        "help/cluster-redirections/",
        RedirectView.as_view(
            url=f"{settings.WIKI_API_BASE_URL}/rest/opinion-cluster-redirections",
            permanent=True,
        ),
        name="cluster_redirections_help",
    ),
    # Added 2018-10-23
    path(
        "search/advanced-techniques/",
        RedirectView.as_view(
            url=f"{settings.WIKI_HELP_BASE_URL}/search/advanced-search-and-query-techniques",
            permanent=True,
        ),
    ),
    # Redirect coverage pages from /coverage/ to /help/coverage/
    # Started: 2023-01-17
    path(
        "coverage/",
        RedirectView.as_view(pattern_name="coverage", permanent=True),
    ),
    path(
        "coverage/financial-disclosures/",
        RedirectView.as_view(pattern_name="coverage_fds", permanent=True),
    ),
    # Terms moved to the wiki. These redirects preserve external links
    # and bookmarks; internal links point directly to wiki URLs to avoid
    # double-hops. Started: 2026-07-23
    path(
        "terms/v/<int:v>/",
        RedirectView.as_view(url=settings.WIKI_TERMS_URL, permanent=True),
        name="old_terms",
    ),
    path(
        "terms/",
        RedirectView.as_view(url=settings.WIKI_TERMS_URL, permanent=True),
        name="terms",
    ),
    path("components/", components, name="components"),  # type: ignore[arg-type]
    # Robots
    path(
        "robots.txt",
        TemplateView.as_view(
            template_name="robots.txt", content_type="text/plain"
        ),
        name="robots",
    ),
    # SEO-related stuff
    path("mywot8f5568174e171ff0acff.html", validate_for_wot),  # type: ignore[arg-type]
]
