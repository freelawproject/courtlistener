from django.urls import path, re_path

from cl.search.feeds import (
    AllJurisdictionsFeed,
    JurisdictionFeed,
    SearchFeed,
    search_feed_error_handler,
)
from cl.search.views import advanced, es_search, show_results

urlpatterns = [
    # Search pages
    path("", show_results, name="show_results"),
    path("opinion/", advanced, name="advanced_o"),
    path("audio/", advanced, name="advanced_oa"),
    path("person/", advanced, name="advanced_p"),
    path("recap/", advanced, name="advanced_r"),
    path("parenthetical/", es_search, name="advanced_pa"),
    path("financial-disclosures/", advanced, name="advanced_fd"),
    # Feeds & Podcasts
    re_path(
        r"^feed/(search)/$",
        search_feed_error_handler(SearchFeed()),
        name="search_feed",
    ),
    # lacks URL capturing b/c it will use GET queries.
    path(
        "feed/court/all/",
        search_feed_error_handler(AllJurisdictionsFeed()),
        name="all_jurisdictions_feed",
    ),
    path(
        "feed/court/<str:court>/",
        search_feed_error_handler(JurisdictionFeed()),
        name="jurisdiction_feed",
    ),
]
