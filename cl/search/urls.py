from cl.search import api3
from cl.search.feeds import (
    JurisdictionFeed, AllJurisdictionsFeed, SearchFeed
)

from django.conf.urls import include, url
from tastypie.api import Api

# Set up the API
v3_api = Api(api_name='v3')
v3_api.register(api3.DocketResource(tally_name='search.api3.docket'))
v3_api.register(api3.AudioResource(tally_name='search.api3.audio'))
v3_api.register(api3.ClusterResource(tally_name='search.api3.cluster'))
v3_api.register(api3.OpinionResource(tally_name='search.api3.opinion'))
v3_api.register(api3.CitesResource(tally_name='search.api3.cites'))
v3_api.register(api3.CitedByResource(tally_name='search.api3.cited-by'))
v3_api.register(api3.JurisdictionResource(tally_name='search.api3.court'))
v3_api.register(api3.SearchResource(tally_name='search.api3.search'))

urlpatterns = [
    # Search pages
    url(r'^$', 'cl.search.views.show_results'),  # the home page!

    # The API
    url(r'^api/rest/', include(v3_api.urls)),

    # Feeds & Podcasts
    url(r'^feed/(search)/$', SearchFeed()),
    # lacks URL capturing b/c it will use GET queries.
    url(r'^feed/court/all/$', AllJurisdictionsFeed()),
    url(r'^feed/court/(?P<court>\w{1,15})/$', JurisdictionFeed()),
]
