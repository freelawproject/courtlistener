from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from cl.api.utils import HyperlinkedModelSerializerWithId
from cl.people_db.models import Person, Position, RetentionEvent, \
    Education, School, PoliticalAffiliation, Source, ABARating, Party, \
    Attorney, Role, PartyType
from cl.search.api_serializers import CourtSerializer


class SchoolSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    is_alias_of = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='school-detail',
        queryset=School.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = School
        fields = '__all__'


class EducationSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
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
                                     HyperlinkedModelSerializerWithId):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = PoliticalAffiliation
        fields = '__all__'


class SourceSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = Source
        fields = '__all__'


class ABARatingSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='person-detail',
        queryset=Person.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = ABARating
        fields = '__all__'


class PersonSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
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
                               HyperlinkedModelSerializerWithId):
    position = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='position-detail',
        queryset=Position.objects.all(),
        style={'base_template': 'input.html'},
    )

    class Meta:
        model = RetentionEvent
        fields = '__all__'


class PositionSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
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


class PartyTypeSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = PartyType
        fields = ('docket', 'name', 'date_terminated', 'extra_info',
                  'highest_offense_level_opening',
                  'highest_offense_level_terminated',)


class AttorneyRoleSerializer(serializers.HyperlinkedModelSerializer):
    role = serializers.ChoiceField(choices=Role.ATTORNEY_ROLES)

    class Meta:
        model = Role
        fields = ('role', 'docket', 'attorney', 'date_action')


class PartyRoleSerializer(serializers.HyperlinkedModelSerializer):
    role = serializers.ChoiceField(choices=Role.ATTORNEY_ROLES)

    class Meta:
        model = Role
        fields = ('role', 'docket', 'party', 'date_action')


class PartySerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    attorneys = AttorneyRoleSerializer(source='roles', many=True)
    party_types = PartyTypeSerializer(many=True)

    class Meta:
        model = Party
        fields = '__all__'


class AttorneySerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    parties_represented = PartyRoleSerializer(source='roles', many=True)

    class Meta:
        model = Attorney
        exclude = ('organizations',)
