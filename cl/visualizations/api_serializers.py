from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from cl.api.utils import HyperlinkedModelSerializerWithId
from cl.visualizations.models import SCOTUSMap
from cl.search.models import OpinionCluster
from cl.recap.models import ProcessingQueue

<<<<<<< HEAD
class VisualizationSerializer(serializers.ModelSerializer):
=======

class CreateVisualizationSerializer(serializers.ModelSerializer):
>>>>>>> 3ae07497bb981edf56c3edbf2ae21fffbcda38ba
    user = serializers.HiddenField(default=serializers.CurrentUserDefault(),)
    title = serializers.CharField(max_length=200)
    cluster_start = serializers.PrimaryKeyRelatedField(
        queryset=OpinionCluster.objects.all(),
        style={"base_template": "select.html"},
    )
    cluster_end = serializers.PrimaryKeyRelatedField(
        queryset=OpinionCluster.objects.all(),
        style={"base_template": "select.html"},
    )

    class Meta:
        model = SCOTUSMap
        fields = ["user", "title", "cluster_start", "cluster_end"]
