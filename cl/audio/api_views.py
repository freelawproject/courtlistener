from cl.audio.filters import AudioFilter
from cl.audio.models import Audio
from cl.audio.serializers import AudioSerializer
from rest_framework import viewsets


class AudioViewSet(viewsets.ModelViewSet):
    queryset = Audio.objects.all()
    serializer_class = AudioSerializer
    filter_class = AudioFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_blocked',
    )
