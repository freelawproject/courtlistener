from rest_framework import viewsets

from cl.api.utils import LoggingMixin
from cl.audio.api_serializers import AudioSerializer
from cl.audio.filters import AudioFilter
from cl.audio.models import Audio


class AudioViewSet(LoggingMixin, viewsets.ModelViewSet):
    serializer_class = AudioSerializer
    filter_class = AudioFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_blocked',
    )
    queryset = Audio.objects.all().select_related(
        'docket').prefetch_related('panel').order_by('-id')
