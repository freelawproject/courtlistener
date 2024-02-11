from django.urls import path
from django.views.generic import RedirectView
from django.views.generic.base import TemplateView

from cl.simple_pages.views import (
    advanced_search,
    alert_help,
    broken_email_help,
    contact,
    contact_thanks,
    contribute,
    coverage_fds,
    coverage_graph,
    coverage_opinions,
    delete_help,
    faq,
    feeds,
    help_home,
    latest_terms,
    markdown_help,
    old_terms,
    podcasts,
    recap_email_help,
    tag_notes_help,
    validate_for_wot,
)

urlpatterns = [
    # Footer stuff
    path("faq/", faq, name="faq"),  # type: ignore[arg-type]
    path("feeds/", feeds, name="feeds_info"),  # type: ignore[arg-type]
    path("podcasts/", podcasts, name="podcasts"),  # type: ignore[arg-type]
    path("contribute/", contribute, name="contribute"),  # type: ignore[arg-type]
    path("contact/", contact, name="contact"),  # type: ignore[arg-type]
    path("contact/thanks/", contact_thanks, name="contact_thanks"),  # type: ignore[arg-type]
    # Help pages
    path("help/", help_home, name="help_home"),  # type: ignore[arg-type]
    path("help/coverage/", coverage_graph, name="coverage"),  # type: ignore[arg-type]
    path(
        "help/coverage/opinions/", coverage_opinions, name="coverage_opinions"  # type: ignore[arg-type]
    ),
    path(
        "help/coverage/financial-disclosures/",
        coverage_fds,  # type: ignore[arg-type]
        name="coverage_fds",
    ),
    path("help/markdown/", markdown_help, name="markdown_help"),  # type: ignore[arg-type]
    path("help/alerts/", alert_help, name="alert_help"),  # type: ignore[arg-type]
    path("help/delete-account/", delete_help, name="delete_help"),  # type: ignore[arg-type]
    path("help/tags-notes/", tag_notes_help, name="tag_notes_help"),  # type: ignore[arg-type]
    path("help/search-operators/", advanced_search, name="advanced_search"),  # type: ignore[arg-type]
    path("help/recap/email/", recap_email_help, name="recap_email_help"),  # type: ignore[arg-type]
    path("help/broken-email/", broken_email_help, name="broken_email_help"),  # type: ignore[arg-type]
    # Added 2018-10-23
    path(
        "search/advanced-techniques/",
        RedirectView.as_view(pattern_name="advanced_search", permanent=True),
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
    path("terms/v/<int:v>/", old_terms, name="old_terms"),  # type: ignore[arg-type]
    path("terms/", latest_terms, name="terms"),  # type: ignore[arg-type]
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
