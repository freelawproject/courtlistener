from http import HTTPStatus

from django.db import transaction
from django.db.models import F, Q
from rest_framework import permissions
from rest_framework.mixins import CreateModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from cl.api.api_permissions import V3APIPermission
from cl.api.pagination import MediumAdjustablePagination
from cl.api.utils import LoggingMixin
from cl.favorites.api_permissions import IsTagOwner
from cl.favorites.api_serializers import (
    DocketTagSerializer,
    EventCountSerializer,
    PrayerSerializer,
    UserTagSerializer,
)
from cl.favorites.filters import DocketTagFilter, PrayerFilter, UserTagFilter
from cl.favorites.models import DocketTag, GenericCount, Prayer, UserTag


class UserTagViewSet(ModelViewSet):
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        V3APIPermission,
    ]
    serializer_class = UserTagSerializer
    pagination_class = MediumAdjustablePagination
    filterset_class = UserTagFilter
    ordering_fields = (
        "date_created",
        "date_modified",
        "name",
        "view_count",
    )
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]

    def get_queryset(self):
        q = Q(published=True)
        if self.request.user.is_authenticated:
            q |= Q(user=self.request.user)
        return UserTag.objects.filter(q).order_by("-id")


class DocketTagViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, IsTagOwner, V3APIPermission]
    serializer_class = DocketTagSerializer
    filterset_class = DocketTagFilter
    pagination_class = MediumAdjustablePagination
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = ["id"]

    def get_queryset(self):
        return DocketTag.objects.filter(
            Q(tag__user=self.request.user) | Q(tag__published=True)
        )


class PrayerViewSet(LoggingMixin, ModelViewSet):
    """A ModelViewset to handle CRUD operations for Prayer."""

    permission_classes = [IsAuthenticated, V3APIPermission]
    serializer_class = PrayerSerializer
    pagination_class = MediumAdjustablePagination
    filterset_class = PrayerFilter
    ordering_fields = ("date_created",)
    # Default cursor ordering key
    ordering = "-date_created"
    # Additional cursor ordering fields
    cursor_ordering_fields = ["date_created"]
    # Only allow these methods. Restricting PUT and PATCH.
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        """
        Return a list of all the open prayers
        for the currently authenticated user.
        """
        user = self.request.user
        return Prayer.objects.filter(
            user=user, status=Prayer.WAITING
        ).order_by("-date_created")


class EventCounterViewset(CreateModelMixin, GenericViewSet):
    serializer_class = EventCountSerializer
    permission_classes = (permissions.AllowAny,)

    def create(self, request, *args, **kwargs):
        """
        Handle a POST request to increment event counters based on their label.

        This method validates incoming request data, retrieves or creates a
        GenericCount record for the specified label, and atomically increments
        its value by 1. It then returns the label and the previous count value
        before the increment.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        event_data = serializer.validated_data
        with transaction.atomic():
            counter_record, _ = (
                GenericCount.objects.select_for_update().get_or_create(
                    label=event_data["label"]
                )
            )
            initial_count = counter_record.value
            counter_record.value = F("value") + 1
            counter_record.save(update_fields=["value"])

        headers = self.get_success_headers(serializer.data)
        return Response(
            {"label": counter_record.label, "value": initial_count},
            status=HTTPStatus.ACCEPTED,
            headers=headers,
        )
