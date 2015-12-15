from cl.audio.models import Audio
from cl.search.models import (
    Court, OpinionCluster, Docket, Opinion
)
import rest_framework_filters as filters


class CourtFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    position = filters.AllLookupsFilter(name='position')
    start_date = filters.AllLookupsFilter(name='start_date')
    end_date = filters.AllLookupsFilter(name='end_date')

    class Meta:
        model = Court
        fields = (
            'id', 'date_modified', 'in_use', 'has_opinion_scraper',
            'has_oral_argument_scraper', 'position', 'start_date', 'end_date',
            'jurisdiction',
        )


class DocketFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_argued = filters.AllLookupsFilter(name='date_argued')
    date_reargued = filters.AllLookupsFilter(name='date_reargued')
    date_reargument_denied = filters.AllLookupsFilter(
        name='date_reargument_denied')
    court = filters.RelatedFilter(CourtFilter, name='court')
    date_blocked = filters.AllLookupsFilter(name='date_blocked')

    class Meta:
        model = Docket
        fields = (
            'id', 'blocked',
        )


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


class OpinionClusterFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_blocked = filters.AllLookupsFilter(name='date_blocked')
    date_filed = filters.AllLookupsFilter(name='date_filed')
    docket = filters.RelatedFilter(DocketFilter, name='docket')

    class Meta:
        model = OpinionCluster
        fields = (
            'id', 'per_curiam', 'citation_id', 'citation_count', 'scdb_id',
            'scdb_decision_direction', 'scdb_votes_majority',
            'scdb_votes_minority', 'source', 'precedential_status', 'blocked',
        )


class OpinionFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    cluster = filters.RelatedFilter(OpinionClusterFilter, name='cluster')

    class Meta:
        model = Opinion
        fields = (
            'id', 'type', 'sha1', 'extracted_by_ocr'
        )
