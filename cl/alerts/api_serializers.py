from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from cl.alerts.models import Alert, DocketAlert
from cl.api.utils import HyperlinkedModelSerializerWithId


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


class DocketAlertSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = DocketAlert
        fields = "__all__"
        read_only_fields = (
            "date_created",
            "date_modified",
            "secret_key",
            "date_last_hit",
        )
