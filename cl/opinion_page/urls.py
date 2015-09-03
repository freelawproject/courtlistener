from cl.opinion_page.sitemap import opinion_sitemap_maker
from cl.opinion_page.views import (
    view_opinion, view_authorities, view_docket, cluster_visualizations
)
from django.conf.urls import url


urlpatterns = [
    url(
        r'^opinion/(?P<pk>\d*)/(?P<slug>[^/]*)/authorities/$',
        view_authorities,
        name='view_authorities'
    ),
    url(
        r'^opinion/(?P<pk>\d*)/(?P<slug>[^/]*)/visualizations/$',
        cluster_visualizations,
        name='cluster_visualizations',
    ),
    url(
        r'^opinion/(\d*)/([^/]*)/$',
        view_opinion,
        name="view_case"
    ),
    url(
        r'^docket/(\d*)/([^/]*)/$',
        view_docket,
        name="view_docket"
    ),

    # Sitemap
    url(
        r'^sitemap-opinions\.xml',
        opinion_sitemap_maker
    ),
]
