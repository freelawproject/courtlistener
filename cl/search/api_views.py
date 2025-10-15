from http import HTTPStatus

from django.db.models import Prefetch
from django.http.response import Http404
from django.urls import reverse
from rest_framework import pagination, permissions, response, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import (
    DjangoModelPermissions,
    DjangoModelPermissionsOrAnonReadOnly,
)
from rest_framework.renderers import BrowsableAPIRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from waffle import flag_is_active

from cl.api.api_permissions import V3APIPermission
from cl.api.pagination import ESCursorPagination
from cl.api.utils import (
    DeferredFieldsMixin,
    LoggingMixin,
    NoFilterCacheListMixin,
    RECAPUsersReadOnly,
)
from cl.lib.elasticsearch_utils import do_es_api_query
from cl.search import api_utils
from cl.search.api_renderers import SafeXMLRenderer
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
    VectorSerializer,
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
    ClusterRedirection,
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


class OriginatingCourtInformationViewSet(
    DeferredFieldsMixin, viewsets.ModelViewSet
):
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


class DocketViewSet(
    LoggingMixin,
    NoFilterCacheListMixin,
    DeferredFieldsMixin,
    viewsets.ModelViewSet,
):
    serializer_class = DocketSerializer
    filterset_class = DocketFilter
    permission_classes = [
        DjangoModelPermissions,
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


class DocketEntryViewSet(
    LoggingMixin,
    NoFilterCacheListMixin,
    DeferredFieldsMixin,
    viewsets.ModelViewSet,
):
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
    LoggingMixin,
    NoFilterCacheListMixin,
    DeferredFieldsMixin,
    viewsets.ModelViewSet,
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


class CourtViewSet(LoggingMixin, DeferredFieldsMixin, viewsets.ModelViewSet):
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


class OpinionClusterViewSet(
    LoggingMixin,
    NoFilterCacheListMixin,
    DeferredFieldsMixin,
    viewsets.ModelViewSet,
):
    serializer_class = OpinionClusterSerializer
    filterset_class = OpinionClusterFilter
    permission_classes = [
        DjangoModelPermissions,
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

    def retrieve(self, request, *args, **kwargs):
        try:
            # First, try to get the object normally
            return super().retrieve(request, *args, **kwargs)
        except Http404 as exc:
            try:
                pk = kwargs.get("pk")
                redirection = ClusterRedirection.objects.get(
                    deleted_cluster_id=pk
                )
            except ClusterRedirection.DoesNotExist:
                raise exc

            if redirection.reason == ClusterRedirection.SEALED:
                message = dict(ClusterRedirection.REDIRECTION_REASON)[
                    ClusterRedirection.SEALED
                ]
                return Response({"detail": message}, status=HTTPStatus.GONE)

            cluster_id = redirection.cluster_id
            redirect_kwargs = kwargs.copy()
            redirect_kwargs["pk"] = cluster_id
            redirection_url = reverse(
                "opinioncluster-detail",
                kwargs=redirect_kwargs,
            )
            absolute_new_url = request.build_absolute_uri(redirection_url)

            return Response(
                status=HTTPStatus.MOVED_PERMANENTLY,
                headers={"Location": absolute_new_url},
            )


class OpinionViewSet(
    LoggingMixin,
    NoFilterCacheListMixin,
    DeferredFieldsMixin,
    viewsets.ModelViewSet,
):
    serializer_class = OpinionSerializer
    filterset_class = OpinionFilter
    permission_classes = [
        DjangoModelPermissions,
        V3APIPermission,
    ]
    # keep the order as in `settings.rest_framework.DEFAULT_RENDERER_CLASSES`
    # but using `SafeXMLRenderer` to handle invalid characters
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer, SafeXMLRenderer]
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
        .prefetch_related(
            "joined_by",
            Prefetch("opinions_cited", queryset=Opinion.objects.only("id")),
        )
        .order_by("-id")
    )


class OpinionsCitedViewSet(
    LoggingMixin,
    NoFilterCacheListMixin,
    DeferredFieldsMixin,
    viewsets.ModelViewSet,
):
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


class TagViewSet(LoggingMixin, DeferredFieldsMixin, viewsets.ModelViewSet):
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

    def execute_es_search(self, cleaned_data, request) -> Response:
        """
        Execute Elasticsearch search for the given cleaned data and request
        object.

        :param cleaned_data: Validated and cleaned data from the request query
            parameters.
        :param request: The request object.
        :return: Response object with paginated search results or validation
            errors.
        """
        search_type = cleaned_data["type"]
        supported_search_type = self.supported_search_types.get(search_type)
        if not supported_search_type:
            raise NotFound(detail="Search type not found or not supported.")
        search_query = supported_search_type["document_class"].search()

        paginator = ESCursorPagination()
        cleaned_data["request_date"] = (
            paginator.initialize_context_from_request(request, search_type)
        )
        highlighting_fields = {}
        main_query, child_docs_query = do_es_api_query(
            search_query,
            cleaned_data,
            highlighting_fields,
            SEARCH_HL_TAG,
            request.version,
        )
        es_list_instance = api_utils.CursorESList(
            main_query, child_docs_query, None, None, cleaned_data, request
        )
        results_page, cached_response = paginator.paginate_queryset(
            es_list_instance, request
        )

        # Avoid displaying the extra document used to determine if more
        # documents remain.
        results_page = api_utils.limit_api_results_to_page(
            results_page, paginator.cursor, cached_response
        )

        serializer_class = supported_search_type["serializer_class"]
        serializer = serializer_class(
            results_page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(
            serializer.data, cached_response
        )

    def list(self, request, *args, **kwargs):
        search_form = SearchForm(request.GET, request=request)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            return self.execute_es_search(cd, request)

        # Invalid search.
        return response.Response(
            search_form.errors, status=HTTPStatus.BAD_REQUEST
        )

    def create(self, request, *args, **kwargs):
        # Check if waffle flag is enabled for this account
        if not flag_is_active(request, "enable_semantic_search"):
            raise ValidationError(
                {
                    "non_field_errors": [
                        "This feature is currently disabled for your account."
                    ]
                }
            )

        # Validate query parameters (from URL) and request body (JSON)
        query_params = SearchForm(request.GET, request=request)
        request_body = VectorSerializer(data=request.data)
        if not all([query_params.is_valid(), request_body.is_valid()]):
            # Merge validation errors from both sources
            combined_errors = query_params.errors | request_body.errors
            return response.Response(
                combined_errors, status=HTTPStatus.BAD_REQUEST
            )

        # Extract validated data
        cd = query_params.cleaned_data
        data = request_body.validated_data
        # Restrict semantic search to supported types (currently only OPINION).
        if cd["type"] not in [SEARCH_TYPES.OPINION]:
            raise ValidationError(
                {
                    "type": [
                        f"Unsupported search type '{cd['type']}'. "
                        f"Semantic search is only supported for type '{SEARCH_TYPES.OPINION}'."
                    ]
                }
            )
        # Enforce semantic search flag in query params
        if not cd["semantic"]:
            raise ValidationError(
                {
                    "semantic": [
                        "Semantic search requires `semantic=true` in the query string."
                    ]
                }
            )
        # Ensure the request body includes a valid embedding/vector
        if not data:
            raise ValidationError(
                {
                    "embedding": [
                        (
                            "You must provide an embedding vector in the request body when "
                            "using semantic search."
                        )
                    ]
                }
            )

        # Attach embedding to query params and run the actual ES query
        cd["embedding"] = data["embedding"]
        return self.execute_es_search(cd, request)
