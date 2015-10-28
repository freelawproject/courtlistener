from cl.search.feeds import (
    JurisdictionFeed, AllJurisdictionsFeed, SearchFeed
)
from django.conf.urls import url

urlpatterns = [
    # Search pages
    url(r'^$', 'cl.search.views.show_results'),

    # Feeds & Podcasts
    url(r'^feed/(search)/$', SearchFeed()),
    # lacks URL capturing b/c it will use GET queries.
    url(r'^feed/court/all/$', AllJurisdictionsFeed()),
    url(r'^feed/court/(?P<court>\w{1,15})/$', JurisdictionFeed()),
]
