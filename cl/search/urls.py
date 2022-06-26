from django.urls import path, re_path

from cl.search.feeds import AllJurisdictionsFeed, JurisdictionFeed, SearchFeed
from cl.search.views import advanced, show_results, es_search_results, es_search

urlpatterns = [
    # Search pages
    path("", show_results, name="show_results"),
    path("opinion/", advanced, name="advanced_o"),
    path("audio/", advanced, name="advanced_oa"),
    path("person/", advanced, name="advanced_p"),
    path("recap/", advanced, name="advanced_r"),
    path("financial-disclosures/", advanced, name="advanced_fd"),
    # Elastic search pages
    # TODO optional param
    path("search/", es_search, name="es_search"),
    path("search/<str:type>/", es_search, name="es_search"),
    path("results/<str:type>/", es_search_results, name="es_results"),
    # Feeds & Podcasts
    re_path(r"^feed/(search)/$", SearchFeed(), name="search_feed"),
    # lacks URL capturing b/c it will use GET queries.
    path(
        "feed/court/all/",
        AllJurisdictionsFeed(),
        name="all_jurisdictions_feed",
    ),
    path(
        "feed/court/<str:court>/",
        JurisdictionFeed(),
        name="jurisdiction_feed",
    ),
]
