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
