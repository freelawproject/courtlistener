from django.urls import include, path, re_path
from django.views.generic import RedirectView, TemplateView
from rest_framework.routers import DefaultRouter

from cl.alerts import api_views as alert_views
from cl.api import views
from cl.audio import api_views as audio_views
from cl.citations import api_views as citations_views
from cl.disclosures import api_views as disclosure_views
from cl.donate import api_views as donate_views
from cl.favorites import api_views as favorite_views
from cl.people_db import api_views as people_views
from cl.recap import views as recap_views
from cl.search import api_views as search_views
from cl.visualizations import api_views as viz_views

router = DefaultRouter()
# Search & Audio
router.register(r"dockets", search_views.DocketViewSet, basename="docket")
router.register(
    r"originating-court-information",
    search_views.OriginatingCourtInformationViewSet,
    basename="originatingcourtinformation",
)
router.register(
    r"docket-entries", search_views.DocketEntryViewSet, basename="docketentry"
)
router.register(
    r"recap-documents",
    search_views.RECAPDocumentViewSet,
    basename="recapdocument",
)
router.register(r"courts", search_views.CourtViewSet, basename="court")
router.register(r"audio", audio_views.AudioViewSet, basename="audio")
router.register(
    r"clusters", search_views.OpinionClusterViewSet, basename="opinioncluster"
)
router.register(r"opinions", search_views.OpinionViewSet, basename="opinion")
router.register(
    r"opinions-cited",
    search_views.OpinionsCitedViewSet,
    basename="opinionscited",
)
router.register(r"search", search_views.SearchViewSet, basename="search")
router.register(r"tag", search_views.TagViewSet, basename="tag")

# People & Entities
router.register(r"people", people_views.PersonViewSet)
router.register(
    r"disclosure-typeahead",
    people_views.PersonDisclosureViewSet,
    basename="disclosuretypeahead",
)
router.register(r"positions", people_views.PositionViewSet)
router.register(r"retention-events", people_views.RetentionEventViewSet)
router.register(r"educations", people_views.EducationViewSet)
router.register(r"schools", people_views.SchoolViewSet)
router.register(
    r"political-affiliations", people_views.PoliticalAffiliationViewSet
)
router.register(r"sources", people_views.SourceViewSet)
router.register(r"aba-ratings", people_views.ABARatingViewSet)
router.register(r"parties", people_views.PartyViewSet, basename="party")
router.register(
    r"attorneys", people_views.AttorneyViewSet, basename="attorney"
)

# RECAP
router.register(r"recap", recap_views.PacerProcessingQueueViewSet)
router.register(r"recap-email", recap_views.EmailProcessingQueueViewSet)
router.register(r"recap-fetch", recap_views.PacerFetchRequestViewSet)
router.register(
    r"recap-query",
    recap_views.PacerDocIdLookupViewSet,
    basename="fast-recapdocument",
)
router.register(
    r"fjc-integrated-database", recap_views.FjcIntegratedDatabaseViewSet
)

# Tags
router.register(r"tags", favorite_views.UserTagViewSet, basename="UserTag")
router.register(
    r"docket-tags", favorite_views.DocketTagViewSet, basename="DocketTag"
)

# Visualizations
router.register(
    r"visualizations/json", viz_views.JSONViewSet, basename="jsonversion"
)
router.register(
    r"visualizations", viz_views.VisualizationViewSet, basename="scotusmap"
)

# Financial Disclosures
router.register(
    r"agreements",
    disclosure_views.AgreementViewSet,
    basename="agreement",
)
router.register(r"debts", disclosure_views.DebtViewSet, basename="debt")
router.register(
    r"financial-disclosures",
    disclosure_views.FinancialDisclosureViewSet,
    basename="financialdisclosure",
)
router.register(r"gifts", disclosure_views.GiftViewSet, basename="gift")
router.register(
    r"investments", disclosure_views.InvestmentViewSet, basename="investment"
)
router.register(
    r"non-investment-incomes",
    disclosure_views.NonInvestmentIncomeViewSet,
    basename="noninvestmentincome",
)
router.register(
    r"disclosure-positions",
    disclosure_views.PositionViewSet,
    basename="disclosureposition",
)
router.register(
    r"reimbursements",
    disclosure_views.ReimbursementViewSet,
    basename="reimbursement",
)
router.register(
    r"spouse-incomes",
    disclosure_views.SpouseIncomeViewSet,
    basename="spouseincome",
)

# Search Alerts
router.register(r"alerts", alert_views.SearchAlertViewSet, basename="alert")

# DocketAlerts
router.register(
    r"docket-alerts", alert_views.DocketAlertViewSet, basename="docket-alert"
)

# Neon webhooks
router.register(
    r"memberships",
    donate_views.MembershipWebhookViewSet,
    basename="membership-webhooks",
)

# Citation lookups
router.register(
    r"citation-lookup",
    citations_views.CitationLookupViewSet,
    basename="citation-lookup",
)

API_TITLE = "CourtListener Legal Data API"


# Version 4 Router
router_v4 = DefaultRouter()
router_v4.register(r"search", search_views.SearchV4ViewSet, basename="search")


