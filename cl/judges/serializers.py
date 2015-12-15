from cl.judges.models import Judge, Position
from rest_framework import serializers


class PositionSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Position


class JudgeSerializer(serializers.HyperlinkedModelSerializer):
    race = serializers.StringRelatedField(many=True)

    class Meta:
        model = Judge
