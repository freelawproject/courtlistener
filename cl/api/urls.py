from django.conf.urls import url, include
from rest_framework.routers import DefaultRouter
from rest_framework.schemas import get_schema_view
from rest_framework_swagger.renderers import OpenAPIRenderer, SwaggerUIRenderer
from rest_framework.renderers import JSONOpenAPIRenderer
from cl.api import views
from cl.audio import api_views as audio_views
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

API_TITLE = "CourtListener Legal Data API"
schema_view = get_schema_view(
    title=API_TITLE,
    url="https://www.courtlistener.com/api/rest/v3/",
    renderer_classes=[JSONOpenAPIRenderer],
)


urlpatterns = [
    url(
        r"^api-auth/",
        include("rest_framework.urls", namespace="rest_framework"),
    ),
    url(r"^api/rest/(?P<version>[v3]+)/", include(router.urls)),
    # Schemas
    url(
        "^api/schema/$",
        views.deprecated_api,
        name="deprecated_core_api_schema",
    ),
    url("^api/swagger/$", schema_view, name="swagger_schema"),
    # Documentation
    url(r"^api/$", views.api_index, name="api_index"),
    url(r"^api/jurisdictions/$", views.court_index, name="court_index"),
    url(
        r"^api/rest-info/(?P<version>v[123])?/?$",
        views.rest_docs,
        name="rest_docs",
    ),
    url(r"^api/bulk-info/$", views.bulk_data_index, name="bulk_data_index"),
    url(
        r"^api/replication/$", views.replication_docs, name="replication_docs"
    ),
    url(
        r"^api/replication/status/$",
        views.replication_status,
        name="replication_status",
    ),
    url(
        r"^api/rest/v(?P<version>[123])/coverage/(?P<court>.+)/$",
        views.coverage_data,
        name="coverage_data",
    ),
    url(
        r"^api/rest/v(?P<version>[123])/alert-frequency/(?P<day_count>\d+)/$",
        views.get_result_count,
        name="alert_frequency",
    ),
    # Deprecation Dates:
    # v1: 2016-04-01
    # v2: 2016-04-01
    url(
        r"^api/rest/v(?P<v>[12])/.*",
        views.deprecated_api,
        name="deprecated_api",
    ),
]
