from rest_framework import viewsets

from cl.api.utils import LoggingMixin
from cl.audio.api_filters import AudioFilter
from cl.audio.api_serializers import AudioSerializer
from cl.audio.models import Audio


class AudioViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Audio.objects.all()
    serializer_class = AudioSerializer
    filter_class = AudioFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_blocked',
    )
