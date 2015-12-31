from rest_framework import viewsets

from cl.api.utils import LoggingMixin, BetaUsersReadOnly
from cl.judges.api_filters import (
    JudgeFilter, PositionFilter, PoliticianFilter, RetentionEventFilter,
    EducationFilter, SchoolFilter, CareerFilter, TitleFilter,
    PoliticalAffiliationFilter, ABARatingFilter, SourceFilter,
)
from cl.judges.api_serializers import (
    JudgeSerializer, PositionSerializer, PoliticianSerializer,
    RetentionEventSerializer, EducationSerializer, SchoolSerializer,
    CareerSerializer, TitleSerializer, PoliticalAffiliationSerializer,
    ABARatingSerializer, SourceSerializer,
)
from cl.judges.models import Judge, Position, Politician, RetentionEvent, \
    Education, School, Career, Title, PoliticalAffiliation, Source, ABARating


class JudgesViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Judge.objects.all()
    serializer_class = JudgeSerializer
    filter_class = JudgeFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_dob', 'date_dod',
    )
    permission_classes = (BetaUsersReadOnly,)


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
    permission_classes = (BetaUsersReadOnly,)


class PoliticianViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Politician.objects.all()
    serializer_class = PoliticianSerializer
    filter_class = PoliticianFilter
    ordering_fields = ('date_created', 'date_modified')
    permission_classes = (BetaUsersReadOnly,)


class RetentionEventViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = RetentionEvent.objects.all()
    serializer_class = RetentionEventSerializer
    filter_class = RetentionEventFilter
    ordering_fields = ('date_created', 'date_modified', 'date_retention')
    permission_classes = (BetaUsersReadOnly,)


class EducationViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Education.objects.all()
    serializer_class = EducationSerializer
    filter_class = EducationFilter
    ordering_fields = ('date_created', 'date_modified')
    permission_classes = (BetaUsersReadOnly,)


class SchoolViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    filter_class = SchoolFilter
    ordering_fields = ('date_created', 'date_modified')
    permission_classes = (BetaUsersReadOnly,)


class CareerViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Career.objects.all()
    serializer_class = CareerSerializer
    filter_class = CareerFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_start', 'date_end',
    )
    permission_classes = (BetaUsersReadOnly,)


class TitleViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Title.objects.all()
    serializer_class = TitleSerializer
    filter_class = TitleFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_start', 'date_end',
    )
    permission_classes = (BetaUsersReadOnly,)


class PoliticalAffiliationViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = PoliticalAffiliation.objects.all()
    serializer_class = PoliticalAffiliationSerializer
    filter_class = PoliticalAffiliationFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_start', 'date_end',
    )
    permission_classes = (BetaUsersReadOnly,)


class SourceViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = Source.objects.all()
    serializer_class = SourceSerializer
    filter_class = SourceFilter
    ordering_fields = (
        'date_modified', 'date_accessed',
    )
    permission_classes = (BetaUsersReadOnly,)


class ABARatingViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = ABARating.objects.all()
    serializer_class = ABARatingSerializer
    filter_class = ABARatingFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_rated',
    )
    permission_classes = (BetaUsersReadOnly,)
