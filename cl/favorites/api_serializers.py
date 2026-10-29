import re

from asgiref.sync import async_to_sync
from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS
from rest_framework.serializers import ModelSerializer

from cl.api.utils import DynamicFieldsMixin
from cl.favorites.models import DocketTag, Prayer, UserTag
from cl.favorites.selectors import prayer_eligible
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
        queryset=UserTag.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = DocketTag
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Scope writable `tag` values to the requester's own tags
        # (GHSA-cvh7-rv7v-wx2j-class).
        request = self.context.get("request")
        if (
            request is not None
            and request.method not in SAFE_METHODS
            and request.user.is_authenticated
        ):
            self.fields["tag"].queryset = UserTag.objects.filter(
                user=request.user
            )


class PrayerSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Prayer
        fields = "__all__"
        read_only_fields = ("date_created",)

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
        # - 'p.<id>:view' format, e.g., 'p.123:view' for judge views
        # - 'o.<id>:view' format, e.g., 'o.123:view' for opinion views
        valid_pattern = [
            r"^[dpo]\.(\d{1,10}):view$",
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
