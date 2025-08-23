from rest_framework import viewsets
from rest_framework.permissions import (
    DjangoModelPermissionsOrAnonReadOnly,
    IsAuthenticated,
)

from cl.api.api_permissions import CanViewTranscriptPermission, V3APIPermission
from cl.api.utils import DeferredFieldsMixin, LoggingMixin
from cl.audio.api_serializers import AudioSerializer, TranscriptSerializer
from cl.audio.filters import AudioFilter
from cl.audio.models import Audio


class AudioViewSet(LoggingMixin, DeferredFieldsMixin, viewsets.ModelViewSet):
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

class TranscriptViewSet(viewsets.ReadOnlyModelViewSet):
    """
    A viewset for viewing transcripts.
    """

    queryset = Audio.objects.all()
    serializer_class = TranscriptSerializer
    permission_classes = [IsAuthenticated, CanViewTranscriptPermission]
