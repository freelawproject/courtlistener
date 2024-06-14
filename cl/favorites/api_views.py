from django.db.models import Q
from rest_framework import permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from cl.api.pagination import MediumAdjustablePagination
from cl.favorites.api_permissions import IsTagOwner
from cl.favorites.api_serializers import DocketTagSerializer, UserTagSerializer
from cl.favorites.filters import DocketTagFilter, UserTagFilter
from cl.favorites.models import DocketTag, UserTag


class UserTagViewSet(ModelViewSet):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
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
    # Other cursor ordering keys
    other_cursor_ordering_keys = [
        "id",
        "date_created",
        "-date_created",
        "date_modified",
        "-date_modified",
    ]

    def get_queryset(self):
        q = Q(published=True)
        if self.request.user.is_authenticated:
            q |= Q(user=self.request.user)
        return UserTag.objects.filter(q).order_by("-id")


class DocketTagViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, IsTagOwner]
    serializer_class = DocketTagSerializer
    filterset_class = DocketTagFilter
    pagination_class = MediumAdjustablePagination
    # Default cursor ordering key
    ordering = "-id"
    # Other cursor ordering keys
    other_cursor_ordering_keys = ["id"]

    def get_queryset(self):
        return DocketTag.objects.filter(
            Q(tag__user=self.request.user) | Q(tag__published=True)
        )
