from cl.api.views import (
    court_index, api_index, bulk_data_index, rest_index, serve_pagerank_file,
    coverage_data, deprecated_api,
)
from django.conf.urls import url

urlpatterns = [
    # Documentation
    url(
        r'^api/$',
        api_index,
        name='api_index',
    ),
    url(
        r'^api/jurisdictions/$',
        court_index,
        name='court_index',
    ),
    url(
        r'^api/rest-info/(?:v(?P<version>[12])/)?$',
        rest_index,
        name='rest_index',
    ),
    url(
        r'^api/bulk-info/$',
        bulk_data_index,
        name='bulk_data_index',
    ),

    # Pagerank file
    url(
        r'^api/bulk/external_pagerank/$',
        serve_pagerank_file,
        name='pagerank_file',
    ),

    # Coverage API
    url(
        r'^api/rest/v(?P<version>[2])/coverage/(?P<court>\w{1,15})/',
        coverage_data,
        name='coverage_api',
    ),
    url(
        # Deprecation Dates:
        # v1: 2015-10-01
        r'^api/rest/v(?P<v>[1])/.*',
        deprecated_api,
        name='deprecated_api',
    ),
]
