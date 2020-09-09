from rest_framework_filters import FilterSet

from cl.api.utils import (
    INTEGER_LOOKUPS,
    BOOLEAN_LOOKUPS,
    BASIC_TEXT_LOOKUPS,
)
from cl.favorites.models import UserTag, DocketTag


class UserTagFilter(FilterSet):
    class Meta:
        model = UserTag
        fields = {
            "id": ["exact"],
            "user": ["exact"],
            "name": BASIC_TEXT_LOOKUPS,
            "published": BOOLEAN_LOOKUPS,
        }


class DocketTagFilter(FilterSet):
    class Meta:
        model = DocketTag
        fields = {
            "id": ["exact"],
            "docket": ["exact"],
            "tag": ["exact"],
        }
