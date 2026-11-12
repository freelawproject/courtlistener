"""REST API filters for tags and prayers."""

import rest_framework_filters as filters

from cl.api.utils import BASIC_TEXT_LOOKUPS, BOOLEAN_LOOKUPS, NoEmptyFilterSet
from cl.favorites.models import DocketTag, Prayer, UserTag


class UserTagFilter(NoEmptyFilterSet):
    """Filter tags by ID, user, name, and published status."""

    class Meta:
        model = UserTag
        fields = {
            "id": ["exact"],
            "user": ["exact"],
            "name": BASIC_TEXT_LOOKUPS,
            "published": BOOLEAN_LOOKUPS,
        }


class DocketTagFilter(NoEmptyFilterSet):
    """Filter docket tags by ID, docket, and tag."""

    tag = filters.RelatedFilter(UserTagFilter, queryset=UserTag.objects.all())

    class Meta:
        model = DocketTag
        fields = {"id": ["exact"], "docket": ["exact"]}


class PrayerFilter(NoEmptyFilterSet):
    """Filter prayers by creation date, user, RECAP document, and status."""

    date_created = filters.DateFromToRangeFilter(
        field_name="date_created",
        help_text="Filter prayers by a date range (e.g., ?date_created_after=2024-09-01&date_created_before=2024-12-31).",
    )

    class Meta:
        model = Prayer
        fields = {
            "date_created": ["exact", "range"],
            "user": ["exact"],
            "recap_document": ["exact"],
            "status": ["exact", "in"],
        }
