from rest_framework_filters import FilterSet

from cl.api.utils import (
    INTEGER_LOOKUPS,
    BOOLEAN_LOOKUPS,
    BASIC_TEXT_LOOKUPS,
)
from cl.favorites.models import UserTag


class UserTagFilter(FilterSet):
    class Meta:
        model = UserTag
        fields = {
            "id": ["exact"],
            "user": ["exact"],
            "name": BASIC_TEXT_LOOKUPS,
            "published": BOOLEAN_LOOKUPS,
        }
