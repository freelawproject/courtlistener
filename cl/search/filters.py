import rest_framework_filters as filters

from cl.api.utils import INTEGER_LOOKUPS, DATETIME_LOOKUPS, DATE_LOOKUPS
from cl.search.models import (
    Court, OpinionCluster, Docket, Opinion, OpinionsCited, SOURCES,
    JURISDICTIONS)


class CourtFilter(filters.FilterSet):
    dockets = filters.RelatedFilter(
        'cl.search.filters.DocketFilter',
        name='dockets',
    )
    jurisdiction = filters.MultipleChoiceFilter(
        choices=JURISDICTIONS,
    )

    class Meta:
        model = Court
        fields = {
            'id': ['exact'],
            'date_modified': DATETIME_LOOKUPS,
            'in_use': ['exact'],
            'has_opinion_scraper': ['exact'],
            'has_oral_argument_scraper': ['exact'],
            'position': INTEGER_LOOKUPS,
            'start_date': DATE_LOOKUPS,
            'end_date': DATE_LOOKUPS,
        }


class DocketFilter(filters.FilterSet):
    court = filters.RelatedFilter(CourtFilter, name='court')
    clusters = filters.RelatedFilter(
        "cl.search.filters.OpinionClusterFilter",
        name='clusters',
    )
    audio_files = filters.RelatedFilter(
        'cl.audio.filters.AudioFilter',
        name='audio_files',
    )

    class Meta:
        model = Docket
        fields = {
            'id': ['exact'],
            'date_modified': DATETIME_LOOKUPS,
            'date_created': DATETIME_LOOKUPS,
            'date_argued': DATE_LOOKUPS,
            'date_reargued': DATE_LOOKUPS,
            'date_reargument_denied': DATE_LOOKUPS,
            'docket_number': ['exact'],
            'date_blocked': DATE_LOOKUPS,
            'blocked': ['exact'],
        }


class OpinionFilter(filters.FilterSet):
    # Cannot to reference to opinions_cited here, due to it being a self join,
    # which is not supported (possibly for good reasons?)
    cluster = filters.RelatedFilter(
        'cl.search.filters.OpinionClusterFilter',
        name='cluster',
    )
    author = filters.RelatedFilter(
        'cl.people_db.filters.PersonFilter',
        name='author',
    )
    joined_by = filters.RelatedFilter(
        'cl.people_db.filters.PersonFilter',
        name='joined_by',
    )
    type = filters.MultipleChoiceFilter(
        choices=Opinion.OPINION_TYPES,
    )

    class Meta:
        model = Opinion
        fields = {
            'id': ['exact'],
            'date_modified': DATETIME_LOOKUPS,
            'date_created': DATETIME_LOOKUPS,
            'sha1': ['exact'],
            'extracted_by_ocr': ['exact'],
        }


class OpinionClusterFilter(filters.FilterSet):
    docket = filters.RelatedFilter(DocketFilter, name='docket')
    non_participating_judges = filters.RelatedFilter(
        'cl.people_db.filters.PersonFilter',
        name='non_participating_judges',
    )
    panel = filters.RelatedFilter(
        'cl.people_db.filters.PersonFilter',
        name='panel',
    )
    sub_opinions = filters.RelatedFilter(
        OpinionFilter,
        name='sub_opinions',
    )
    source = filters.MultipleChoiceFilter(
        choices=SOURCES,
    )

    class Meta:
        model = OpinionCluster
        fields = {
            'id': ['exact'],
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_filed': DATE_LOOKUPS,
            'per_curiam': ['exact'],
            'citation_id': ['exact'],
            'federal_cite_one': ['exact'],
            'federal_cite_two': ['exact'],
            'federal_cite_three': ['exact'],
            'state_cite_one': ['exact'],
            'state_cite_two': ['exact'],
            'state_cite_three': ['exact'],
            'state_cite_regional': ['exact'],
            'specialty_cite_one': ['exact'],
            'scotus_early_cite': ['exact'],
            'lexis_cite': ['exact'],
            'westlaw_cite': ['exact'],
            'neutral_cite': ['exact'],
            'scdb_id': ['exact'],
            'scdb_decision_direction': ['exact'],
            'scdb_votes_majority': INTEGER_LOOKUPS,
            'scdb_votes_minority': INTEGER_LOOKUPS,
            'citation_count': INTEGER_LOOKUPS,
            'precedential_status': ['exact'],
            'date_blocked': DATE_LOOKUPS,
            'blocked': ['exact'],
        }


class OpinionsCitedFilter(filters.FilterSet):
    citing_opinion = filters.RelatedFilter(
            OpinionFilter,
            name='citing_opinion',
    )
    cited_opinion = filters.RelatedFilter(
            OpinionFilter,
            name='cited_opinion',
    )

    class Meta:
        model = OpinionsCited
        fields = {
            'id': ['exact'],
        }
