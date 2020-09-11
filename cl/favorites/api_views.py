from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from cl.api.api_permissions import IsOwner
from cl.api.utils import LoggingMixin, MediumPagination
from cl.favorites.api_permissions import IsTagOwner
from cl.favorites.api_serializers import UserTagSerializer, DocketTagSerializer
from cl.favorites.filters import UserTagFilter, DocketTagFilter
from cl.favorites.models import UserTag, DocketTag


class UserTagViewSet(LoggingMixin, ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = UserTagSerializer
    pagination_class = MediumPagination
    filter_class = UserTagFilter
    ordering_fields = (
        "date_created",
        "date_modified",
        "view_count",
    )

    def get_queryset(self):
        return UserTag.objects.filter(
            Q(user=self.request.user) | Q(published=True)
        ).order_by("-id")


class DocketTagViewSet(LoggingMixin, ModelViewSet):
    permission_classes = [IsAuthenticated, IsTagOwner]
    serializer_class = DocketTagSerializer
    filter_class = DocketTagFilter
    pagination_class = MediumPagination

    def get_queryset(self):
        return DocketTag.objects.filter(
            Q(tag__user=self.request.user) | Q(tag__published=True)
        )
