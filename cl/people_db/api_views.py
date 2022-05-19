from django.db.models import Exists, OuterRef, Prefetch
from rest_framework import viewsets

from cl.api.pagination import TinyAdjustablePagination
from cl.api.utils import LoggingMixin, RECAPUsersReadOnly
from cl.disclosures.models import FinancialDisclosure
from cl.people_db.api_serializers import (
    ABARatingSerializer,
    AttorneySerializer,
    EducationSerializer,
    PartySerializer,
    PersonDisclosureSerializer,
    PersonSerializer,
    PoliticalAffiliationSerializer,
    PositionSerializer,
    RetentionEventSerializer,
    SchoolSerializer,
    SourceSerializer,
)
from cl.people_db.filters import (
    ABARatingFilter,
    AttorneyFilter,
    EducationFilter,
    PartyFilter,
    PersonDisclosureFilter,
    PersonFilter,
    PoliticalAffiliationFilter,
    PositionFilter,
    RetentionEventFilter,
    SchoolFilter,
    SourceFilter,
)
from cl.people_db.models import (
    ABARating,
    Attorney,
    Education,
    Party,
    Person,
    PoliticalAffiliation,
    Position,
    RetentionEvent,
    School,
    Source,
)


class PersonDisclosureViewSet(viewsets.ModelViewSet):
    queryset = (
        Person.objects.filter(
            # Only return people that have disclosure sub-objects
            Exists(
                FinancialDisclosure.objects.filter(
                    person=OuterRef("pk"),
                ).only("pk")
            ),
            # Don't include aliases
            is_alias_of=None,
        )
        .prefetch_related(
            # Prefetch disclosures and positions to avoid query floods
            Prefetch(
                "financial_disclosures",
                queryset=FinancialDisclosure.objects.all()
                .only("year", "id", "person_id")
                .order_by("-year"),
                to_attr="disclosures",
            ),
            Prefetch(
                "positions",
                queryset=Position.objects.filter(court__isnull=False)
                .select_related("court")
                .only("pk", "court_id", "person_id")
                .order_by("-date_start"),
                to_attr="court_positions",
            ),
        )
        .only(
            "name_first",
            "name_middle",
            "name_last",
            "name_suffix",
            "has_photo",
            "date_dob",
            "date_granularity_dob",
            "slug",
        )
        .order_by("-id")
    )
    serializer_class = PersonDisclosureSerializer
    filterset_class = PersonDisclosureFilter
    pagination_class = TinyAdjustablePagination
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "name_last",
    )


class PersonViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = (
        Person.objects.all()
        .prefetch_related(
            "positions",
            "educations",
            "political_affiliations",
            "sources",
            "aba_ratings",
            "race",
        )
        .order_by("-id")
    )
    serializer_class = PersonSerializer
    filterset_class = PersonFilter
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "date_dob",
        "date_dod",
        "name_last",
    )


class PositionViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Position.objects.all().order_by("-id")
    serializer_class = PositionSerializer
    filterset_class = PositionFilter
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "date_nominated",
        "date_elected",
        "date_recess_appointment",
        "date_referred_to_judicial_committee",
        "date_judicial_committee_action",
        "date_hearing",
        "date_confirmation",
        "date_start",
        "date_retirement",
        "date_termination",
    )


class RetentionEventViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = RetentionEvent.objects.all().order_by("-id")
    serializer_class = RetentionEventSerializer
    filterset_class = RetentionEventFilter
    ordering_fields = ("id", "date_created", "date_modified", "date_retention")


class EducationViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Education.objects.all().order_by("-id")
    serializer_class = EducationSerializer
    filterset_class = EducationFilter
    ordering_fields = ("id", "date_created", "date_modified")


class SchoolViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = School.objects.all().order_by("-id")
    serializer_class = SchoolSerializer
    filterset_class = SchoolFilter
    ordering_fields = ("id", "date_created", "date_modified", "name")


class PoliticalAffiliationViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = PoliticalAffiliation.objects.all().order_by("-id")
    serializer_class = PoliticalAffiliationSerializer
    filterset_class = PoliticalAffiliationFilter
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "date_start",
        "date_end",
    )


class SourceViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Source.objects.all().order_by("-id")
    serializer_class = SourceSerializer
    filterset_class = SourceFilter
    ordering_fields = (
        "id",
        "date_modified",
        "date_accessed",
    )


class ABARatingViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = ABARating.objects.all().order_by("-id")
    serializer_class = ABARatingSerializer
    filterset_class = ABARatingFilter
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "year_rated",
    )


class PartyViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (RECAPUsersReadOnly,)
    serializer_class = PartySerializer
    filterset_class = PartyFilter
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
    )
    queryset = Party.objects.prefetch_related(
        "party_types__criminal_counts",
        "party_types__criminal_complaints",
        "roles",
    ).order_by("-id")


class AttorneyViewSet(LoggingMixin, viewsets.ModelViewSet):
    permission_classes = (RECAPUsersReadOnly,)
    serializer_class = AttorneySerializer
    filterset_class = AttorneyFilter
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
    )
    queryset = Attorney.objects.prefetch_related("roles").order_by("-id")
