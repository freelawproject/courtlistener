from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from cl.alerts.api_serializers import (
    DocketAlertSerializer,
    SearchAlertSerializer,
)
from cl.alerts.filters import DocketAlertFilter, SearchAlertFilter
from cl.alerts.models import Alert, DocketAlert
from cl.api.api_permissions import IsOwner, V3APIPermission
from cl.api.pagination import MediumAdjustablePagination
from cl.api.utils import LoggingMixin


class SearchAlertViewSet(LoggingMixin, ModelViewSet):
    """A ModelViewset to handle CRUD operations for SearchAlerts."""

    permission_classes = [IsOwner, IsAuthenticated, V3APIPermission]
    serializer_class = SearchAlertSerializer
    pagination_class = MediumAdjustablePagination
    filterset_class = SearchAlertFilter
    ordering_fields = (
        "date_created",
        "date_modified",
        "name",
        "rate",
    )
    # Default cursor ordering key
    ordering = "-date_created"
    # Additional cursor ordering fields
    cursor_ordering_fields = ["date_created"]

    def get_queryset(self):
        """
        Return a list of all the search alerts
        for the currently authenticated user.
        """
        user = self.request.user
        return Alert.objects.filter(user=user).order_by("-date_created")


class DocketAlertViewSet(LoggingMixin, ModelViewSet):
    """A ModelViewset to handle CRUD operations for DocketAlerts."""

    permission_classes = [IsOwner, IsAuthenticated, V3APIPermission]
    serializer_class = DocketAlertSerializer
    pagination_class = MediumAdjustablePagination
    filterset_class = DocketAlertFilter
    ordering_fields = (
        "date_created",
        "date_modified",
    )
    # Default cursor ordering key
    ordering = "-date_created"
    # Additional cursor ordering fields
    cursor_ordering_fields = ["date_created"]

    def get_queryset(self):
        """
        Return a list of all the docket alerts
        for the currently authenticated user.
        """
        user = self.request.user
        return DocketAlert.objects.filter(user=user).order_by("-date_created")
