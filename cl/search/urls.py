from django.urls import path, re_path

from cl.lib.ratelimiter import ratelimit_deny_list
from cl.search.feeds import (
    AllJurisdictionsFeed,
    JurisdictionFeed,
    SearchFeed,
    search_feed_error_handler,
)
from cl.search.models import SEARCH_TYPES
from cl.search.views import (
    advanced,
    es_search,
    export_search_results,
    home_router,
)

urlpatterns = [
    # Search pages
    path("", home_router, name="show_results"),
    path(
        "search/export/", export_search_results, name="export_search_results"
    ),
    path(
        "opinion/",
        advanced,
        kwargs={"search_type": SEARCH_TYPES.OPINION},
        name="advanced_o",
    ),
    path(
        "audio/",
        advanced,
        kwargs={"search_type": SEARCH_TYPES.ORAL_ARGUMENT},
        name="advanced_oa",
    ),
    path(
        "person/",
        advanced,
        kwargs={"search_type": SEARCH_TYPES.PEOPLE},
        name="advanced_p",
    ),
    path(
        "recap/",
        advanced,
        kwargs={"search_type": SEARCH_TYPES.RECAP},
        name="advanced_r",
    ),
    path("parenthetical/", es_search, name="advanced_pa"),
    # Feeds & Podcasts
    re_path(
        r"^feed/(search)/$",
        ratelimit_deny_list(search_feed_error_handler(SearchFeed())),
        name="search_feed",
    ),
    # lacks URL capturing b/c it will use GET queries.
    path(
        "feed/court/all/",
        ratelimit_deny_list(search_feed_error_handler(AllJurisdictionsFeed())),
        name="all_jurisdictions_feed",
    ),
    path(
        "feed/court/<str:court>/",
        ratelimit_deny_list(search_feed_error_handler(JurisdictionFeed())),
        name="jurisdiction_feed",
    ),
]
