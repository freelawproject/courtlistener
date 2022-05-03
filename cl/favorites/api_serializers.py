from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from cl.favorites.models import DocketTag, UserTag
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
