from http import HTTPStatus

from asgiref.sync import async_to_sync
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from cl.api.api_permissions import IsOwner
from cl.api.utils import LoggingMixin
from cl.visualizations.api_permissions import IsParentVisualizationOwner
from cl.visualizations.api_serializers import (
    JSONVersionSerializer,
    VisualizationSerializer,
)
from cl.visualizations.models import JSONVersion, SCOTUSMap
from cl.visualizations.network_utils import reverse_endpoints_if_needed
from cl.visualizations.utils import build_visualization


class JSONViewSet(LoggingMixin, ModelViewSet):
    permission_classes = [IsAuthenticated, IsParentVisualizationOwner]
    serializer_class = JSONVersionSerializer
    ordering_fields = ("id", "date_created", "date_modified")

    def get_queryset(self):
        return JSONVersion.objects.filter(
            Q(map__user=self.request.user) | Q(map__published=True)
        ).order_by("-id")


class VisualizationViewSet(LoggingMixin, ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = VisualizationSerializer
    ordering_fields = ("id", "date_created", "date_modified", "user")

    def get_queryset(self):
        return SCOTUSMap.objects.filter(
            Q(user=self.request.user) | Q(published=True)
        ).order_by("-id")

    def create(self, request, *args, **kwargs):
        # Override create by copying from source so we can throw 403's
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        status = self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        if status != "success":
            return Response(
                {"error": status},
                status=HTTPStatus.BAD_REQUEST,
                headers=headers,
            )
        else:
            return Response(
                serializer.data, status=HTTPStatus.CREATED, headers=headers
            )

    def perform_create(self, serializer):
        cd = serializer.validated_data
        start, end = reverse_endpoints_if_needed(
            cd["cluster_start"], cd["cluster_end"]
        )
        viz = serializer.save(
            user=self.request.user, cluster_start=start, cluster_end=end
        )
        status, viz = async_to_sync(build_visualization)(viz)
        return status
