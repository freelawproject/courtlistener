from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from cl.api.utils import HyperlinkedModelSerializerWithId
from cl.search.models import OpinionCluster
from cl.visualizations.models import JSONVersion, SCOTUSMap


class JSONVersionSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    class Meta:
        model = JSONVersion
        fields = "__all__"


class VisualizationSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    title = serializers.CharField(max_length=200)
    cluster_start = serializers.HyperlinkedRelatedField(
        queryset=OpinionCluster.objects.filter(docket__court_id="scotus"),
        view_name="opinioncluster-detail",
        style={"base_template": "input.html"},
    )
    cluster_end = serializers.HyperlinkedRelatedField(
        queryset=OpinionCluster.objects.filter(docket__court_id="scotus"),
        view_name="opinioncluster-detail",
        style={"base_template": "input.html"},
    )
    json_versions = JSONVersionSerializer(many=True, read_only=True)
    clusters = serializers.HyperlinkedRelatedField(
        view_name="opinioncluster-detail",
        style={"base_template": "input.html"},
        read_only=True,
        many=True,
    )
    absolute_url = serializers.CharField(
        source="get_absolute_url", read_only=True
    )

    class Meta:
        model = SCOTUSMap
        fields = "__all__"
        read_only_fields = (
            "view_count",
            "date_created",
            "date_modified",
            "date_published",
            "date_deleted",
            "slug",
            "generation_time",
        )
