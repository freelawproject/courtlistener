from typing import Any

import rest_framework_filters as filters
from django.db.models import Prefetch, QuerySet

from cl.api.utils import (
    ALL_TEXT_LOOKUPS,
    BASIC_TEXT_LOOKUPS,
    DATE_LOOKUPS,
    DATETIME_LOOKUPS,
    INTEGER_LOOKUPS,
    FilterManyToManyMixin,
    NoEmptyFilterSet,
)
from cl.people_db.lookup_utils import lookup_judge_by_name_components
from cl.people_db.models import (
    ABARating,
    Attorney,
    Education,
    Party,
    PartyType,
    Person,
    PoliticalAffiliation,
    Position,
    Race,
    RetentionEvent,
    Role,
    School,
    Source,
)
from cl.search.filters import CourtFilter
from cl.search.models import Court, Docket, Opinion, OpinionCluster


class SourceFilter(NoEmptyFilterSet):
    class Meta:
        model = Source
        fields = {
            "id": ["exact"],
            "date_modified": DATETIME_LOOKUPS,
            "person": ["exact"],
        }


class ABARatingFilter(NoEmptyFilterSet):
    class Meta:
        model = ABARating
        fields = {
            "id": INTEGER_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "year_rated": INTEGER_LOOKUPS,
            "rating": ["exact"],
            "person": ["exact"],
        }


class PoliticalAffiliationFilter(NoEmptyFilterSet):
    class Meta:
        model = PoliticalAffiliation
        fields = {
            "id": INTEGER_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "date_start": DATE_LOOKUPS,
            "date_end": DATE_LOOKUPS,
            "political_party": ["exact"],
            "source": ["exact"],
            "person": ["exact"],
        }


class SchoolFilter(NoEmptyFilterSet):
    educations = filters.RelatedFilter(
        "cl.people_db.filters.EducationFilter",
        queryset=Education.objects.all(),
    )

    class Meta:
        model = School
        fields = {
            "id": INTEGER_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "name": ALL_TEXT_LOOKUPS,
            "ein": ["exact"],
        }


class EducationFilter(NoEmptyFilterSet):
    school = filters.RelatedFilter(SchoolFilter, queryset=School.objects.all())
    person = filters.RelatedFilter(
        "cl.people_db.filters.PersonFilter", queryset=Person.objects.all()
    )

    class Meta:
        model = Education
        fields = {
            "id": INTEGER_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "degree_year": ["exact"],
            "degree_detail": BASIC_TEXT_LOOKUPS,
            "degree_level": ["exact"],
            "person": ["exact"],
        }


class RetentionEventFilter(NoEmptyFilterSet):
    class Meta:
        model = RetentionEvent
        fields = {
            "id": INTEGER_LOOKUPS,
            "position": ["exact"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "date_retention": DATE_LOOKUPS,
            "retention_type": ["exact"],
            "votes_yes": INTEGER_LOOKUPS,
            "votes_no": INTEGER_LOOKUPS,
            "unopposed": ["exact"],
            "won": ["exact"],
        }


class PositionFilter(NoEmptyFilterSet):
    court = filters.RelatedFilter(CourtFilter, queryset=Court.objects.all())
    retention_events = filters.RelatedFilter(
        RetentionEventFilter, queryset=RetentionEvent.objects.all()
    )

    class Meta:
        model = Position
        fields = {
            "id": INTEGER_LOOKUPS,
            "position_type": ["exact"],
            "person": ["exact"],
            "appointer": ["exact"],
            "predecessor": ["exact"],
            "job_title": ALL_TEXT_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "date_nominated": DATE_LOOKUPS,
            "date_elected": DATE_LOOKUPS,
            "date_recess_appointment": DATE_LOOKUPS,
            "date_referred_to_judicial_committee": DATE_LOOKUPS,
            "date_judicial_committee_action": DATE_LOOKUPS,
            "date_hearing": DATE_LOOKUPS,
            "date_confirmation": DATE_LOOKUPS,
            "date_start": DATE_LOOKUPS,
            "date_retirement": DATE_LOOKUPS,
            "date_termination": DATE_LOOKUPS,
            "judicial_committee_action": ["exact"],
            "nomination_process": ["exact"],
            "voice_vote": ["exact"],
            "votes_yes": INTEGER_LOOKUPS,
            "votes_no": INTEGER_LOOKUPS,
            "how_selected": ["exact"],
            "termination_reason": ["exact"],
            "location_city": BASIC_TEXT_LOOKUPS,
            "location_state": BASIC_TEXT_LOOKUPS,
        }


class PersonDisclosureFilter(NoEmptyFilterSet):
    """Filters for looking up judges in the disclosure pages"""

    fullname = filters.Filter(method="filter_fullname")

    def filter_fullname(
        self,
        queryset: QuerySet,
        name: str,
        value: str,
    ) -> QuerySet:
        return lookup_judge_by_name_components(queryset, value)

    class Meta:
        model = Person
        fields = {}


class PersonFilter(NoEmptyFilterSet):
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
        "cl.search.filters.OpinionClusterFilter",
        "opinion_clusters_participating_judges",
        queryset=OpinionCluster.objects.all(),
    )
    opinion_clusters_non_participating_judges = filters.RelatedFilter(
        "cl.search.filters.OpinionClusterFilter",
        "opinion_clusters_non_participating_judges",
        queryset=OpinionCluster.objects.all(),
    )
    opinions_written = filters.RelatedFilter(
        "cl.search.filters.OpinionFilter",
        queryset=Opinion.objects.all(),
    )
    opinions_joined = filters.RelatedFilter(
        "cl.search.filters.OpinionFilter",
        queryset=Opinion.objects.all(),
    )
    race = filters.MultipleChoiceFilter(
        choices=Race.RACES, method="filter_race"
    )

    def filter_race(
        self,
        queryset: QuerySet,
        name: str,
        value: str,
    ) -> QuerySet:
        return queryset.filter(race__race__in=value)

    class Meta:
        model = Person
        fields = {
            "id": INTEGER_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "date_dob": DATE_LOOKUPS,
            "date_dod": DATE_LOOKUPS,
            "name_first": BASIC_TEXT_LOOKUPS,
            "name_middle": BASIC_TEXT_LOOKUPS,
            "name_last": BASIC_TEXT_LOOKUPS,
            "name_suffix": BASIC_TEXT_LOOKUPS,
            "is_alias_of": ["exact"],
            "fjc_id": ["exact"],
            "ftm_eid": ["exact"],
            "dob_city": BASIC_TEXT_LOOKUPS,
            "dob_state": BASIC_TEXT_LOOKUPS,
            "dod_city": BASIC_TEXT_LOOKUPS,
            "dod_state": BASIC_TEXT_LOOKUPS,
            "gender": ["exact"],
        }


