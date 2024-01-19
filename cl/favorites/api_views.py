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
    permission_classes = [permissions.AllowAny]
    serializer_class = UserTagSerializer
    pagination_class = MediumAdjustablePagination
    filterset_class = UserTagFilter
    ordering_fields = (
        "date_created",
        "date_modified",
        "name",
        "view_count",
    )

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

    def get_queryset(self):
        return DocketTag.objects.filter(
            Q(tag__user=self.request.user) | Q(tag__published=True)
        )
