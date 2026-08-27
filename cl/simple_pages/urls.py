from django.conf import settings
from django.urls import path
from django.views.generic import RedirectView
from django.views.generic.base import TemplateView

from cl.simple_pages.views import (
    broken_email_help,
    components,
    contact,
    contact_thanks,
    help_home,
    validate_for_wot,
)

urlpatterns = [
    # Footer stuff
    path("contact/", contact, name="contact"),  # type: ignore[arg-type]
    path("contact/thanks/", contact_thanks, name="contact_thanks"),  # type: ignore[arg-type]
    # Help pages
    path("help/", help_home, name="help_home"),  # type: ignore[arg-type]
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
