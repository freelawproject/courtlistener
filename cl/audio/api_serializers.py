from rest_framework import serializers

from cl.audio import models as audio_models


class AudioSerializer(serializers.HyperlinkedModelSerializer):
    absolute_url = serializers.CharField(source='get_absolute_url',
                                         read_only=True)
    panel = serializers.HyperlinkedRelatedField(
        many=True,
        view_name='person-detail',
        read_only=True,
    )
    # This seems unnecessary and it serializes the same data either way. But
    # when this is not here, the API does a query that pulls back ALL dockets.
    docket = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='docket-detail',
        read_only=True,
    )

    class Meta:
        model = audio_models.Audio
