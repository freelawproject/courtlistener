from django.conf.urls import url
from django.views.generic import RedirectView

from cl.simple_pages.sitemap import sitemap_maker
from cl.simple_pages.views import (
    advanced_search,
    alert_help,
    contact,
    contact_thanks,
    contribute,
    coverage_graph,
    delete_help,
    donation_help,
    faq,
    feeds,
    latest_terms,
    markdown_help,
    old_terms,
    podcasts,
    robots,
    validate_for_wot,
    help_home,
)

urlpatterns = [
    # Footer stuff
    url(r"^faq/$", faq, name="faq"),
    url(r"^coverage/$", coverage_graph, name="coverage"),
    url(r"^feeds/$", feeds, name="feeds_info"),
    url(r"^podcasts/$", podcasts, name="podcasts"),
    url(r"^contribute/$", contribute, name="contribute"),
    url(r"^contact/$", contact, name="contact"),
    url(r"^contact/thanks/$", contact_thanks, name="contact_thanks"),
    # Help pages
    url(r"^help/$", help_home, name="help_home"),
    url(r"^help/markdown/$", markdown_help, name="markdown_help"),
    url(r"^help/alerts/$", alert_help, name="alert_help"),
    url(r"^help/donations/$", donation_help, name="donation_help"),
    url(r"^help/delete-account/$", delete_help, name="delete_help"),
    url(r"^help/search-operators/$", advanced_search, name="advanced_search"),
    # Added 2018-10-23
    url(
        r"^search/advanced-techniques/$",
        RedirectView.as_view(pattern_name="advanced_search", permanent=True),
    ),
    url(r"^terms/v/(\d{1,2})/$", old_terms, name="old_terms"),
    url(r"^terms/$", latest_terms, name="terms"),
    # Robots
    url(r"^robots\.txt$", robots, name="robots"),
    # Sitemap:
    url(
        r"^sitemap-simple-pages\.xml$",
        sitemap_maker,
        name="simple_pages_sitemap",
    ),
    # SEO-related stuff
    url(r"^mywot8f5568174e171ff0acff.html$", validate_for_wot),
]
