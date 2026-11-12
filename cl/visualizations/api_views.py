"""REST API viewsets for SCOTUS network visualizations and their JSON versions."""

from http import HTTPStatus

from asgiref.sync import async_to_sync
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from cl.api.api_permissions import IsOwner, V3APIPermission
from cl.api.utils import LoggingMixin
from cl.visualizations.api_serializers import (
    JSONVersionSerializer,
    VisualizationSerializer,
)
from cl.visualizations.models import JSONVersion, SCOTUSMap
from cl.visualizations.network_utils import reverse_endpoints_if_needed
from cl.visualizations.utils import build_visualization


class JSONViewSet(LoggingMixin, ReadOnlyModelViewSet):
    """Read-only: JSONVersions are only ever created server-side, by build_visualization() (GHSA-cvh7-rv7v-wx2j)."""

    permission_classes = [
        IsAuthenticated,
        V3APIPermission,
    ]
    serializer_class = JSONVersionSerializer
    ordering_fields = ("id", "date_created", "date_modified")
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]

    def get_queryset(self):
        """Get the JSON versions of the user's and published visualizations."""
        return JSONVersion.objects.filter(
            Q(map__user=self.request.user) | Q(map__published=True)
        ).order_by("-id")


class VisualizationViewSet(LoggingMixin, ModelViewSet):
    """API endpoint for SCOTUS network visualizations."""

    permission_classes = [IsAuthenticated, IsOwner, V3APIPermission]
    serializer_class = VisualizationSerializer
    ordering_fields = ("id", "date_created", "date_modified", "user")
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]

    def get_queryset(self):
        """Get the user's and published visualizations."""
        return (
            SCOTUSMap.objects.filter(
                Q(user=self.request.user) | Q(published=True)
            )
            .prefetch_related("json_versions", "clusters")
            .order_by("-id")
        )

    def create(self, request, *args, **kwargs):
        """Create and build a visualization.

        Responds with 400 and the build status if the build doesn't
        succeed, otherwise with 201 and the visualization.
        """
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
        """Save the visualization with its endpoints in date order, then build it.

        Returns:
            The status of building the visualization.
        """
        cd = serializer.validated_data
        start, end = reverse_endpoints_if_needed(
            cd["cluster_start"], cd["cluster_end"]
        )
        viz = serializer.save(
            user=self.request.user, cluster_start=start, cluster_end=end
        )
        status, viz = async_to_sync(build_visualization)(viz)
        return status
