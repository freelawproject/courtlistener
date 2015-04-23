from cl.api.views import (
    court_index, documentation_index, bulk_data_index, rest_index,
    serve_pagerank_file, coverage_data, rest_index_v1
)
from django.conf.urls import url

urlpatterns = [
    # Documentation
    url(r'^api/$', documentation_index),
    url(r'^api/jurisdictions/$', court_index),
    url(r'^api/rest-info/$', rest_index),
    url(r'^api/rest-info/v1/$', rest_index_v1),
    url(r'^api/bulk-info/$', bulk_data_index),

    # Pagerank file
    url(r'^api/bulk/external_pagerank/$', serve_pagerank_file),

    # Coverage API
    url(r'^api/rest/v[12]/coverage/(\w{1,15})/', coverage_data),
]
