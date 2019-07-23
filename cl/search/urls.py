from django.conf.urls import url

from cl.search.views import advanced, show_results

from cl.search.feeds import (
    JurisdictionFeed, AllJurisdictionsFeed, SearchFeed
)

urlpatterns = [
    # Search pages
    url(
        r'^$', show_results, name='show_results',
    ),
    url(
        r'^opinion/$', advanced, name='advanced_o',
    ),
    url(
        r'^audio/$', advanced, name='advanced_oa',
    ),
    url(
        r'^person/$', advanced, name='advanced_p',
    ),
    url(
        r'^recap/$', advanced, name='advanced_r',
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
