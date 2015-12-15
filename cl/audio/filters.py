import rest_framework_filters as filters
from cl.audio.models import Audio
from cl.search.filters import DocketFilter


class AudioFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_blocked = filters.AllLookupsFilter(name='date_blocked')
    docket = filters.RelatedFilter(DocketFilter, name='docket')

    class Meta:
        model = Audio
        fields = (
            'id', 'source', 'sha1', 'blocked', 'processing_complete',
        )
