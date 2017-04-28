from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from cl.audio import models as audio_models
from cl.people_db.models import Person
from cl.search.models import Docket


class AudioSerializer(DynamicFieldsMixin,
                      serializers.HyperlinkedModelSerializer):
    absolute_url = serializers.CharField(source='get_absolute_url',
                                         read_only=True)
    panel = serializers.HyperlinkedRelatedField(
        many=True,
        view_name='person-detail',
        queryset=Person.objects.all(),
        style={'base_template': 'input.html'},
    )
    # This seems unnecessary and it serializes the same data either way. But
    # when this is not here, the API does a query that pulls back ALL dockets.
    docket = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='docket-detail',
        queryset=Docket.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = audio_models.Audio
        fields = '__all__'
