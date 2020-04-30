from rest_framework import serializers
from cl.visualizations.models import SCOTUSMap
from cl.search.models import OpinionCluster


class VisualizationSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    title = serializers.CharField(max_length=200)
    cluster_start = serializers.PrimaryKeyRelatedField(
        queryset=OpinionCluster.objects.filter(docket__court_id="scotus"),
        style={"base_template": "select.html"},
    )
    cluster_end = serializers.PrimaryKeyRelatedField(
        queryset=OpinionCluster.objects.filter(docket__court_id="scotus"),
        style={"base_template": "select.html"},
    )

    class Meta:
        model = SCOTUSMap
        # TODO: Do we just want all fields?
        # TODO: What about nested JSON data?
        # TODO: What about security?
        # TODO: What about validation?
        # TODO: fields looks like it could just be "__all__"
        fields = ["user", "title", "cluster_start", "cluster_end"]
