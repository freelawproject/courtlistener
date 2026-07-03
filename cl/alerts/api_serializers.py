from http import HTTPStatus
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import QueryDict
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied

from cl.alerts.constants import (
    FLP_MEMBERSHIP_URL,
    LEGACY_MEMBERSHIP_HELP_URL,
    MEMBERSHIP_UPGRADE_BASE_URL,
)
from cl.alerts.models import (
    Alert,
    DocketAlert,
    validate_alert_type,
    validate_recap_alert_type,
)
from cl.alerts.utils import (
    AlertLimitViolation,
    check_alert_limits,
    get_alert_estimation_count,
    is_match_all_query,
)
from cl.api.utils import DynamicFieldsMixin, HyperlinkedModelSerializerWithId
from cl.donate.models import NeonMembershipLevel
from cl.search.models import SEARCH_TYPES

# The number of days the alert frequency estimation averages over, matching
# the value used by the alert_frequency endpoint in the frontend.
ALERT_ESTIMATION_DAY_COUNT = 100

# Key included in the API response with the estimated number of hits the alert
# query would have produced over the last ALERT_ESTIMATION_DAY_COUNT days.
ALERT_ESTIMATION_RESPONSE_KEY = "estimated_hits"


class BroadAlertQueryError(APIException):
    """Raised when an alert query is estimated to exceed the per-day hit limit.

    Unlike serializers.ValidationError, this sets ``detail`` directly so the
    estimated hits stay an integer in the response (matching the success
    response) instead of being coerced into a list of stringified errors.
    """

    status_code = HTTPStatus.BAD_REQUEST
    default_code = "broad_alert_query"

    def __init__(self, estimated_hits: int, detail: str) -> None:
        # Typed as dict[str, Any] because, unlike DRF's ErrorDetail-based
        # payloads, this intentionally carries a raw integer for the estimated
        # hits so it isn't coerced into a stringified list.
        payload: dict[str, Any] = {
            ALERT_ESTIMATION_RESPONSE_KEY: estimated_hits,
            "detail": detail,
        }
        self.detail = payload


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
        """Validate the query type, set a default for alert_type if not
        provided, enforce the user's alert creation quotas, and reject alerts
        whose query is estimated to be too broad."""

        # The query provided in this request, if any. Used to decide when to
        # re-run the frequency estimation (only when the query is being set).
        request_query = attrs.get("query")
        # Get the query from the request or fall back to the instance, as done
        # during PATCH requests.
        query = request_query or getattr(self.instance, "query", "")
        if query:
            match_all_query = is_match_all_query(query)
            if match_all_query:
                raise serializers.ValidationError(
                    {
                        "query": "You can't create a match-all alert. Please try narrowing your query."
                    }
                )
            attrs["alert_type"] = self._resolve_alert_type(attrs, query)

        # Enforce the membership and per-rate alert quotas, mirroring the
        # checks performed by CreateAlertForm.clean_rate in the frontend.
        self._validate_alert_quota(attrs)

        # Estimate the alert frequency and reject overly broad queries. Only
        # run when the query is being created or changed.
        if request_query:
            self._validate_alert_frequency(request_query)
        return attrs

    @staticmethod
    def _resolve_alert_type(attrs, query):
        """Determine the alert_type from the search query and request body.

        :param attrs: The partially validated request data.
        :param query: The alert's search query string.
        :return: The resolved alert_type.
        """
        qd = QueryDict(query.encode(), mutable=True)
        alert_type_query = qd.get("type")
        alert_type_request = attrs.get("alert_type")

        # If no 'type' is provided in the query parameters, default the alert
        # to an OPINION alert.
        if not alert_type_query:
            return SEARCH_TYPES.OPINION

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
            return alert_type_query

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
        return alert_type_request

    def _validate_alert_quota(self, attrs):
        """Enforce the user's alert creation quotas based on their membership
        status, mirroring CreateAlertForm.clean_rate.

        The shared business logic lives in cl.alerts.utils.check_alert_limits;
        here we only translate the result into the appropriate API error.

        :param attrs: The partially validated request data.
        :return: None
        :raises PermissionDenied: If the request would exceed the user's quota
        or the user isn't eligible to create a Real-Time alert.
        """
        # On PATCH requests, fall back to the instance values for fields that
        # aren't part of the request.
        user = attrs.get("user") or getattr(self.instance, "user", None)
        rate = attrs.get("rate") or getattr(self.instance, "rate", None)
        if user is None or rate is None:
            return
        alert_type = attrs.get("alert_type") or getattr(
            self.instance, "alert_type", None
        )
        alert_being_edited = bool(self.instance and self.instance.pk)

        result = check_alert_limits(
            user,
            rate,
            alert_type,
            exclude_alert_pk=self.instance.pk if alert_being_edited else None,
        )
        match result.violation:
            case AlertLimitViolation.REAL_TIME_NOT_ALLOWED:
                raise PermissionDenied(
                    "You must be a member to create Real Time alerts. "
                    f"Please join Free Law Project as a member: {FLP_MEMBERSHIP_URL}"
                )
            case AlertLimitViolation.MEMBER_QUOTA_EXCEEDED:
                membership = user.membership
                if membership.level == NeonMembershipLevel.LEGACY:
                    # Legacy memberships can't be upgraded online, so point
                    # them at the help page instead of the Neon upgrade flow.
                    raise PermissionDenied(
                        "You've used all of the alerts included with your "
                        "legacy membership. Legacy memberships can't be "
                        "upgraded online; see "
                        f"{LEGACY_MEMBERSHIP_HELP_URL} to learn how to get "
                        "more features, or disable a RECAP Alert."
                    )
                upgrade_url = (
                    f"{MEMBERSHIP_UPGRADE_BASE_URL}{membership.neon_id}"
                )
                raise PermissionDenied(
                    "You've used all of the alerts included with your "
                    "membership. To create this alert, upgrade your membership "
                    f"at {upgrade_url} or disable a RECAP Alert."
                )
            case AlertLimitViolation.FREE_QUOTA_EXCEEDED:
                raise PermissionDenied(
                    f"To create more than {result.free_quota} alerts and to "
                    "gain access to real time alerts, please join Free Law "
                    f"Project as a member: {FLP_MEMBERSHIP_URL}"
                )

    def _validate_alert_frequency(self, query):
        """Estimate the alert's frequency and reject overly broad queries.

        Mirrors the frontend check in search.html: if the query averages more
        than ``settings.MAX_ALERT_RESULTS_PER_DAY`` hits per day over the last
        ``ALERT_ESTIMATION_DAY_COUNT`` days, the alert can't be created. The
        estimated number of hits is stashed so it can be included in the
        response on success, and surfaced in the error otherwise.

        :param query: The alert's search query string.
        :return: None
        :raises ValidationError: If the query can't be validated by SearchForm
        or is estimated to be too broad.
        """
        qd = QueryDict(query.encode(), mutable=True)
        estimation = get_alert_estimation_count(qd, ALERT_ESTIMATION_DAY_COUNT)
        if estimation is None:
            # The query couldn't be validated by SearchForm, so it can't be
            # used for an alert.
            raise serializers.ValidationError(
                {
                    "query": "This query is invalid and can't be used for an alert."
                }
            )

        # Use the first value, as it is the broadest value present across all
        # search types.
        total_hits = estimation[0]
        hits_per_day = total_hits // ALERT_ESTIMATION_DAY_COUNT
        if hits_per_day > settings.MAX_ALERT_RESULTS_PER_DAY:
            raise BroadAlertQueryError(
                estimated_hits=total_hits,
                detail=(
                    f"This query averages about {hits_per_day} results per "
                    "day, which is more than our system can support. Please "
                    "narrow your query to have fewer results per day."
                ),
            )
        self._alert_frequency_estimation = total_hits

    def to_representation(self, instance):
        """Include the alert frequency estimation in the response when it was
        computed during validation (i.e. on create/update)."""
        representation = super().to_representation(instance)
        estimation = getattr(self, "_alert_frequency_estimation", None)
        if estimation is not None:
            representation[ALERT_ESTIMATION_RESPONSE_KEY] = estimation
        return representation

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
                self.instance.validate_alert_type_change()
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
