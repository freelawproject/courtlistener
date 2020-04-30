from rest_framework import serializers
from cl.visualizations.models import SCOTUSMap
from cl.search.models import OpinionCluster


class VisualizationSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
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