urlpatterns = [
    path(
        "api-auth/",
        include("rest_framework.urls", namespace="rest_framework"),
    ),
    re_path(r"^api/rest/(?P<version>[v3]+)/", include(router.urls)),
    re_path(r"^api/rest/(?P<version>[v4]+)/", include(router_v4.urls)),
    # Documentation
    path("help/api/", views.api_index, name="api_index"),
    path("help/api/jurisdictions/", views.court_index, name="court_index"),
    re_path(
        r"^help/api/rest/(?P<version>v[123])?/?$",
        views.rest_docs,
        name="rest_docs",
    ),
    path(
        "help/api/rest/v3/citation-lookup/",
        views.citation_lookup_api,
        name="citation_lookup_api",
    ),
    path(
        "help/api/rest/v3/case-law/",
        TemplateView.as_view(
            template_name="case-law-api-docs-vlatest.html",
            extra_context={"private": False},
        ),
        name="case_law_api_help",
    ),
    path(
        "help/api/rest/v3/citations/",
        TemplateView.as_view(
            template_name="citation-api-docs-vlatest.html",
            extra_context={"private": False},
        ),
        name="citation_api_help",
    ),
    path(
        "help/api/rest/v3/pacer/",
        TemplateView.as_view(
            template_name="pacer-api-docs-vlatest.html",
            extra_context={"private": False},
        ),
        name="pacer_api_help",
    ),
    path(
        "help/api/rest/v3/recap/",
        TemplateView.as_view(
            template_name="recap-api-docs-vlatest.html",
            extra_context={"private": False},
        ),
        name="recap_api_help",
    ),
    path(
        "help/api/rest/v3/judges/",
        TemplateView.as_view(
            template_name="judge-api-docs-vlatest.html",
            extra_context={"private": False},
        ),
        name="judge_api_help",
    ),
    path(
        "help/api/rest/v3/oral-arguments/",
        TemplateView.as_view(
            template_name="oral-argument-api-docs-vlatest.html",
            extra_context={"private": False},
        ),
        name="oral_argument_api_help",
    ),
    path(
        "help/api/rest/v3/visualizations/",
        TemplateView.as_view(
            template_name="visualizations-api-docs-vlatest.html",
            extra_context={"private": False},
        ),
        name="visualization_api_help",
    ),
    path(
        "help/api/rest/v3/financial-disclosures/",
        TemplateView.as_view(
                         #"financial-disclosure-docs-vlatest.html"
            template_name="financial-disclosure-api-docs-vlatest.html",
            extra_context={"private": False},
        ),
        name="financial_disclosures_api_help",
    ),
    path(
        "help/api/rest/v3/search/",
        TemplateView.as_view(
            template_name="search-api-docs-vlatest.html",
            extra_context={"private": False},
        ),
        name="search_api_help",
    ),
    path(
        "help/api/rest/v3/alerts/",
        TemplateView.as_view(
            template_name="alert-api-docs-vlatest.html",
            extra_context={"private": False},
        ),
        name="alert_api_help",
    ),
    path(
        "help/api/rest/v3/fields/",
        TemplateView.as_view(
            template_name="field-help.html",
            extra_context={"private": True},
        ),
        name="field_api_help",
    ),
    path(
        "help/api/rest/changes/",
        TemplateView.as_view(
            template_name="rest-change-log.html",
            extra_context={"private": False},
        ),
        name="rest_change_log",
    ),
    path("help/api/bulk-data/", views.bulk_data_index, name="bulk_data_index"),
    path(
        "help/api/replication/",
        TemplateView.as_view(
            template_name="replication.html",
            extra_context={"private": False},
        ),
        name="replication_docs",
    ),
    re_path(
        r"^api/rest/v(?P<version>[123])/coverage/(?P<court>.+)/$",
        views.coverage_data,
        name="coverage_data",
    ),
    re_path(
        r"^api/rest/v4/coverage/opinions/",
        views.coverage_data_opinions,
        name="coverage_data_opinions",
    ),
    re_path(
        r"^api/rest/v(?P<version>[123])/alert-frequency/(?P<day_count>\d+)/$",
        views.get_result_count,
        name="alert_frequency",
    ),
    # Webhooks Documentation
    path(
        "help/api/webhooks/getting-started/",
        TemplateView.as_view(
            template_name="webhooks-getting-started.html",
            extra_context={"private": False},
        ),
        name="webhooks_getting_started",
    ),
    re_path(
        r"^help/api/webhooks/(?P<version>v[123])?/?$",
        views.webhooks_docs,
        name="webhooks_docs",
    ),
    # Deprecation Dates:
    # v1: 2016-04-01
    # v2: 2016-04-01
    re_path(
        r"^api/rest/v(?P<v>[12])/.*",
        views.deprecated_api,
        name="deprecated_api",
    ),
    # Redirect api docs from /api/* to /help/api/*
    # Started: 2022-12-05
    re_path(
        r"^api/rest-info/(?P<version>v[123])?/?$",
        RedirectView.as_view(pattern_name="rest_docs", permanent=True),
    ),
    path(
        "api/",
        RedirectView.as_view(pattern_name="api_index", permanent=True),
    ),
    path(
        "api/jurisdictions/",
        RedirectView.as_view(pattern_name="court_index", permanent=True),
    ),
    path(
        "api/bulk-info/",
        RedirectView.as_view(pattern_name="bulk_data_index", permanent=True),
    ),
    path(
        "api/replication/",
        RedirectView.as_view(pattern_name="replication_docs", permanent=True),
    ),
]
