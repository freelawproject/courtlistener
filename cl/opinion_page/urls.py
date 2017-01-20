from django.conf.urls import url

from cl.opinion_page.sitemap import opinion_sitemap_maker, recap_sitemap_maker
from cl.opinion_page.views import (
    view_opinion, view_authorities, view_docket, cluster_visualizations,
    citation_redirector, view_recap_document,
    ajax_get_recap_documents_and_attachments, block_item,
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
        r'^docket-entry/(\d*)/$',
        ajax_get_recap_documents_and_attachments,
        name="ajax_get_recap_documents_and_attachments"
    ),
    url(
        r'^c/(?:(?P<reporter>.*)/(?P<volume>\d{1,4})/(?P<page>\d{1,4})/)?$',
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
