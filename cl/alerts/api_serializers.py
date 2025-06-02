from django.core.exceptions import ValidationError
from django.http import QueryDict
from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from cl.alerts.models import (
    Alert,
    DocketAlert,
    validate_alert_type,
    validate_recap_alert_type,
)
from cl.alerts.utils import is_match_all_query
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

        query = attrs.get("query", "")
        if not query:
            return attrs

        match_all_query = is_match_all_query(query)
        if match_all_query:
            raise serializers.ValidationError(
                {
                    "query": "You can't create a match-all alert. Please try narrowing your query."
                }
            )

        qd = QueryDict(query.encode(), mutable=True)
        alert_type_query = qd.get("type")
        alert_type_request = attrs.get("alert_type")

        # If the request provided an alert_type and the query type is
        # RECAP or DOCKETS, validate alert_type_request against RECAP-specific
        # valid types.
        if alert_type_request and alert_type_query in [
            SEARCH_TYPES.RECAP,
            SEARCH_TYPES.DOCKETS,
        ]:
            try:
                validate_recap_alert_type(alert_type_request)
            except ValidationError:
                raise serializers.ValidationError(
                    {
                        "alert_type": "The specified alert type is not valid "
                        "for the given RECAP search query."
                    }
                )
            # If the provided alert_type_request is valid for the RECAP query, use it.
            attrs["alert_type"] = alert_type_request

            return attrs

        # Validate the alert type specified in the query for non-RECAP alerts.
        if alert_type_query:
            try:
                validate_alert_type(alert_type_query)
                attrs["alert_type"] = alert_type_query
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
