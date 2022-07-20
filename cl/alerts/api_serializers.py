from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from cl.alerts.models import Alert
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
