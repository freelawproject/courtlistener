from rest_framework import viewsets
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly

from cl.api.api_permissions import V3APIPermission
from cl.api.utils import LoggingMixin
from cl.audio.api_serializers import AudioSerializer
from cl.audio.filters import AudioFilter
from cl.audio.models import Audio


class AudioViewSet(LoggingMixin, viewsets.ModelViewSet):
    serializer_class = AudioSerializer
    filterset_class = AudioFilter
    permission_classes = [
        DjangoModelPermissionsOrAnonReadOnly,
        V3APIPermission,
    ]
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "date_blocked",
    )
    # Default cursor ordering key
    ordering = "-id"
    # Additional cursor ordering fields
    cursor_ordering_fields = [
        "id",
        "date_created",
        "date_modified",
    ]
    queryset = (
        Audio.objects.all()
        .select_related("docket")
        .prefetch_related("panel")
        .order_by("-id")
    )
