from django.urls import path, re_path

from cl.opinion_page.views import (
    block_item,
    citation_homepage,
    citation_redirector,
    court_homepage,
    court_publish_page,
    docket_authorities,
    docket_idb_data,
    download_docket_entries_csv,
    redirect_docket_recap,
    redirect_og_lookup,
    update_opinion_tabs,
    view_docket,
    view_docket_feed,
    view_opinion,
    view_opinion_authorities,
    view_opinion_cited_by,
    view_opinion_pdf,
    view_opinion_related_cases,
    view_opinion_summaries,
    view_parties,
    view_recap_authorities,
    view_recap_document,
)

urlpatterns = [
    # Court pages
    path("court/<str:pk>/", court_homepage, name="court_homepage"),  # type: ignore[arg-type]
    path(
        "court/<str:pk>/new-opinion/",
        court_publish_page,
        name="court_publish_page",
    ),
    # Opinion pages
    path(
        "docket/<int:docket_id>/feed/",
        view_docket_feed,  # type: ignore[arg-type]
        name="docket_feed",
    ),
    path(
        "opinion/update-tabs/<int:pk>/",
        update_opinion_tabs,
        name="update_opinion_tabs",
    ),
    path("opinion/<int:pk>/<blank-slug:_>/", view_opinion, name="view_case"),  # type: ignore[arg-type]
    path(
        "opinion/<int:pk>/<blank-slug:_>/authorities/",
        view_opinion_authorities,
        name="view_case_authorities",
    ),  # with the tab
    path(
        "opinion/<int:pk>/<blank-slug:_>/cited-by/",
        view_opinion_cited_by,
        name="view_case_cited_by",
    ),  # with the tab
    path(
        "opinion/<int:pk>/<blank-slug:_>/summaries/",
        view_opinion_summaries,
        name="view_case_summaries",
    ),  # with the tab
    path(
        "opinion/<int:pk>/<blank-slug:_>/related-cases/",
        view_opinion_related_cases,
        name="view_case_related_cases",
    ),  # with the tab
    path(
        "opinion/<int:pk>/<blank-slug:_>/pdf/",
        view_opinion_pdf,
        name="view_case_pdf",
    ),  # with the tab
    path(
        "docket/<int:docket_id>/download/",
        download_docket_entries_csv,  # type: ignore[arg-type]
        name="view_download_docket",
    ),
    path(
        "docket/<int:pk>/<blank-slug:slug>/",
        view_docket,
        name="view_docket",
        # type: ignore[arg-type]
    ),
    path(
        "recap/gov.uscourts.<str:court>.<str:pacer_case_id>/",
        redirect_docket_recap,  # type: ignore[arg-type]
        name="redirect_docket_recap",
    ),
    path(
        "recap/og-lookup/",
        redirect_og_lookup,  # type: ignore[arg-type]
        name="redirect_og_lookup",
    ),
    path(
        "docket/<int:docket_id>/parties/<blank-slug:slug>/",
        view_parties,  # type: ignore[arg-type]
        name="docket_parties",
    ),
    path(
        "docket/<int:docket_id>/idb/<blank-slug:slug>/",
        docket_idb_data,  # type: ignore[arg-type]
        name="docket_idb_data",
    ),
    path(
        "docket/<int:docket_id>/authorities/<blank-slug:slug>/",
        docket_authorities,  # type: ignore[arg-type]
        name="docket_authorities",
    ),
    path(
        "docket/<int:docket_id>/<str:doc_num>/<blank-slug:slug>/",
        view_recap_document,  # type: ignore[arg-type]
        name="view_recap_document",
    ),
    path(
        "docket/<int:docket_id>/<str:doc_num>/<blank-slug:slug>/authorities/",
        view_recap_authorities,  # type: ignore[arg-type]
        name="view_document_authorities",
    ),
    path(
        "docket/<int:docket_id>/<str:doc_num>/<int:att_num>/<blank-slug:slug>/",
        view_recap_document,  # type: ignore[arg-type]
        name="view_recap_attachment",
    ),
    path(
        "docket/<int:docket_id>/<str:doc_num>/<int:att_num>/<blank-slug:slug>/authorities/",
        view_recap_authorities,  # type: ignore[arg-type]
        name="view_attachment_authorities",
    ),
    # Citation look up pages
    path(
        "c/",
        citation_homepage,  # type: ignore[arg-type]
        name="citation_homepage",
    ),
    re_path(
        r"^c/(?:(?P<reporter>.*)/(?P<volume>\d{1,10})/(?P<page>.*)/)?$",
        citation_redirector,  # type: ignore[arg-type]
        name="citation_redirector",
    ),
    re_path(
        r"^c/(?P<reporter>.*)/(?P<volume>\d{1,10})/$",
        citation_redirector,  # type: ignore[arg-type]
        name="citation_redirector",
    ),
    path(
        "c/<str:reporter>/",
        citation_redirector,  # type: ignore[arg-type]
        name="citation_redirector",
    ),
    # Admin tools
    path("admin-tools/block-item/", block_item, name="block_item"),  # type: ignore[arg-type]
]
