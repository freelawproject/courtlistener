from rest_framework import serializers

from cl.api.utils import DynamicFieldsModelSerializer
from cl.people_db.models import Person, Position, RetentionEvent, \
    Education, School, PoliticalAffiliation, Source, ABARating
from cl.search.api_serializers import CourtSerializer


class SchoolSerializer(DynamicFieldsModelSerializer,
                       serializers.HyperlinkedModelSerializer):
    is_alias_of = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='school-detail',
        read_only=True
    )

    class Meta:
        model = School


class EducationSerializer(DynamicFieldsModelSerializer,
                          serializers.HyperlinkedModelSerializer):
    school = SchoolSerializer(many=False, read_only=True)
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        read_only=True,
    )

    class Meta:
        model = Education


class PoliticalAffiliationSerializer(DynamicFieldsModelSerializer,
                                     serializers.HyperlinkedModelSerializer):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        read_only=True,
    )

    class Meta:
        model = PoliticalAffiliation


class SourceSerializer(DynamicFieldsModelSerializer,
                       serializers.HyperlinkedModelSerializer):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        read_only=True,
    )

    class Meta:
        model = Source


class ABARatingSerializer(DynamicFieldsModelSerializer,
                          serializers.HyperlinkedModelSerializer):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        read_only=True,
    )

    class Meta:
        model = ABARating


class PersonSerializer(DynamicFieldsModelSerializer,
                       serializers.HyperlinkedModelSerializer):
    race = serializers.StringRelatedField(many=True)
    sources = SourceSerializer(many=True, read_only=True)
    aba_ratings = ABARatingSerializer(many=True, read_only=True)
    educations = EducationSerializer(many=True, read_only=True)
    positions = serializers.HyperlinkedRelatedField(
        many=True,
        view_name='position-detail',
        read_only=True,
    )
    political_affiliations = PoliticalAffiliationSerializer(
        many=True,
        read_only=True
    )
    is_alias_of = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        read_only=True
    )

    class Meta:
        model = Person


class RetentionEventSerializer(DynamicFieldsModelSerializer,
                               serializers.HyperlinkedModelSerializer):
    position = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='position-detail',
        read_only=True,
    )

    class Meta:
        model = RetentionEvent


class PositionSerializer(DynamicFieldsModelSerializer,
                         serializers.HyperlinkedModelSerializer):
    retention_events = RetentionEventSerializer(many=True, read_only=True)
    person = PersonSerializer(many=False, read_only=True)
    appointer = PersonSerializer(many=False, read_only=True)
    supervisor = PersonSerializer(many=False, read_only=True)
    predecessor = PersonSerializer(many=False, read_only=True)
    school = SchoolSerializer(many=False, read_only=True)
    court = CourtSerializer(many=False, read_only=True)

    # TODO: add clerks

    class Meta:
        model = Position
