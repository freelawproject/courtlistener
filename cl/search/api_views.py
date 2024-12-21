from http import HTTPStatus

import waffle
from django.db.models import Prefetch
from rest_framework import pagination, permissions, response, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly

from cl.api.api_permissions import V3APIPermission
from cl.api.pagination import ESCursorPagination
from cl.api.utils import CacheListMixin, LoggingMixin, RECAPUsersReadOnly
from cl.lib.elasticsearch_utils import do_es_api_query
from cl.search import api_utils
from cl.search.api_serializers import (
    CourtSerializer,
    DocketEntrySerializer,
    DocketESResultSerializer,
    DocketSerializer,
    ExtendedPersonESSerializer,
    OAESResultSerializer,
    OpinionClusterESResultSerializer,
    OpinionClusterSerializer,
    OpinionsCitedSerializer,
    OpinionSerializer,
    OriginalCourtInformationSerializer,
    PersonESResultSerializer,
    RECAPDocumentESResultSerializer,
    RECAPDocumentSerializer,
    RECAPESResultSerializer,
    TagSerializer,
    V3OAESResultSerializer,
    V3OpinionESResultSerializer,
    V3RECAPDocumentESResultSerializer,
)
from cl.search.constants import SEARCH_HL_TAG
from cl.search.documents import (
    AudioDocument,
    DocketDocument,
    OpinionClusterDocument,
    PersonDocument,
)
from cl.search.filters import (
    CourtFilter,
    DocketEntryFilter,
    DocketFilter,
    OpinionClusterFilter,
    OpinionFilter,
    OpinionsCitedFilter,
    RECAPDocumentFilter,
)
from cl.search.forms import SearchForm
from cl.search.models import (
    SEARCH_TYPES,
    Court,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    OriginatingCourtInformation,
    RECAPDocument,
    Tag,
)


class OriginatingCourtInformationViewSet(viewsets.ModelViewSet):
    serializer_class = OriginalCourtInformationSerializer
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]
    queryset = OriginatingCourtInformation.objects.all().order_by("-id")


class DocketViewSet(LoggingMixin, viewsets.ModelViewSet):
    serializer_class = DocketSerializer
    filterset_class = DocketFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "date_blocked",
        "date_filed",
        "date_terminated",
        "date_last_filing",
    )
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]
    queryset = (
        Docket.objects.select_related(
            "court",
            "assigned_to",
            "referred_to",
            "originating_court_information",
            "idb_data",
        )
        .prefetch_related("panel", "clusters", "audio_files", "tags")
        .order_by("-id")
    )


class DocketEntryViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (RECAPUsersReadOnly, V3APIPermission)
    serializer_class = DocketEntrySerializer
    filterset_class = DocketEntryFilter
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "date_filed",
        "recap_sequence_number",
        "entry_number",
    )
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]
    queryset = (
        DocketEntry.objects.select_related(
            "docket",  # For links back to dockets
        )
        .prefetch_related(
            "recap_documents",  # Sub items
            "recap_documents__tags",  # Sub-sub items
            "tags",  # Tags on docket entries
        )
        .order_by("-id")
    )


class RECAPDocumentViewSet(
    LoggingMixin, CacheListMixin, viewsets.ModelViewSet
):
    permission_classes = (RECAPUsersReadOnly, V3APIPermission)
    serializer_class = RECAPDocumentSerializer
    filterset_class = RECAPDocumentFilter
    ordering_fields = ("id", "date_created", "date_modified", "date_upload")
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]
    queryset = (
        RECAPDocument.objects.select_related(
            "docket_entry", "docket_entry__docket"
        )
        .prefetch_related("tags")
        .order_by("-id")
    )


class CourtViewSet(LoggingMixin, viewsets.ModelViewSet):
    serializer_class = CourtSerializer
    filterset_class = CourtFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = (
        "id",
        "date_modified",
        "position",
        "start_date",
        "end_date",
    )
    queryset = Court.objects.exclude(
        jurisdiction=Court.TESTING_COURT
    ).order_by("position")
    # Our default pagination blocks deep pagination by overriding
    # PageNumberPagination. Allow deep pagination, by overriding our default
    # with this base class.
    pagination_class = PageNumberPagination


class OpinionClusterViewSet(LoggingMixin, viewsets.ModelViewSet):
    serializer_class = OpinionClusterSerializer
    filterset_class = OpinionClusterFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "date_filed",
        "citation_count",
        "date_blocked",
    )
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]
    queryset = OpinionCluster.objects.prefetch_related(
        Prefetch(
            "sub_opinions", queryset=Opinion.objects.order_by("ordering_key")
        ),
        "panel",
        "non_participating_judges",
        "citations",
    ).order_by("-id")


