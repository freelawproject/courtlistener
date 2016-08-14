from django.conf.urls import url

from cl.search.feeds import (
    JurisdictionFeed, AllJurisdictionsFeed, SearchFeed
)

urlpatterns = [
    # Search pages
    url(
        r'^$',
        'cl.search.views.show_results',
        name='show_results',
    ),
    url(
        r'^opinion/',
        'cl.search.views.advanced_o',
        name='advanced_o',
    ),
    url(
        r'^audio/',
        'cl.search.views.advanced_oa',
        name='advanced_oa',
    ),
    url(
        r'^person/',
        'cl.search.views.advanced_p',
        name='advanced_p',
    ),

    # Feeds & Podcasts
    url(
        r'^feed/(search)/$',
        SearchFeed(),
        name='search_feed'
    ),

    # lacks URL capturing b/c it will use GET queries.
    url(
        r'^feed/court/all/$',
        AllJurisdictionsFeed(),
        name='all_jurisdictions_feed'
    ),
    url(
        r'^feed/court/(?P<court>\w{1,15})/$',
        JurisdictionFeed(),
        name='jurisdiction_feed'
    ),
]
