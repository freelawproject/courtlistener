from cl.api.utils import BASIC_TEXT_LOOKUPS, BOOLEAN_LOOKUPS, NoEmptyFilterSet
from cl.favorites.models import DocketTag, UserTag


class UserTagFilter(NoEmptyFilterSet):
    class Meta:
        model = UserTag
        fields = {
            "id": ["exact"],
            "user": ["exact"],
            "name": BASIC_TEXT_LOOKUPS,
            "published": BOOLEAN_LOOKUPS,
        }


class DocketTagFilter(NoEmptyFilterSet):
    class Meta:
        model = DocketTag
        fields = {
            "id": ["exact"],
            "docket": ["exact"],
            "tag": ["exact"],
        }
