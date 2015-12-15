from cl.judges.models import Judge, Position, Politician, RetentionEvent, \
    Education, School, Career, Title, PoliticalAffiliation, Source, ABARating
import rest_framework_filters as filters


class JudgeFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_dob = filters.AllLookupsFilter(name='date_created')
    date_dod = filters.AllLookupsFilter(name='date_created')

    class Meta:
        model = Judge
        fields = (
            'race', 'is_alias_of', 'fjc_id', 'name_first', 'name_middle',
            'name_last', 'dob_city', 'dob_state', 'dod_city', 'dod_state',
            'gender',
        )


class PositionFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_nominated = filters.AllLookupsFilter(name='date_nominated')
    date_elected = filters.AllLookupsFilter(name='date_elected')
    date_recess_appointment = filters.AllLookupsFilter(
            name='date_recess_appointment')
    date_referred_to_judicial_committee = filters.AllLookupsFilter(
            name='date_referred_to_judicial_committee')
    date_judicial_committee_action = filters.AllLookupsFilter(
        name='date_judicial_committee_action')
    date_hearing = filters.AllLookupsFilter(name='date_hearing')
    date_confirmation = filters.AllLookupsFilter(name='date_confirmation')
    date_start = filters.AllLookupsFilter(name='date_start')
    date_retirement = filters.AllLookupsFilter(name='date_retirement')
    date_termination = filters.AllLookupsFilter(name='date_termination')

    class Meta:
        model = Position
        fields = (
            'judicial_committee_action', 'nomination_process', 'voice_vote',
            'votes_yes', 'votes_no', 'how_selected', 'termination_reason',
        )


class PoliticianFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')

    class Meta:
        model = Politician
        fields = (
            'name_first', 'name_middle', 'name_last', 'office',
        )


class RetentionEventFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_retention = filters.AllLookupsFilter(name='date_retention')

    class Meta:
        model = RetentionEvent
        fields = (
            'retention_type', 'votes_yes', 'votes_no', 'unopposed', 'won',
        )


class EducationFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')

    class Meta:
        model = Education
        fields = (
            'degree_year',
        )


class SchoolFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')

    class Meta:
        model = School
        fields = (
            'name', 'is_alias_of', 'unit_id', 'ein', 'ope_id',
        )


class CareerFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_start = filters.AllLookupsFilter(name='date_start')
    date_end = filters.AllLookupsFilter(name='date_end')

    class Meta:
        model = Career
        fields = (
            'job_type', 'job_title', 'organization_name',
        )


class TitleFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_start = filters.AllLookupsFilter(name='date_start')
    date_end = filters.AllLookupsFilter(name='date_end')

    class Meta:
        model = Title
        fields = (
            'title_name',
        )


class PoliticalAffiliationFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_start = filters.AllLookupsFilter(name='date_start')
    date_end = filters.AllLookupsFilter(name='date_end')

    class Meta:
        model = PoliticalAffiliation
        fields = (
            'political_party', 'source',
        )


class SourceFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_accessed = filters.AllLookupsFilter(name='date_accessed')

    class Meta:
        model = Source


class ABARatingFilter(filters.FilterSet):
    date_modified = filters.AllLookupsFilter(name='date_modified')
    date_created = filters.AllLookupsFilter(name='date_created')
    date_rated = filters.AllLookupsFilter(name='date_rated')

    class Meta:
        model = ABARating
        fields = (
            'rating',
        )
