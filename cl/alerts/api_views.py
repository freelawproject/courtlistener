from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import BaseThrottle
from rest_framework.viewsets import ModelViewSet

from cl.alerts.api_serializers import (
    DocketAlertSerializer,
    SearchAlertSerializer,
)
from cl.alerts.filters import DocketAlertFilter, SearchAlertFilter
from cl.alerts.models import Alert, DocketAlert
from cl.api.api_permissions import IsOwner, V3APIPermission
from cl.api.models import ThrottleType
from cl.api.pagination import MediumAdjustablePagination
from cl.api.utils import (
    AlertThrottle,
    ExceptionalUserRateThrottle,
    LoggingMixin,
    has_throttle_override,
)

# HTTP methods that create or modify an alert. Commercial-agreement users have
# these governed only by their AlertThrottle rate (get_throttles).
ALERT_WRITE_METHODS = {"POST", "PUT", "PATCH"}


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

    def get_throttles(self) -> list[BaseThrottle]:
        """Route throttling based on the user and the request method.

        Commercial-agreement users (those with an ``APIThrottle`` of type
        ALERTS) have their alert writes governed only by the per-user
        ``AlertThrottle`` rate, bypassing the global per-user API throttle so
        they can create/edit alerts as fast as their configured rate allows.

        Everyone else and commercial users' reads (GET/LIST/DELETE) fall
        back to the standard global throttles.
        """
        user = self.request.user
        is_commercial = user.is_authenticated and has_throttle_override(
            user, ThrottleType.ALERTS
        )
        if is_commercial and self.request.method in ALERT_WRITE_METHODS:
            return [AlertThrottle()]
        return [ExceptionalUserRateThrottle()]

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
