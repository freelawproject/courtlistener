from django.urls import path, re_path

from cl.opinion_page.views import (
    block_item,
    citation_homepage,
    citation_redirector,
    cluster_visualizations,
    court_homepage,
    court_publish_page,
    docket_idb_data,
    redirect_docket_recap,
    redirect_og_lookup,
    view_authorities,
    view_docket,
    view_docket_feed,
    view_opinion,
    view_parties,
    view_recap_document,
    view_summaries,
)

urlpatterns = [
    # Court pages
    path("court/<str:pk>/", court_homepage, name="court_homepage"),
    path(
        "court/<str:pk>/new-opinion/",
        court_publish_page,
        name="court_publish_page",
    ),
    # Opinion pages
    path(
        "opinion/<int:pk>/<blank-slug:slug>/summaries/",
        view_summaries,
        name="view_summaries",
    ),
    path(
        "opinion/<int:pk>/<blank-slug:slug>/authorities/",
        view_authorities,
        name="view_authorities",
    ),
    path(
        "opinion/<int:pk>/<blank-slug:slug>/visualizations/",
        cluster_visualizations,
        name="cluster_visualizations",
    ),
    path(
        "docket/<int:docket_id>/feed/",
        view_docket_feed,
        name="docket_feed",
    ),
    path("opinion/<int:pk>/<blank-slug:_>/", view_opinion, name="view_case"),
    path(
        "docket/<int:pk>/<blank-slug:slug>/", view_docket, name="view_docket"  # type: ignore[arg-type]
    ),
    path(
        "recap/gov.uscourts.<str:court>.<str:pacer_case_id>/",
        redirect_docket_recap,  # type: ignore[arg-type]
        name="redirect_docket_recap",
    ),
    path(
        "recap/og-lookup/",
        redirect_og_lookup,
        name="redirect_og_lookup",
    ),
    path(
        "docket/<int:docket_id>/parties/<blank-slug:slug>/",
        view_parties,
        name="docket_parties",
    ),
    path(
        "docket/<int:docket_id>/idb/<blank-slug:slug>/",
        docket_idb_data,
        name="docket_idb_data",
    ),
    path(
        "docket/<int:docket_id>/<str:doc_num>/<blank-slug:slug>/",
        view_recap_document,
        name="view_recap_document",
    ),
    path(
        "docket/<int:docket_id>/<str:doc_num>/<int:att_num>/<blank-slug:slug>/",
        view_recap_document,
        name="view_recap_attachment",
    ),
    # Citation look up pages
    path(
        "c/",
        citation_homepage,
        name="citation_homepage",
    ),
    re_path(
        r"^c/(?:(?P<reporter>.*)/(?P<volume>\d{1,10})/(?P<page>.*)/)?$",
        citation_redirector,
        name="citation_redirector",
    ),
    re_path(
        r"^c/(?P<reporter>.*)/(?P<volume>\d{1,10})/$",
        citation_redirector,
        name="citation_redirector",
    ),
    path(
        "c/<str:reporter>/",
        citation_redirector,
        name="citation_redirector",
    ),
    # Admin tools
    path("admin-tools/block-item/", block_item, name="block_item"),
]
