from cl.audio import models as audio_models
from rest_framework import serializers


class AudioSerializer(serializers.HyperlinkedModelSerializer):
    absolute_url = serializers.CharField(source='get_absolute_url',
                                         read_only=True)
    panel = serializers.HyperlinkedRelatedField(
            many=True,
            view_name='judge-detail',
            read_only=True,
    )

    class Meta:
        model = audio_models.Audio
