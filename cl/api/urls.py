from cl.api import views

from django.conf.urls import url, include
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'dockets', views.DocketViewSet)
router.register(r'courts', views.CourtViewSet)
router.register(r'audio', views.AudioViewSet)
router.register(r'clusters', views.OpinionClusterViewSet)
router.register(r'opinions', views.OpinionViewSet)
router.register(r'cited-by', views.OpinionsCitedViewSet)
router.register(r'search', views.SearchViewSet, base_name='search')


urlpatterns = [
    # url(r'^api/rest/(?P<version>[v3]+)/', include(router.urls)),
    url(r'^api-auth/',
        include('rest_framework.urls', namespace='rest_framework')),
    url(r'^api/rest/(?P<version>[v3]+)/', include(router.urls)),

    # Documentation
    url(r'^api/$',
        views.api_index,
        name='api_index'),
    url(r'^api/jurisdictions/$',
        views.court_index,
        name='court_index'),
    url(r'^api/rest-info/(?P<version>v[123])?/?$',
        views.rest_docs,
        name='rest_docs'),
    url(r'^api/bulk-info/$',
        views.bulk_data_index,
        name='bulk_data_index'),
    url(r'^api/rest/v(?P<version>[123])/coverage/(?P<court>.+)/$',
        views.coverage_data,
        name='coverage_data'),

    # Pagerank file
    url(r'^api/bulk/external_pagerank/$',
        views.serve_pagerank_file,
        name='pagerank_file'),

    # Deprecation Dates:
    # v1: 2015-11-01
    # v2: 2015-11-01
    url(r'^api/rest/v(?P<v>[12])/.*',
        views.deprecated_api,
        name='deprecated_api'),
]
