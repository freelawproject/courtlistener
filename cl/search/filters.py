import rest_framework_filters as filters
from rest_framework_filters import FilterSet

from cl.api.utils import (
    INTEGER_LOOKUPS, DATETIME_LOOKUPS, DATE_LOOKUPS, ALL_TEXT_LOOKUPS
)
from cl.search.models import (
    Court, OpinionCluster, Docket, Opinion, OpinionsCited, SOURCES,
    DocketEntry, RECAPDocument, Tag,
)


class CourtFilter(FilterSet):
    dockets = filters.RelatedFilter('cl.search.filters.DocketFilter')
    jurisdiction = filters.MultipleChoiceFilter(choices=Court.JURISDICTIONS)

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


class TagFilter(FilterSet):
    class Meta:
        model = Tag
        fields = {
            'id': ['exact'],
            'name': ['exact'],
        }


class DocketFilter(FilterSet):
    court = filters.RelatedFilter(CourtFilter)
    clusters = filters.RelatedFilter("cl.search.filters.OpinionClusterFilter")
    docket_entries = filters.RelatedFilter("cl.search.filters.DocketEntryFilter")
    audio_files = filters.RelatedFilter('cl.audio.filters.AudioFilter')
    assigned_to = filters.RelatedFilter('cl.people_db.filters.PersonFilter')
    referred_to = filters.RelatedFilter('cl.people_db.filters.PersonFilter')
    parties = filters.RelatedFilter('cl.people_db.filters.PartyFilter')
    tags = filters.RelatedFilter(TagFilter)

    class Meta:
        model = Docket
        fields = {
            'id': ['exact'],
            'date_modified': DATETIME_LOOKUPS,
            'date_created': DATETIME_LOOKUPS,
            'date_cert_granted': DATE_LOOKUPS,
            'date_cert_denied': DATE_LOOKUPS,
            'date_argued': DATE_LOOKUPS,
            'date_reargued': DATE_LOOKUPS,
            'date_reargument_denied': DATE_LOOKUPS,
            'date_filed': DATE_LOOKUPS,
            'date_terminated': DATE_LOOKUPS,
            'date_last_filing': DATE_LOOKUPS,
            'docket_number': ['exact', 'startswith'],
            'nature_of_suit': ALL_TEXT_LOOKUPS,
            'pacer_case_id': ['exact'],
            'source': ['exact', 'in'],
            'date_blocked': DATE_LOOKUPS,
            'blocked': ['exact'],
        }


class OpinionFilter(FilterSet):
    # Cannot to reference to opinions_cited here, due to it being a self join,
    # which is not supported (possibly for good reasons?)
    cluster = filters.RelatedFilter('cl.search.filters.OpinionClusterFilter')
    author = filters.RelatedFilter('cl.people_db.filters.PersonFilter')
    joined_by = filters.RelatedFilter('cl.people_db.filters.PersonFilter')
    type = filters.MultipleChoiceFilter(choices=Opinion.OPINION_TYPES)

    class Meta:
        model = Opinion
        fields = {
            'id': INTEGER_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_created': DATETIME_LOOKUPS,
            'sha1': ['exact'],
            'extracted_by_ocr': ['exact'],
            'per_curiam': ['exact'],
        }


class OpinionClusterFilter(FilterSet):
    docket = filters.RelatedFilter(DocketFilter)
    panel = filters.RelatedFilter('cl.people_db.filters.PersonFilter')
    non_participating_judges = filters.RelatedFilter(
        'cl.people_db.filters.PersonFilter',
    )
    sub_opinions = filters.RelatedFilter(OpinionFilter)
    source = filters.MultipleChoiceFilter(choices=SOURCES)

    class Meta:
        model = OpinionCluster
        fields = {
            'id': ['exact'],
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_filed': DATE_LOOKUPS,
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


class OpinionsCitedFilter(FilterSet):
    citing_opinion = filters.RelatedFilter(OpinionFilter)
    cited_opinion = filters.RelatedFilter(OpinionFilter)

    class Meta:
        model = OpinionsCited
        fields = {
            'id': ['exact'],
        }


class DocketEntryFilter(FilterSet):
    docket = filters.RelatedFilter(DocketFilter)
    recap_documents = filters.RelatedFilter(
        'cl.search.filters.RECAPDocumentFilter'
    )
    tags = filters.RelatedFilter(TagFilter)

    class Meta:
        model = DocketEntry
        fields = {
            'id': ['exact'],
            'entry_number': INTEGER_LOOKUPS,
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_filed': DATE_LOOKUPS,
        }


class RECAPDocumentFilter(FilterSet):
    docket_entry = filters.RelatedFilter(DocketEntryFilter)
    tags = filters.RelatedFilter(TagFilter)

    class Meta:
        model = RECAPDocument
        fields = {
            'id': ['exact'],
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_upload': DATETIME_LOOKUPS,
            'document_type': ['exact'],
            'document_number': ['exact', 'gte', 'gt', 'lte', 'lt'],
            'pacer_doc_id': ['exact', 'in'],
            'is_available': ['exact'],
            'sha1': ['exact'],
            'ocr_status': INTEGER_LOOKUPS,
            'is_free_on_pacer': ['exact'],
        }
