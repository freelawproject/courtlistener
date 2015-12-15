from cl.judges.models import Judge
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
            'name_last', 'date_granularity_dob', 'date_granularity_dod',
            'dob_city', 'dob_state', 'dod_city', 'dod_state', 'gender',
        )
