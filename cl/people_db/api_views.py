from rest_framework import viewsets

from cl.api.utils import LoggingMixin
from cl.people_db.api_serializers import (
    PersonSerializer, PositionSerializer,
    RetentionEventSerializer, EducationSerializer, SchoolSerializer,
    PoliticalAffiliationSerializer,
    ABARatingSerializer, SourceSerializer,
)
from cl.people_db.filters import (
    PersonFilter, PositionFilter, RetentionEventFilter,
    EducationFilter, SchoolFilter,
    PoliticalAffiliationFilter, ABARatingFilter, SourceFilter,
)
from cl.people_db.models import Person, Position, RetentionEvent, \
    Education, School, PoliticalAffiliation, Source, ABARating


class PersonViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Person.objects.all()
    serializer_class = PersonSerializer
    filter_class = PersonFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_dob', 'date_dod',
    )


class PositionViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Position.objects.all()
    serializer_class = PositionSerializer
    filter_class = PositionFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_nominated', 'date_elected',
        'date_recess_appointment', 'date_referred_to_judicial_committee',
        'date_judicial_committee_action', 'date_hearing', 'date_confirmation',
        'date_start', 'date_retirement', 'date_termination',
    )


class RetentionEventViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = RetentionEvent.objects.all()
    serializer_class = RetentionEventSerializer
    filter_class = RetentionEventFilter
    ordering_fields = ('date_created', 'date_modified', 'date_retention')


class EducationViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Education.objects.all()
    serializer_class = EducationSerializer
    filter_class = EducationFilter
    ordering_fields = ('date_created', 'date_modified')


class SchoolViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    filter_class = SchoolFilter
    ordering_fields = ('date_created', 'date_modified')


class PoliticalAffiliationViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = PoliticalAffiliation.objects.all()
    serializer_class = PoliticalAffiliationSerializer
    filter_class = PoliticalAffiliationFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_start', 'date_end',
    )


class SourceViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Source.objects.all()
    serializer_class = SourceSerializer
    filter_class = SourceFilter
    ordering_fields = (
        'date_modified', 'date_accessed',
    )


class ABARatingViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = ABARating.objects.all()
    serializer_class = ABARatingSerializer
    filter_class = ABARatingFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_rated',
    )
