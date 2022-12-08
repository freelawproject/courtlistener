from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers
from rest_framework.serializers import HyperlinkedRelatedField

from cl.alerts.models import Alert, DocketAlert
from cl.api.utils import HyperlinkedModelSerializerWithId
from cl.search.models import Docket


class SearchAlertSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Alert
        fields = "__all__"
        read_only_fields = (
            "date_created",
            "date_modified",
            "secret_key",
            "date_last_hit",
        )


class SearchAlertSerializerModel(
    DynamicFieldsMixin, serializers.ModelSerializer
):
    """This serializer is used to serialize an alert when a webhook is sent
    because SearchAlertSerializer inherits from HyperlinkedModelSerializerWithId
    which requires an HTTP request to work.
    """

    class Meta:
        model = Alert
        fields = "__all__"


class DocketAlertSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    docket: HyperlinkedRelatedField = HyperlinkedRelatedField(
        many=False,
        view_name="docket-detail",
        queryset=Docket.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = DocketAlert
        fields = "__all__"
        extra_kwargs = {"resource_uri": {"view_name": "docket-alert-detail"}}
        read_only_fields = (
            "date_created",
            "date_modified",
            "secret_key",
            "date_last_hit",
        )
