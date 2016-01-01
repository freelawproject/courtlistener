import rest_framework_filters as filters

from cl.api.utils import DATETIME_LOOKUPS, DATE_LOOKUPS
from cl.audio.models import Audio
from cl.search.filters import DocketFilter
from cl.search.models import SOURCES


class AudioFilter(filters.FilterSet):
    docket = filters.RelatedFilter(DocketFilter, name='docket')
    source = filters.MultipleChoiceFilter(
        choices=SOURCES,
    )

    class Meta:
        model = Audio
        fields = {
            'id': ['exact'],
            'date_modified': DATETIME_LOOKUPS,
            'date_created': DATETIME_LOOKUPS,
            'sha1': ['exact'],
            'blocked': ['exact'],
            'date_blocked': DATE_LOOKUPS,
            'processing_complete': ['exact'],
        }
