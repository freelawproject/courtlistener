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
    help_home,
    validate_for_wot,
)

urlpatterns = [
    # Footer stuff
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
