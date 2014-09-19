from alert.api.views import (
    court_index, documentation_index, dump_index, rest_index,
    serve_or_gen_dump, serve_pagerank_file, coverage_data
)
from alert.urls import pacer_codes
from django.conf.urls import patterns

urlpatterns = patterns('',
    (r'^api/$', documentation_index),
    (r'^api/jurisdictions/$', court_index),
    (r'^api/rest-info/$', rest_index),
    (r'^api/bulk-info/$', dump_index),
    (r'^api/bulk/(?P<court>all|%s)\.xml\.gz$' % "|".join(pacer_codes),
     serve_or_gen_dump),
    (r'^api/bulk/(?P<year>\d{4})/(?P<court>all|%s)\.xml\.gz$' % "|".join(
        pacer_codes),
     serve_or_gen_dump),
    (r'^api/bulk/(?P<year>\d{4})/(?P<month>\d{1,2})/(?P<court>all|%s)\.xml\.gz$' % "|".join(
            pacer_codes),
        serve_or_gen_dump),
    (r'^api/bulk/(?P<year>\d{4})/(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<court>all|%s)\.xml\.gz$' % "|".join(
            pacer_codes),
        serve_or_gen_dump),
    (r'^api/bulk/external_pagerank/$', serve_pagerank_file),
    (r'^api/rest/v[12]/coverage/(all|%s)/' % '|'.join(pacer_codes),
     coverage_data),
)
