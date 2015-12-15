from cl.judges.models import Judge, Position, Politician, RetentionEvent, \
    Education, School, Career, Title, PoliticalAffiliation, Source, ABARating
from rest_framework import serializers


class SchoolSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = School


class EducationSerializer(serializers.HyperlinkedModelSerializer):
    school = SchoolSerializer(many=False, read_only=True)

    class Meta:
        model = Education


class CareerSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Career


class TitleSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Title


class PoliticalAffiliationSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = PoliticalAffiliation


class SourceSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Source


class ABARatingSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = ABARating


class JudgeSerializer(serializers.HyperlinkedModelSerializer):
    race = serializers.StringRelatedField(many=True)
    positions = serializers.HyperlinkedRelatedField(
        many=True,
        view_name='position-detail',
        read_only=True,
    )
    educations = EducationSerializer(many=True, read_only=True)
    careers = CareerSerializer(many=True, read_only=True)
    titles = TitleSerializer(many=True, read_only=True)
    political_affiliations = PoliticalAffiliationSerializer(many=True,
                                                            read_only=True)
    sources = SourceSerializer(many=True, read_only=True)
    aba_ratings = ABARatingSerializer(many=True, read_only=True)

    class Meta:
        model = Judge


class PoliticianSerializer(serializers.HyperlinkedModelSerializer):
    political_affiliations = PoliticalAffiliationSerializer(many=True, read_only=True)

    class Meta:
        model = Politician


class RetentionEventSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = RetentionEvent


class PositionSerializer(serializers.HyperlinkedModelSerializer):
    appointer = PoliticianSerializer(many=False, read_only=True)
    retention_events = RetentionEventSerializer(many=True, read_only=True)

    class Meta:
        model = Position
