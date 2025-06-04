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

        # Get the query from the request or fall back to the instance, as done
        # during PATCH requests.
        query = attrs.get("query") or getattr(self.instance, "query", "")
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

        # If no 'type' is provided in the query parameters, default the alert
        # to an OPINION alert.
        if not alert_type_query:
            attrs["alert_type"] = SEARCH_TYPES.OPINION
            return attrs

        recap_supported_types = [
            alert_type for alert_type, _ in SEARCH_TYPES.RECAP_ALERT_TYPES
        ]
        # For non-RECAP alert types specified in the query, validate against
        # all supported types.
        if alert_type_query not in recap_supported_types:
            try:
                validate_alert_type(alert_type_query)
            except ValidationError as e:
                raise serializers.ValidationError({"alert_type": e.messages})
            attrs["alert_type"] = alert_type_query
            return attrs

        # If the query specifies a RECAP alert type, make sure an 'alert_type'
        # is also provided in the request body.
        if not alert_type_request:
            raise serializers.ValidationError(
                {
                    "alert_type": "Please provide an alert type for your RECAP search query. "
                    "For notifications on cases only, use the d type. "
                    "For notifications on both cases and filings, use the r type."
                }
            )

        # For RECAP or DOCKETS query types, validate the requested
        # 'alert_type' against RECAP-specific valid types.
        try:
            validate_recap_alert_type(alert_type_request)
        except ValidationError:
            raise serializers.ValidationError(
                {
                    "alert_type": "The specified alert type is not valid "
                    "for the given RECAP search query."
                }
            )
        # If the requested RECAP alert type is valid, use it.
        attrs["alert_type"] = alert_type_request
        return attrs

    def create(self, validated_data):
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # On alert updates, validates that the alert_type hasn't changed in a
        # disallowed way.
        alert_type = validated_data.get("alert_type")
        if alert_type:
            try:
                # Update the instance's alert_type to compare it with its old value
                self.instance.alert_type = alert_type
                self.instance.alert_type_changed()
            except ValidationError as e:
                raise serializers.ValidationError(e.message_dict)

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
