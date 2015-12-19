import rest_framework_filters as filters
from cl.api.utils import DATETIME_LOOKUPS, \
    DATE_LOOKUPS, BASIC_TEXT_LOOKUPS, ALL_TEXT_LOOKUPS, INTEGER_LOOKUPS
from cl.judges.models import Judge, Position, Politician, RetentionEvent, \
    Education, School, Career, Title, PoliticalAffiliation, Source, ABARating, \
    Race
from cl.search.filters import CourtFilter


class SourceFilter(filters.FilterSet):
    class Meta:
        model = Source
        fields = {
            'date_modified': DATETIME_LOOKUPS,
            'judge': ['exact'],
        }


class ABARatingFilter(filters.FilterSet):
    class Meta:
        model = ABARating
        fields = {
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_rated': DATE_LOOKUPS,
            'rating': ['exact'],
            'judge': ['exact'],
        }


class PoliticalAffiliationFilter(filters.FilterSet):
    class Meta:
        model = PoliticalAffiliation
        fields = {
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_start': DATE_LOOKUPS,
            'date_end': DATE_LOOKUPS,
            'political_party': ['exact'],
            'source': ['exact'],
            'judge': ['exact'],
            'politician': ['exact'],
        }


class TitleFilter(filters.FilterSet):
    class Meta:
        model = Title
        fields = {
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_start': DATE_LOOKUPS,
            'date_end': DATE_LOOKUPS,
            'title_name': ['exact'],
            'judge': ['exact'],
        }


class CareerFilter(filters.FilterSet):
    class Meta:
        model = Career
        fields = {
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'date_start': DATE_LOOKUPS,
            'date_end': DATE_LOOKUPS,
            'job_type': ['exact'],
            'job_title': ALL_TEXT_LOOKUPS,
            'organization_name': ALL_TEXT_LOOKUPS,
            'judge': ['exact'],
        }


class SchoolFilter(filters.FilterSet):
    class Meta:
        model = School
        fields = {
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'name': BASIC_TEXT_LOOKUPS,
            'is_alias_of': ['exact'],
            'unit_id': ['exact'],
            'ein': ['exact'],
            'ope_id': ['exact'],
        }


class EducationFilter(filters.FilterSet):
    school = filters.RelatedFilter(SchoolFilter, name='school')

    class Meta:
        model = Education
        fields = {
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'degree_year': ['exact'],
            'degree': BASIC_TEXT_LOOKUPS,
            'judge': ['exact'],
        }


class PoliticianFilter(filters.FilterSet):
    political_affiliations = filters.RelatedFilter(
            PoliticalAffiliationFilter, name='political_affiliations')

    class Meta:
        model = Politician
        fields = {
            'date_modified': DATETIME_LOOKUPS,
            'date_created': DATETIME_LOOKUPS,
            'name_first': BASIC_TEXT_LOOKUPS,
            'name_middle': BASIC_TEXT_LOOKUPS,
            'name_last': BASIC_TEXT_LOOKUPS,
            'office': ['exact'],
        }


class RetentionEventFilter(filters.FilterSet):
    # date_retention = filters.AllLookupsFilter(name='date_retention')

    class Meta:
        model = RetentionEvent
        fields = {
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


class PositionFilter(filters.FilterSet):
    court = filters.RelatedFilter(CourtFilter, name='court')
    retention_events = filters.RelatedFilter(
            RetentionEventFilter, name='retention_events')
    appointer = filters.RelatedFilter(PoliticianFilter, name='appointer')

    class Meta:
        model = Position
        fields = {
            'judge': ['exact'],
            'predecessor': ['exact'],
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
        }


class JudgeFilter(filters.FilterSet):
    # filter_overrides = default_filter_overrides
    educations = filters.RelatedFilter(EducationFilter, name='educations')
    careers = filters.RelatedFilter(CareerFilter, name='careers')
    titles = filters.RelatedFilter(TitleFilter, name='titles')
    political_affiliations = filters.RelatedFilter(
            PoliticalAffiliationFilter, name='political_affiliations')
    sources = filters.RelatedFilter(SourceFilter, name='sources')
    aba_ratings = filters.RelatedFilter(ABARatingFilter, name='aba_ratings')
    positions = filters.RelatedFilter(PositionFilter, name='positions')
    race = filters.MultipleChoiceFilter(
        choices=Race.RACES,
        action=lambda queryset, value:
            queryset.filter(race__race__in=value)
    )

    class Meta:
        model = Judge
        fields = {
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
            'dob_city': BASIC_TEXT_LOOKUPS,
            'dob_state': BASIC_TEXT_LOOKUPS,
            'dod_city': BASIC_TEXT_LOOKUPS,
            'dod_state': BASIC_TEXT_LOOKUPS,
            'gender': ['exact'],
        }
