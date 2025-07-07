import re

from asgiref.sync import async_to_sync
from django.conf import settings
from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import ModelSerializer

from cl.favorites.models import DocketTag, Prayer, UserTag
from cl.favorites.utils import prayer_eligible
from cl.search.models import Docket


class UserTagSerializer(DynamicFieldsMixin, ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    description = serializers.CharField(
        max_length=250_000,  # Huge, but small enough to prevent DOS. ~1MB
        allow_blank=True,
        required=False,
    )

    class Meta:
        model = UserTag
        fields = "__all__"
        read_only_fields = (
            "date_created",
            "date_modified",
            "view_count",
        )


class DocketTagSerializer(DynamicFieldsMixin, ModelSerializer):
    docket = serializers.PrimaryKeyRelatedField(
        queryset=Docket.objects.all(), style={"base_template": "input.html"}
    )
    tag = serializers.PrimaryKeyRelatedField(
        # Should this block other people's from being submitted?
        queryset=UserTag.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = DocketTag
        fields = "__all__"


class PrayerSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Prayer
        fields = "__all__"
        read_only_fields = (
            "date_created",
            "user",
        )

    def validate(self, data):
        user = self.context["request"].user
        recap_document = data.get("recap_document")

        # Check if a Prayer for the same user and recap_document already exists
        if Prayer.objects.filter(
            user=user, recap_document=recap_document
        ).exists():
            raise ValidationError(
                "A prayer for this recap document already exists."
            )

        # Check if the user is eligible to create a new prayer
        if not async_to_sync(prayer_eligible)(user)[0]:
            raise ValidationError(
                f"You have reached the maximum number of prayers ({settings.ALLOWED_PRAYER_COUNT}) allowed in the last 24 hours."
            )
        return data


class EventCountSerializer(serializers.Serializer):
    label = serializers.CharField(required=True, max_length=255)

    def validate(self, attrs):
        label = attrs.get("label")
        # Define a list of allowed regex patterns for valid labels
        # Currently supports:
        # - 'd.<id>:view' format, e.g., 'd.123:view' for docket views
        valid_pattern = [
            r"^d\.(\d+):view$",
        ]
        # Check if the label matches any of the allowed patterns
        pattern_checks = [
            re.match(pattern, label) for pattern in valid_pattern
        ]
        # If no pattern matches, raise a validation error
        if not any(pattern_checks):
            raise serializers.ValidationError(
                {"label": "Invalid label format provided."}
            )
        return super().validate(attrs)
