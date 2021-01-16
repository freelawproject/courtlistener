from django.conf.urls import url

from cl.opinion_page.views import (
    block_item,
    citation_redirector,
    cluster_visualizations,
    court_homepage,
    court_publish_page,
    docket_idb_data,
    redirect_docket_recap,
    view_authorities,
    view_docket,
    view_opinion,
    view_parties,
    view_recap_document,
)

urlpatterns = [
    # Court pages
    url(r"^court/(?P<pk>[^/]*)/$", court_homepage, name="court_homepage"),
    url(
        r"^court/(?P<pk>[^/]*)/new-opinion/$",
        court_publish_page,
        name="court_publish_page",
    ),
    # Opinion pages
    url(
        r"^opinion/(?P<pk>\d+)/(?P<slug>[^/]*)/authorities/$",
        view_authorities,
        name="view_authorities",
    ),
    url(
        r"^opinion/(?P<pk>\d+)/(?P<slug>[^/]*)/visualizations/$",
        cluster_visualizations,
        name="cluster_visualizations",
    ),
    url(r"^opinion/(\d+)/([^/]*)/$", view_opinion, name="view_case"),
    url(r"^docket/(\d+)/([^/]*)/$", view_docket, name="view_docket"),
    url(
        r"^recap/gov.uscourts"
        r"\.(?P<court>[^\./]+)"
        r"\.(?P<pacer_case_id>[^\./]+)/?$",
        redirect_docket_recap,
        name="redirect_docket_recap",
    ),
    url(
        r"^docket/(?P<docket_id>\d+)/parties/(?P<slug>[^/]*)/$",
        view_parties,
        name="docket_parties",
    ),
    url(
        r"^docket/(?P<docket_id>\d+)/idb/(?P<slug>[^/]*)/$",
        docket_idb_data,
        name="docket_idb_data",
    ),
    url(
        r"^docket/(?P<docket_id>\d+)/(?P<doc_num>\d+)/(?P<slug>[^/]*)/$",
        view_recap_document,
        name="view_recap_document",
    ),
    url(
        r"^docket/(?P<docket_id>\d+)/"
        r"(?P<doc_num>\d+)/"
        r"(?P<att_num>\d+)/"
        r"(?P<slug>[^/]*)/$",
        view_recap_document,
        name="view_recap_attachment",
    ),
    url(
        r"^c/(?:(?P<reporter>.*)/(?P<volume>\d{1,10})/(?P<page>.*)/)?$",
        citation_redirector,
        name="citation_redirector",
    ),
    url(
        r"^c/(?P<reporter>.*)/(?P<volume>\d{1,10})/$",
        citation_redirector,
        name="citation_redirector",
    ),
    url(
        r"^c/(?P<reporter>.*)/$",
        citation_redirector,
        name="citation_redirector",
    ),
    # Admin tools
    url(r"^admin-tools/block-item/$", block_item, name="block_item"),
]
