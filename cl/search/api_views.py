from cl.lib import api
from cl.search.models import Docket, Court, OpinionCluster, Opinion
from cl.search.forms import SearchForm
from cl.search.filters import (
    DocketFilter, CourtFilter, OpinionClusterFilter, OpinionFilter
)
from cl.search.serializers import (
    DocketSerializer, CourtSerializer, OpinionClusterSerializer,
    OpinionSerializer, SearchResultSerializer,
)
from rest_framework import status, pagination, viewsets, permissions, response


class DocketViewSet(viewsets.ModelViewSet):
    queryset = Docket.objects.all()
    serializer_class = DocketSerializer
    filter_class = DocketFilter


class CourtViewSet(viewsets.ModelViewSet):
    queryset = Court.objects.exclude(jurisdiction='T')
    serializer_class = CourtSerializer
    filter_class = CourtFilter


class OpinionClusterViewSet(viewsets.ModelViewSet):
    queryset = OpinionCluster.objects.all()
    serializer_class = OpinionClusterSerializer
    filter_class = OpinionClusterFilter


class OpinionViewSet(viewsets.ModelViewSet):
    queryset = Opinion.objects.all()
    serializer_class = OpinionSerializer
    filter_class = OpinionFilter


class SearchViewSet(viewsets.ViewSet):
    # Default permissions use Django permissions, so here we AllowAny, but folks
    # will need to log in to get past the thresholds.
    permission_classes = (permissions.AllowAny,)

    def list(self, request, *args, **kwargs):
        search_form = SearchForm(request.GET)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            if cd['q'] == '':
                cd['q'] = '*:*'  # Get everything

            paginator = pagination.PageNumberPagination()
            sl = api.get_object_list(request, cd=cd, paginator=paginator)

            result_page = paginator.paginate_queryset(sl, request)
            serializer = SearchResultSerializer(
                result_page,
                many=True,
                context={'schema': sl.conn.schema}
            )
            return paginator.get_paginated_response(serializer.data)

        # Invalid search.
        return response.Response(
            serializers.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
