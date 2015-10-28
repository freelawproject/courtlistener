from cl.audio import models as audio_models
from cl.search import models as search_models

from rest_framework import serializers


class DocketSerializer(serializers.HyperlinkedModelSerializer):
    court = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='court-detail',
        read_only=True,
    )
    clusters = serializers.HyperlinkedRelatedField(
        many=True,
        view_name='opinioncluster-detail',
        read_only=True,
    )
    absolute_url = serializers.CharField(source='get_absolute_url',
                                         read_only=True)

    class Meta:
        model = search_models.Docket


class CourtSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = search_models.Court
        exclude = ('notes',)


class AudioSerializer(serializers.HyperlinkedModelSerializer):
    absolute_url = serializers.CharField(source='get_absolute_url',
                                         read_only=True)

    class Meta:
        model = audio_models.Audio


class OpinionClusterSerializer(serializers.HyperlinkedModelSerializer):
    absolute_url = serializers.CharField(source='get_absolute_url',
                                         read_only=True)

    class Meta:
        model = search_models.OpinionCluster


class OpinionSerializer(serializers.HyperlinkedModelSerializer):
    absolute_url = serializers.CharField(source='get_absolute_url',
                                         read_only=True)

    class Meta:
        model = search_models.Opinion


class OpinionsCitedSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = search_models.OpinionsCited


class SearchResultSerializer(serializers.Serializer):
    """The serializer for search results.
    """
    pk = serializers.IntegerField(read_only=True)
