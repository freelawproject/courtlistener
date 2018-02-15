from django.conf.urls import url

from cl.opinion_page.sitemap import opinion_sitemap_maker, recap_sitemap_maker
from cl.opinion_page.views import (
    block_item, cluster_visualizations, view_opinion, citation_redirector,
    redirect_docket_recap, view_authorities, view_docket, view_parties,
    view_recap_document,
)

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
    url(
        r'^recap/gov.uscourts'
        r'\.(?P<court>[^\./]+)'
        r'\.(?P<pacer_case_id>[^\./]+)/$',
        redirect_docket_recap,
        name="redirect_docket_recap",
    ),
    url(
        r'^docket/(?P<docket_id>\d*)/parties/(?P<slug>[^/]*)/$',
        view_parties,
        name="docket_parties",
    ),
    url(
        r'^docket/(?P<docket_id>\d*)/(?P<doc_num>\d*)/(?P<slug>[^/]*)/$',
        view_recap_document,
        name='view_recap_document',
    ),
    url(
        r'^docket/(?P<docket_id>\d*)/(?P<doc_num>\d*)/(?P<att_num>\d*)/(?P<slug>[^/]*)/$',
        view_recap_document,
        name='view_recap_attachment',
    ),
    url(
        r'^c/(?:(?P<reporter>.*)/(?P<volume>\d{1,4})/(?P<page>\d{1,8})/)?$',
        citation_redirector,
        name="citation_redirector",
    ),

    # Sitemap
    url(
        r'^sitemap-opinions\.xml',
        opinion_sitemap_maker,
        name='opinion_sitemap',
    ),
    url(
        r'^sitemap-recap\.xml',
        recap_sitemap_maker,
        name='recap_sitemap',
    ),

    # Admin tools
    url(
        r'^admin-tools/block-item/$',
        block_item,
        name='block_item',
    )
]