class OpinionViewSet(LoggingMixin, viewsets.ModelViewSet):
    serializer_class = OpinionSerializer
    filterset_class = OpinionFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
    )
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]
    queryset = (
        Opinion.objects.select_related("cluster", "author")
        .prefetch_related("opinions_cited", "joined_by")
        .order_by("-id")
    )


class OpinionsCitedViewSet(LoggingMixin, viewsets.ModelViewSet):
    serializer_class = OpinionsCitedSerializer
    filterset_class = OpinionsCitedFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = ["id"]
    queryset = OpinionsCited.objects.all().order_by("-id")


class TagViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (RECAPUsersReadOnly, V3APIPermission)
    serializer_class = TagSerializer
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]
    queryset = Tag.objects.all().order_by("-id")


class SearchViewSet(LoggingMixin, viewsets.ViewSet):
    # Default permissions use Django permissions, so here we AllowAny,
    # but folks will need to log in to get past the thresholds.
    permission_classes = (permissions.AllowAny, V3APIPermission)

    def list(self, request, *args, **kwargs):
        search_form = SearchForm(request.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            search_type = cd["type"]
            paginator = pagination.PageNumberPagination()
            sl = api_utils.get_object_list(
                request,
                cd=cd,
                paginator=paginator,
            )
            result_page = paginator.paginate_queryset(sl, request)
            match search_type:
                case SEARCH_TYPES.ORAL_ARGUMENT:
                    serializer = V3OAESResultSerializer(result_page, many=True)
                case SEARCH_TYPES.PEOPLE:
                    serializer = ExtendedPersonESSerializer(
                        result_page, many=True
                    )
                case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
                    serializer = V3RECAPDocumentESResultSerializer(
                        result_page, many=True
                    )
                case _:
                    # Default to Opinion type.
                    serializer = V3OpinionESResultSerializer(
                        result_page, many=True
                    )

            return paginator.get_paginated_response(serializer.data)
        # Invalid search.
        return response.Response(
            search_form.errors, status=HTTPStatus.BAD_REQUEST
        )


class SearchV4ViewSet(LoggingMixin, viewsets.ViewSet):
    # Default permissions use Django permissions, so here we AllowAny,
    # but folks will need to log in to get past the thresholds.
    permission_classes = (permissions.AllowAny,)

    supported_search_types = {
        SEARCH_TYPES.RECAP: {
            "document_class": DocketDocument,
            "serializer_class": RECAPESResultSerializer,
        },
        SEARCH_TYPES.DOCKETS: {
            "document_class": DocketDocument,
            "serializer_class": DocketESResultSerializer,
        },
        SEARCH_TYPES.RECAP_DOCUMENT: {
            "document_class": DocketDocument,
            "serializer_class": RECAPDocumentESResultSerializer,
        },
        SEARCH_TYPES.OPINION: {
            "document_class": OpinionClusterDocument,
            "serializer_class": OpinionClusterESResultSerializer,
        },
        SEARCH_TYPES.PEOPLE: {
            "document_class": PersonDocument,
            "serializer_class": PersonESResultSerializer,
        },
        SEARCH_TYPES.ORAL_ARGUMENT: {
            "document_class": AudioDocument,
            "serializer_class": OAESResultSerializer,
        },
    }

    def list(self, request, *args, **kwargs):
        search_form = SearchForm(request.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            search_type = cd["type"]

            supported_search_type = self.supported_search_types.get(
                search_type
            )
            if not supported_search_type:
                raise NotFound(
                    detail="Search type not found or not supported."
                )
            search_query = supported_search_type["document_class"].search()

            paginator = ESCursorPagination()
            cd["request_date"] = paginator.initialize_context_from_request(
                request, search_type
            )
            highlighting_fields = {}
            main_query, child_docs_query = do_es_api_query(
                search_query,
                cd,
                highlighting_fields,
                SEARCH_HL_TAG,
                request.version,
            )
            es_list_instance = api_utils.CursorESList(
                main_query, child_docs_query, None, None, cd, request
            )
            results_page = paginator.paginate_queryset(
                es_list_instance, request
            )

            # Avoid displaying the extra document used to determine if more
            # documents remain.
            results_page = api_utils.limit_api_results_to_page(
                results_page, paginator.cursor
            )

            serializer_class = supported_search_type["serializer_class"]
            serializer = serializer_class(results_page, many=True)
            return paginator.get_paginated_response(serializer.data)
        # Invalid search.
        return response.Response(
            search_form.errors, status=HTTPStatus.BAD_REQUEST
        )
