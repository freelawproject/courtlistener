from cl.judges.filters import (
    JudgeFilter, PositionFilter, PoliticianFilter, RetentionEventFilter,
    EducationFilter, SchoolFilter, CareerFilter, TitleFilter,
    PoliticalAffiliationFilter, ABARatingFilter, SourceFilter,
)
from cl.judges.serializers import (
    JudgeSerializer, PositionSerializer, PoliticianSerializer,
    RetentionEventSerializer, EducationSerializer, SchoolSerializer,
    CareerSerializer, TitleSerializer, PoliticalAffiliationSerializer,
    ABARatingSerializer, SourceSerializer,
)
from cl.judges.models import Judge, Position, Politician, RetentionEvent, \
    Education, School, Career, Title, PoliticalAffiliation, Source, ABARating
from rest_framework import viewsets


class JudgesViewSet(viewsets.ModelViewSet):
    queryset = Judge.objects.all()
    serializer_class = JudgeSerializer
    filter_class = JudgeFilter


class PositionViewSet(viewsets.ModelViewSet):
    queryset = Position.objects.all()
    serializer_class = PositionSerializer
    filter_class = PositionFilter


class PoliticianViewSet(viewsets.ModelViewSet):
    queryset = Politician.objects.all()
    serializer_class = PoliticianSerializer
    filter_class = PoliticianFilter


class RetentionEventViewSet(viewsets.ModelViewSet):
    queryset = RetentionEvent.objects.all()
    serializer_class = RetentionEventSerializer
    filter_class = RetentionEventFilter


class EducationViewSet(viewsets.ModelViewSet):
    queryset = Education.objects.all()
    serializer_class = EducationSerializer
    filter_class = EducationFilter


class SchoolViewSet(viewsets.ModelViewSet):
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    filter_class = SchoolFilter


class CareerViewSet(viewsets.ModelViewSet):
    queryset = Career.objects.all()
    serializer_class = CareerSerializer
    filter_class = CareerFilter


class TitleViewSet(viewsets.ModelViewSet):
    queryset = Title.objects.all()
    serializer_class = TitleSerializer
    filter_class = TitleFilter


class PoliticalAffiliationViewSet(viewsets.ModelViewSet):
    queryset = PoliticalAffiliation.objects.all()
    serializer_class = PoliticalAffiliationSerializer
    filter_class = PoliticalAffiliationFilter


class SourceViewSet(viewsets.ModelViewSet):
    queryset = Source.objects.all()
    serializer_class = SourceSerializer
    filter_class = SourceFilter


class ABARatingViewSet(viewsets.ModelViewSet):
    queryset = ABARating.objects.all()
    serializer_class = ABARatingSerializer
    filter_class = ABARatingFilter
