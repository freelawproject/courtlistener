from django.core.exceptions import ValidationError
from django.http import QueryDict
from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from cl.alerts.models import Alert, DocketAlert, validate_alert_type
from cl.api.utils import HyperlinkedModelSerializerWithId
from cl.search.models import SEARCH_TYPES


class SearchAlertSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    alert_type = serializers.CharField(required=False)

    class Meta:
        model = Alert
        fields = "__all__"
        read_only_fields = (
            "date_created",
            "date_modified",
            "secret_key",
            "date_last_hit",
        )

    def validate(self, attrs):
        """Validate the query type and set default for alert_type if not
        provided."""
        if "query" not in attrs:
            return attrs

        qd = QueryDict(attrs.get("query").encode(), mutable=True)
        alert_type = qd.get("type")
        if alert_type:
            try:
                validate_alert_type(alert_type)
                attrs["alert_type"] = alert_type
            except ValidationError as e:
                raise serializers.ValidationError({"alert_type": e.messages})
        else:
            # If not type provided in the query it's an OPINION Alert.
            attrs["alert_type"] = SEARCH_TYPES.OPINION
        return attrs

    def create(self, validated_data):
        return super().create(validated_data)

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)


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
