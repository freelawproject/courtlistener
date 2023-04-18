import rest_framework_filters as filters

from cl.api.utils import DATE_LOOKUPS, DATETIME_LOOKUPS, NoEmptyFilterSet
from cl.audio.models import Audio
from cl.search.filters import DocketFilter
from cl.search.models import SOURCES, Docket


class AudioFilter(NoEmptyFilterSet):
    docket = filters.RelatedFilter(DocketFilter, queryset=Docket.objects.all())
    source = filters.MultipleChoiceFilter(choices=SOURCES.NAMES)

    class Meta:
        model = Audio
        fields = {
            "id": ["exact"],
            "date_modified": DATETIME_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "sha1": ["exact"],
            "blocked": ["exact"],
            "date_blocked": DATE_LOOKUPS,
            "processing_complete": ["exact"],
        }
