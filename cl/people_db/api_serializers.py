from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from cl.people_db.models import Person, Position, RetentionEvent, \
    Education, School, PoliticalAffiliation, Source, ABARating, Party, \
    Attorney, Role
from cl.search.api_serializers import CourtSerializer


class SchoolSerializer(DynamicFieldsMixin,
                       serializers.HyperlinkedModelSerializer):
    is_alias_of = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='school-detail',
        queryset=School.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = School
        fields = '__all__'


class EducationSerializer(DynamicFieldsMixin,
                          serializers.HyperlinkedModelSerializer):
    school = SchoolSerializer(many=False, read_only=True)
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = Education
        fields = '__all__'


class PoliticalAffiliationSerializer(DynamicFieldsMixin,
                                     serializers.HyperlinkedModelSerializer):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = PoliticalAffiliation
        fields = '__all__'


class SourceSerializer(DynamicFieldsMixin,
                       serializers.HyperlinkedModelSerializer):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = Source
        fields = '__all__'


class ABARatingSerializer(DynamicFieldsMixin,
                          serializers.HyperlinkedModelSerializer):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = ABARating
        fields = '__all__'


class PersonSerializer(DynamicFieldsMixin,
                       serializers.HyperlinkedModelSerializer):
    race = serializers.StringRelatedField(many=True)
    sources = SourceSerializer(many=True, read_only=True)
    aba_ratings = ABARatingSerializer(many=True, read_only=True)
    educations = EducationSerializer(many=True, read_only=True)
    positions = serializers.HyperlinkedRelatedField(
        many=True,
        view_name='position-detail',
        queryset=Position.objects.all(),
        style={'base_template': 'input.html'},
    )
    political_affiliations = PoliticalAffiliationSerializer(many=True,
                                                            read_only=True)
    is_alias_of = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = Person
        fields = '__all__'


class RetentionEventSerializer(DynamicFieldsMixin,
                               serializers.HyperlinkedModelSerializer):
    position = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='position-detail',
        queryset=Position.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = RetentionEvent
        fields = '__all__'


class PositionSerializer(DynamicFieldsMixin,
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
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = Position
        fields = '__all__'


class AttorneyRoleSerializer(serializers.HyperlinkedModelSerializer):
    role_name = serializers.ChoiceField(source='role',
                                        choices=Role.ATTORNEY_ROLES)

    class Meta:
        model = Role
        fields = ('role_name', 'docket', 'attorney')


class PartySerializer(DynamicFieldsMixin,
                      serializers.HyperlinkedModelSerializer):
    attorneys = AttorneyRoleSerializer(source='roles', many=True)

    class Meta:
        model = Party
        fields = '__all__'


class AttorneySerializer(DynamicFieldsMixin,
                         serializers.HyperlinkedModelSerializer):

    class Meta:
        model = Attorney
        exclude = ('organizations',)
