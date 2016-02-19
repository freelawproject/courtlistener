from rest_framework import serializers

from cl.api.utils import DynamicFieldsModelSerializer
from cl.people_db.models import Person, Position, RetentionEvent, \
    Education, School, PoliticalAffiliation, Source, ABARating


class SchoolSerializer(DynamicFieldsModelSerializer,
                       serializers.HyperlinkedModelSerializer):
    class Meta:
        model = School


class EducationSerializer(DynamicFieldsModelSerializer,
                          serializers.HyperlinkedModelSerializer):
    school = SchoolSerializer(many=False, read_only=True)

    class Meta:
        model = Education

class PoliticalAffiliationSerializer(DynamicFieldsModelSerializer,
                                     serializers.HyperlinkedModelSerializer):
    class Meta:
        model = PoliticalAffiliation


class SourceSerializer(DynamicFieldsModelSerializer,
                       serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Source


class ABARatingSerializer(DynamicFieldsModelSerializer,
                          serializers.HyperlinkedModelSerializer):
    class Meta:
        model = ABARating


class PersonSerializer(DynamicFieldsModelSerializer,
                      serializers.HyperlinkedModelSerializer):
    race = serializers.StringRelatedField(many=True)
    positions = serializers.HyperlinkedRelatedField(
        many=True,
        view_name='position-detail',
        read_only=True,
    )
    educations = EducationSerializer(many=True, read_only=True)    
    political_affiliations = PoliticalAffiliationSerializer(many=True,
                                                            read_only=True)
    sources = SourceSerializer(many=True, read_only=True)
    aba_ratings = ABARatingSerializer(many=True, read_only=True)

    class Meta:
        model = Person

class RetentionEventSerializer(DynamicFieldsModelSerializer,
                               serializers.HyperlinkedModelSerializer):
    class Meta:
        model = RetentionEvent


class PositionSerializer(DynamicFieldsModelSerializer,
                         serializers.HyperlinkedModelSerializer):
    appointer = PersonSerializer(many=False, read_only=True)
    retention_events = RetentionEventSerializer(many=True, read_only=True)
    # TODO: add clerks 

    class Meta:
        model = Position
