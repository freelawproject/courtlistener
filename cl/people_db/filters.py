import rest_framework_filters as filters
from rest_framework_filters import FilterSet

from cl.api.utils import (
    DATETIME_LOOKUPS, DATE_LOOKUPS, BASIC_TEXT_LOOKUPS, INTEGER_LOOKUPS,
    ALL_TEXT_LOOKUPS
)
from cl.people_db.models import Person, Position, RetentionEvent, \
    Education, School, PoliticalAffiliation, Source, ABARating, \
    Race, Party, Attorney
from cl.search.filters import CourtFilter
from cl.search.models import Docket, Court, OpinionCluster, Opinion


class SourceFilter(FilterSet):
    class Meta:
        model = Source
        fields = {
            'id': ['exact'],
            'date_modified': DATETIME_LOOKUPS,
            'person': ['exact'],
        }


class ABARatingFilter(FilterSet):
    class Meta:
        model = ABARating
        fields = {
            'id': ['exact'],
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'year_rated': INTEGER_LOOKUPS,
            'rating': ['exact'],
            'person': ['exact'],
        }


class PoliticalAffiliationFilter(FilterSet):
    class Meta:
        model = PoliticalAffiliation
        fields = {
            'id': ['exact'],
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_start': DATE_LOOKUPS,
            'date_end': DATE_LOOKUPS,
            'political_party': ['exact'],
            'source': ['exact'],
            'person': ['exact'],
        }


class SchoolFilter(FilterSet):
    educations = filters.RelatedFilter(
        'cl.people_db.filters.EducationFilter',
        queryset=Education.objects.all(),
    )

    class Meta:
        model = School
        fields = {
            'id': ['exact'],
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'name': BASIC_TEXT_LOOKUPS,
            'ein': ['exact'],
        }


class EducationFilter(FilterSet):
    school = filters.RelatedFilter(
        SchoolFilter,
        queryset=School.objects.all(),
    )
    person = filters.RelatedFilter(
        'cl.people_db.filters.PersonFilter',
        queryset=Person.objects.all(),
    )

    class Meta:
        model = Education
        fields = {
            'id': ['exact'],
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'degree_year': ['exact'],
            'degree_detail': BASIC_TEXT_LOOKUPS,
            'degree_level': ['exact'],
            'person': ['exact'],
        }


class RetentionEventFilter(FilterSet):
    class Meta:
        model = RetentionEvent
        fields = {
            'id': ['exact'],
            'position': ['exact'],
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_retention': DATE_LOOKUPS,
            'retention_type': ['exact'],
            'votes_yes': INTEGER_LOOKUPS,
            'votes_no': INTEGER_LOOKUPS,
            'unopposed': ['exact'],
            'won': ['exact'],
        }


class PositionFilter(FilterSet):
    court = filters.RelatedFilter(
        CourtFilter,
        queryset=Court.objects.all()
    )
    retention_events = filters.RelatedFilter(
        RetentionEventFilter,
        queryset=RetentionEvent.objects.all(),
    )

    class Meta:
        model = Position
        fields = {
            'id': ['exact'],
            'position_type': ['exact'],
            'person': ['exact'],
            'appointer': ['exact'],
            'predecessor': ['exact'],
            'job_title': ALL_TEXT_LOOKUPS,
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_nominated': DATE_LOOKUPS,
            'date_elected': DATE_LOOKUPS,
            'date_recess_appointment': DATE_LOOKUPS,
            'date_referred_to_judicial_committee': DATE_LOOKUPS,
            'date_judicial_committee_action': DATE_LOOKUPS,
            'date_hearing': DATE_LOOKUPS,
            'date_confirmation': DATE_LOOKUPS,
            'date_start': DATE_LOOKUPS,
            'date_retirement': DATE_LOOKUPS,
            'date_termination': DATE_LOOKUPS,
            'judicial_committee_action': ['exact'],
            'nomination_process': ['exact'],
            'voice_vote': ['exact'],
            'votes_yes': INTEGER_LOOKUPS,
            'votes_no': INTEGER_LOOKUPS,
            'how_selected': ['exact'],
            'termination_reason': ['exact'],
            'location_city': BASIC_TEXT_LOOKUPS,
            'location_state': BASIC_TEXT_LOOKUPS,
        }


class PersonFilter(FilterSet):
    educations = filters.RelatedFilter(
        EducationFilter,
        queryset=Education.objects.all(),
    )
    political_affiliations = filters.RelatedFilter(
        PoliticalAffiliationFilter,
        queryset=PoliticalAffiliation.objects.all(),
    )
    sources = filters.RelatedFilter(
        SourceFilter,
        queryset=Source.objects.all(),
    )
    aba_ratings = filters.RelatedFilter(
        ABARatingFilter,
        queryset=ABARating.objects.all(),
    )
    positions = filters.RelatedFilter(
        PositionFilter,
        queryset=Position.objects.all(),
    )
    opinion_clusters_participating_judges = filters.RelatedFilter(
        'cl.search.filters.OpinionClusterFilter',
        'opinion_clusters_participating_judges',
        queryset=OpinionCluster.objects.all(),
    )
    opinion_clusters_non_participating_judges = filters.RelatedFilter(
        'cl.search.filters.OpinionClusterFilter',
        'opinion_clusters_non_participating_judges',
        queryset=OpinionCluster.objects.all(),
    )
    opinions_written = filters.RelatedFilter(
        'cl.search.filters.OpinionFilter',
        queryset=Opinion.objects.all(),
    )
    opinions_joined = filters.RelatedFilter(
        'cl.search.filters.OpinionFilter',
        queryset=Opinion.objects.all(),
    )

    race = filters.MultipleChoiceFilter(
        choices=Race.RACES,
        method='filter_race',
    )

    def filter_race(self, queryset, name, value):
        return queryset.filter(race__race__in=value)

    class Meta:
        model = Person
        fields = {
            'id': ['exact'],
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_dob': DATE_LOOKUPS,
            'date_dod': DATE_LOOKUPS,
            'name_first': BASIC_TEXT_LOOKUPS,
            'name_middle': BASIC_TEXT_LOOKUPS,
            'name_last': BASIC_TEXT_LOOKUPS,
            'name_suffix': BASIC_TEXT_LOOKUPS,
            'is_alias_of': ['exact'],
            'fjc_id': ['exact'],
            'ftm_eid': ['exact'],
            'dob_city': BASIC_TEXT_LOOKUPS,
            'dob_state': BASIC_TEXT_LOOKUPS,
            'dod_city': BASIC_TEXT_LOOKUPS,
            'dod_state': BASIC_TEXT_LOOKUPS,
            'gender': ['exact'],
        }


class PartyFilter(FilterSet):
    docket = filters.RelatedFilter(
        'cl.search.filters.DocketFilter',
        field_name='dockets',
        queryset=Docket.objects.all(),
    )
    attorney = filters.RelatedFilter(
        'cl.people_db.filters.AttorneyFilter',
        field_name='attorneys',
        queryset=Attorney.objects.all(),
    )

    class Meta:
        model = Party
        fields = {
            'id': ['exact'],
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'name': ALL_TEXT_LOOKUPS,
        }


class AttorneyFilter(FilterSet):
    docket = filters.RelatedFilter(
        'cl.search.filters.DocketFilter',
        field_name='roles__docket',
        queryset=Docket.objects.all(),
    )
    parties_represented = filters.RelatedFilter(
        PartyFilter,
        field_name='roles__party',
        queryset=Party.objects.all(),
    )

    class Meta:
        model = Attorney
        fields = {
            'id': ['exact'],
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'name': ALL_TEXT_LOOKUPS,
        }