class PartyFilter(NoEmptyFilterSet, FilterManyToManyMixin):
    docket = filters.RelatedFilter(
        "cl.search.filters.DocketFilter",
        field_name="dockets",
        queryset=Docket.objects.all(),
        distinct=True,
    )
    attorney = filters.RelatedFilter(
        "cl.people_db.filters.AttorneyFilter",
        field_name="attorneys",
        queryset=Attorney.objects.all(),
        distinct=True,
    )
    filter_nested_results = filters.BooleanFilter(
        field_name="roles", method="filter_join_tables"
    )

    # Attributes for the mixin
    # **Important:** Keep this mapping up-to-date with any changes to
    # RelatedFilters or custom labels in this class to avoid unexpected
    # behavior.
    join_table_cleanup_mapping = {
        "dockets": "docket",
        "attorneys": "attorney",
    }

    class Meta:
        model = Party
        fields = {
            "id": INTEGER_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "name": ALL_TEXT_LOOKUPS,
        }

    def filter_join_tables(
        self, qs: QuerySet, name: str, value: bool
    ) -> QuerySet:
        """
        Filters a QuerySet based on a many-to-many relationship involving the
        `Role` and `PartyType` model.

        Args:
            qs: The original QuerySet to be filtered.
            name: The name of the field to filter on.
            value: The value of the request filter.

        Returns:
            The filtered QuerySet, prefetched with the filtered many-to-many
            relationship.
        """
        if not value:
            return qs

        filters = self.get_filters_for_join_table()
        if not filters:
            return qs

        prefetch_roles = Prefetch(
            name,
            queryset=Role.objects.filter(**filters),
            to_attr=f"filtered_roles",
        )
        prefetch_party_types = Prefetch(
            name,
            queryset=PartyType.objects.filter(
                **{
                    key: value
                    for key, value in filters.items()
                    if key.startswith("docket")
                }
            ),
            to_attr=f"filtered_party_types",
        )
        return qs.prefetch_related(prefetch_roles, prefetch_party_types)


class AttorneyFilter(NoEmptyFilterSet, FilterManyToManyMixin):
    docket = filters.RelatedFilter(
        "cl.search.filters.DocketFilter",
        field_name="roles__docket",
        queryset=Docket.objects.all(),
        distinct=True,
    )
    parties_represented = filters.RelatedFilter(
        PartyFilter,
        field_name="roles__party",
        queryset=Party.objects.all(),
        distinct=True,
    )
    filter_nested_results = filters.BooleanFilter(
        field_name="roles", method="filter_roles"
    )

    # Attributes for the mixin
    # **Important:** Keep this mapping up-to-date with any changes to
    # RelatedFilters or custom labels in this class to avoid unexpected
    # behavior.
    join_table_cleanup_mapping = {
        "roles__docket": "docket",
        "roles__party": "party",
    }

    class Meta:
        model = Attorney
        fields = {
            "id": INTEGER_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "name": ALL_TEXT_LOOKUPS,
        }

    def filter_roles(self, qs: QuerySet, name: str, value: bool) -> QuerySet:
        """
        Filters a QuerySet based on a many-to-many relationship involving the
        `Role` model.

        Args:
            qs: The original QuerySet to be filtered.
            name: The name of the many-to-many field to filter on.
            value: The value to filter the many-to-many relationship with.

        Returns:
            The filtered QuerySet, prefetched with the filtered many-to-many
            relationship.
        """
        if not value:
            return qs

        role_filters = self.get_filters_for_join_table()
        if not role_filters:
            return qs

        prefetch = Prefetch(
            name,
            queryset=Role.objects.filter(**role_filters),
            to_attr=f"filtered_roles",
        )
        return qs.prefetch_related(prefetch)
