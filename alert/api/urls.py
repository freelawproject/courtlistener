from alert.api.views import (
    court_index, documentation_index, dump_index, rest_index,
    serve_pagerank_file, coverage_data
)

from alert.urls import pacer_codes
from django.conf.urls import patterns

urlpatterns = patterns('',
    # Documentation
    (r'^api/$', documentation_index),
    (r'^api/jurisdictions/$', court_index),
    (r'^api/rest-info/$', rest_index),
    (r'^api/bulk-info/$', dump_index),

    # Pagerank file
    (r'^api/bulk/external_pagerank/$', serve_pagerank_file),

    # Coverage API
    (r'^api/rest/v[12]/coverage/(all|%s)/' % '|'.join(pacer_codes),
     coverage_data),
)
