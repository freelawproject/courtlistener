from rest_framework import serializers

from cl.api.utils import DynamicFieldsModelSerializer
from cl.people_db.models import Person, Position, RetentionEvent, \
    Education, School, PoliticalAffiliation, Source, ABARating, Party
from cl.search.api_serializers import CourtSerializer


class SchoolSerializer(DynamicFieldsModelSerializer,
                       serializers.HyperlinkedModelSerializer):
    is_alias_of = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='school-detail',
        queryset=School.objects.all(),
    )

    class Meta:
        model = School
        fields = '__all__'


class EducationSerializer(DynamicFieldsModelSerializer,
                          serializers.HyperlinkedModelSerializer):
    school = SchoolSerializer(many=False, read_only=True)
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
    )

    class Meta:
        model = Education
        fields = '__all__'


class PoliticalAffiliationSerializer(DynamicFieldsModelSerializer,
                                     serializers.HyperlinkedModelSerializer):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
    )

    class Meta:
        model = PoliticalAffiliation
        fields = '__all__'


class SourceSerializer(DynamicFieldsModelSerializer,
                       serializers.HyperlinkedModelSerializer):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
    )

    class Meta:
        model = Source
        fields = '__all__'


class ABARatingSerializer(DynamicFieldsModelSerializer,
                          serializers.HyperlinkedModelSerializer):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
    )

    class Meta:
        model = ABARating
        fields = '__all__'


class PersonSerializer(DynamicFieldsModelSerializer,
                       serializers.HyperlinkedModelSerializer):
    race = serializers.StringRelatedField(many=True)
    sources = SourceSerializer(many=True, read_only=True)
    aba_ratings = ABARatingSerializer(many=True, read_only=True)
    educations = EducationSerializer(many=True, read_only=True)
    positions = serializers.HyperlinkedRelatedField(
        many=True,
        view_name='position-detail',
        queryset=Position.objects.all(),
    )
    political_affiliations = PoliticalAffiliationSerializer(many=True,
                                                            read_only=True)
    is_alias_of = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
    )

    class Meta:
        model = Person
        fields = '__all__'


class RetentionEventSerializer(DynamicFieldsModelSerializer,
                               serializers.HyperlinkedModelSerializer):
    position = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='position-detail',
        queryset=Position.objects.all(),
    )

    class Meta:
        model = RetentionEvent
        fields = '__all__'


class PositionSerializer(DynamicFieldsModelSerializer,
                         serializers.HyperlinkedModelSerializer):
    retention_events = RetentionEventSerializer(many=True, read_only=True)
    person = PersonSerializer(many=False, read_only=True)
    supervisor = PersonSerializer(many=False, read_only=True)
    predecessor = PersonSerializer(many=False, read_only=True)
    school = SchoolSerializer(many=False, read_only=True)
    court = CourtSerializer(many=False, read_only=True)

    # Needed b/c a self join.
    appointer = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='position-detail',
        queryset=Position.objects.all(),
    )

    class Meta:
        model = Position
        fields = '__all__'


class PartySerializer(DynamicFieldsModelSerializer,
                      serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Party
        fields = '__all__'
