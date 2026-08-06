from django.urls import include, path, re_path
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter

from cl.alerts import api_views as alert_views
from cl.api import views
from cl.api.wiki_redirects import wiki_redirect_urlpatterns
from cl.audio import api_views as audio_views
from cl.citations import api_views as citations_views
from cl.disclosures import api_views as disclosure_views
from cl.donate import api_views as donate_views
from cl.favorites import api_views as favorite_views
from cl.people_db import api_views as people_views
from cl.recap import views as recap_views
from cl.scrapers import views as scraper_views
from cl.search import api_views as search_views
from cl.visualizations import api_views as viz_views

router = DefaultRouter()
# Search & Audio
router.register(r"dockets", search_views.DocketViewSet, basename="docket")
router.register(
    r"bankruptcy-information",
    search_views.BankruptcyInformationViewSet,
    basename="bankruptcyinformation",
)
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
router.register(
    r"opinions-cited-by-recap-document",
    search_views.OpinionsCitedByRECAPDocumentViewSet,
    basename="opinionscitedbyrecapdocument",
)
router.register(r"search", search_views.SearchViewSet, basename="search")
router.register(r"tag", search_views.TagViewSet, basename="tag")

# People & Entities
router.register(r"people", people_views.PersonViewSet, basename="person")
router.register(
    r"positions", people_views.PositionViewSet, basename="position"
)
router.register(
    r"retention-events",
    people_views.RetentionEventViewSet,
    basename="retentionevent",
)
router.register(
    r"educations", people_views.EducationViewSet, basename="education"
)
router.register(r"schools", people_views.SchoolViewSet, basename="school")
router.register(
    r"political-affiliations",
    people_views.PoliticalAffiliationViewSet,
    basename="politicalaffiliation",
)
router.register(r"sources", people_views.SourceViewSet, basename="source")
router.register(
    r"aba-ratings", people_views.ABARatingViewSet, basename="abarating"
)
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

# Scrapers
router.register(
    r"scrapers/scotus-email",
    scraper_views.ScraperSCOTUSEmailEndpoint,
    basename="scotus-email",
)

# Tags
router.register(r"tags", favorite_views.UserTagViewSet, basename="UserTag")
router.register(
    r"docket-tags", favorite_views.DocketTagViewSet, basename="DocketTag"
)

# State content
router.register(
    r"state/(?P<state>\w{2})/(?P<site>[^/]+)/alerts",
    scraper_views.StateEmailEndpoint,
    basename="StateEmail",
)

# Prayers
router.register(r"prayers", favorite_views.PrayerViewSet, basename="prayer")

# Increment events
router.register(
    r"increment-event",
    favorite_views.EventCounterViewset,
    basename="increment-event",
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

for prefix, viewset, basename in router.registry:
    # Register all the URLs from the v3 router into the v4 router except for
    # the "search" route.
    if basename != "search":
        router_v4.register(prefix, viewset, basename)

# When we finally need to deprecate V3 of the API, the process to remove it, is:
# - Remove the re_path(r"^api/rest/(?P<version>[v3]+)/", include(router.urls)) below
# - The only ViewSet that requires removal is SearchViewSet and its related
# helper methods should also be removed.
# - Remove all references to "v3" in the code and tests and simplify them
# accordingly, as no need to apply conditions based on the V3 API version.
# - Remove V3 documentation.
urlpatterns = [
    path(
        "api-auth/",
        include("rest_framework.urls", namespace="rest_framework"),
    ),
    re_path(r"^api/rest/(?P<version>[v3]+)/", include(router.urls)),
    re_path(r"^api/rest/(?P<version>[v4]+)/", include(router_v4.urls)),
    path("help/api/jurisdictions/", views.court_index, name="court_index"),
    # Live API endpoints
    path("api/rest/v4/wiki-data/", views.wiki_data, name="wiki_data"),
    re_path(
        r"^api/rest/v4/coverage/opinions/",
        views.coverage_data_opinions,
        name="coverage_data_opinions",
    ),
    re_path(
        r"^api/rest/v(?P<version>[1234])/coverage/(?P<court>.+)/$",
        views.coverage_data,
        name="coverage_data",
    ),
    re_path(
        r"^api/rest/v(?P<version>[1234])/alert-frequency/(?P<day_count>\d+)/$",
        views.get_result_count,
        name="alert_frequency",
    ),
    # Deprecation Dates:
    # v1: 2016-04-01
    # v2: 2016-04-01
    re_path(
        r"^api/rest/v(?P<v>[12])/.*",
        views.deprecated_api,
        name="deprecated_api",
    ),
    # Legacy redirect (still points to a local view)
    path(
        "api/jurisdictions/",
        RedirectView.as_view(pattern_name="court_index", permanent=True),
    ),
    # 301 redirects to wiki.free.law (see wiki_redirects.py)
    *wiki_redirect_urlpatterns,
]
