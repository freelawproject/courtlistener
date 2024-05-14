from http import HTTPStatus

import waffle
from rest_framework import pagination, permissions, response, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination

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
    RECAPDocumentESResultSerializer,
    RECAPDocumentSerializer,
    RECAPESResultSerializer,
    SearchResultSerializer,
    TagSerializer,
    V3OpinionESResultSerializer,
)
from cl.search.constants import SEARCH_HL_TAG
from cl.search.documents import DocketDocument, OpinionClusterDocument
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
    queryset = OriginatingCourtInformation.objects.all().order_by("-id")


class DocketViewSet(LoggingMixin, viewsets.ModelViewSet):
    serializer_class = DocketSerializer
    filterset_class = DocketFilter
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "date_blocked",
        "date_filed",
        "date_terminated",
        "date_last_filing",
    )
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
    permission_classes = (RECAPUsersReadOnly,)
    serializer_class = DocketEntrySerializer
    filterset_class = DocketEntryFilter
    ordering_fields = ("id", "date_created", "date_modified", "date_filed")

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
    permission_classes = (RECAPUsersReadOnly,)
    serializer_class = RECAPDocumentSerializer
    filterset_class = RECAPDocumentFilter
    ordering_fields = ("id", "date_created", "date_modified", "date_upload")
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
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "date_filed",
        "citation_count",
        "date_blocked",
    )
    queryset = OpinionCluster.objects.prefetch_related(
        "sub_opinions", "panel", "non_participating_judges", "citations"
    ).order_by("-id")


class OpinionViewSet(LoggingMixin, viewsets.ModelViewSet):
    serializer_class = OpinionSerializer
    filterset_class = OpinionFilter
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
    )
    queryset = (
        Opinion.objects.select_related("cluster", "author")
        .prefetch_related("opinions_cited", "joined_by")
        .order_by("-id")
    )


class OpinionsCitedViewSet(LoggingMixin, viewsets.ModelViewSet):
    serializer_class = OpinionsCitedSerializer
    filterset_class = OpinionsCitedFilter
    queryset = OpinionsCited.objects.all().order_by("-id")


class TagViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (RECAPUsersReadOnly,)
    serializer_class = TagSerializer
    queryset = Tag.objects.all().order_by("-id")


class SearchViewSet(LoggingMixin, viewsets.ViewSet):
    # Default permissions use Django permissions, so here we AllowAny,
    # but folks will need to log in to get past the thresholds.
    permission_classes = (permissions.AllowAny,)

    def list(self, request, *args, **kwargs):

        is_opinion_active = waffle.flag_is_active(
            request, "o-es-search-api-active"
        )
        search_form = SearchForm(request.GET, is_es_form=is_opinion_active)
        if search_form.is_valid():
            cd = search_form.cleaned_data

            search_type = cd["type"]
            paginator = pagination.PageNumberPagination()
            sl = api_utils.get_object_list(request, cd=cd, paginator=paginator)
            result_page = paginator.paginate_queryset(sl, request)
            if (
                search_type == SEARCH_TYPES.ORAL_ARGUMENT
                and waffle.flag_is_active(request, "oa-es-active")
            ):
                serializer = OAESResultSerializer(result_page, many=True)
            elif search_type == SEARCH_TYPES.PEOPLE and waffle.flag_is_active(
                request, "p-es-active"
            ):
                serializer = ExtendedPersonESSerializer(result_page, many=True)
            elif search_type == SEARCH_TYPES.OPINION and is_opinion_active:
                serializer = V3OpinionESResultSerializer(
                    result_page, many=True
                )
            else:
                if cd["q"] == "":
                    cd["q"] = "*"  # Get everything
                serializer = SearchResultSerializer(
                    result_page, many=True, context={"schema": sl.conn.schema}
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

    document_search_classes = {
        SEARCH_TYPES.RECAP: DocketDocument,
        SEARCH_TYPES.DOCKETS: DocketDocument,
        SEARCH_TYPES.RECAP_DOCUMENT: DocketDocument,
        SEARCH_TYPES.OPINION: OpinionClusterDocument,
    }

    def list(self, request, *args, **kwargs):
        search_form = SearchForm(request.GET, is_es_form=True)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            search_type = cd["type"]
            search_query = self.document_search_classes[search_type].search()
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
                main_query,
                child_docs_query,
                None,
                None,
                cd,
                version=request.version,
            )
            results_page = paginator.paginate_queryset(
                es_list_instance, request
            )

            # Avoid displaying the extra document used to determine if more
            # documents remain.
            results_page = api_utils.limit_api_results_to_page(
                results_page, paginator.cursor
            )

            match search_type:
                case SEARCH_TYPES.RECAP:
                    serializer = RECAPESResultSerializer(
                        results_page, many=True
                    )
                case SEARCH_TYPES.DOCKETS:
                    serializer = DocketESResultSerializer(
                        results_page, many=True
                    )
                case SEARCH_TYPES.RECAP_DOCUMENT:
                    serializer = RECAPDocumentESResultSerializer(
                        results_page, many=True
                    )
                case SEARCH_TYPES.OPINION:
                    serializer = OpinionClusterESResultSerializer(
                        results_page, many=True
                    )
                case _:
                    # Not found error
                    raise NotFound(
                        detail="Search type not found or not supported."
                    )
            return paginator.get_paginated_response(serializer.data)
        # Invalid search.
        return response.Response(
            search_form.errors, status=HTTPStatus.BAD_REQUEST
        )
