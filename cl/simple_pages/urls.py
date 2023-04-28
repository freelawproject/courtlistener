from django.urls import path
from django.views.generic import RedirectView

from cl.simple_pages.views import (
    advanced_search,
    alert_help,
    broken_email_help,
    contact,
    contact_thanks,
    contribute,
    coverage_fds,
    coverage_graph,
    delete_help,
    donation_help,
    faq,
    feeds,
    help_home,
    latest_terms,
    markdown_help,
    old_terms,
    podcasts,
    recap_email_help,
    robots,
    tag_notes_help,
    validate_for_wot,
)

urlpatterns = [
    # Footer stuff
    path("faq/", faq, name="faq"),
    path("feeds/", feeds, name="feeds_info"),
    path("podcasts/", podcasts, name="podcasts"),
    path("contribute/", contribute, name="contribute"),
    path("contact/", contact, name="contact"),
    path("contact/thanks/", contact_thanks, name="contact_thanks"),
    # Help pages
    path("help/", help_home, name="help_home"),
    path("help/coverage/", coverage_graph, name="coverage"),
    path(
        "help/coverage/financial-disclosures/",
        coverage_fds,
        name="coverage_fds",
    ),
    path("help/markdown/", markdown_help, name="markdown_help"),
    path("help/alerts/", alert_help, name="alert_help"),
    path("help/donations/", donation_help, name="donation_help"),
    path("help/delete-account/", delete_help, name="delete_help"),
    path("help/tags-notes/", tag_notes_help, name="tag_notes_help"),
    path("help/search-operators/", advanced_search, name="advanced_search"),
    path("help/recap/email/", recap_email_help, name="recap_email_help"),
    path("help/broken-email/", broken_email_help, name="broken_email_help"),
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
    path("terms/v/<int:v>/", old_terms, name="old_terms"),
    path("terms/", latest_terms, name="terms"),
    # Robots
    path("robots.txt", robots, name="robots"),
    # SEO-related stuff
    path("mywot8f5568174e171ff0acff.html", validate_for_wot),
]
