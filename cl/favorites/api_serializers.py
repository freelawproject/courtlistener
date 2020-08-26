from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from cl.favorites.models import UserTag, DocketTag
from cl.search.models import Docket


class UserTagSerializer(DynamicFieldsMixin, ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

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
