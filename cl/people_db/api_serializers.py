from drf_dynamic_fields import DynamicFieldsMixin
from judge_pics.search import ImageSizes, portrait
from rest_framework import serializers

from cl.api.utils import HyperlinkedModelSerializerWithId
from cl.disclosures.utils import make_disclosure_year_range
from cl.people_db.models import (
    ABARating,
    Attorney,
    CriminalComplaint,
    CriminalCount,
    Education,
    Party,
    PartyType,
    Person,
    PoliticalAffiliation,
    Position,
    RetentionEvent,
    Role,
    School,
    Source,
)
from cl.search.api_serializers import CourtSerializer


class SchoolSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    is_alias_of = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="school-detail",
        queryset=School.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = School
        fields = "__all__"


class EducationSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    school = SchoolSerializer(many=False, read_only=True)
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="person-detail",
        queryset=Person.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = Education
        fields = "__all__"


class PoliticalAffiliationSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="person-detail",
        queryset=Person.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = PoliticalAffiliation
        fields = "__all__"


class SourceSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="person-detail",
        queryset=Person.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = Source
        fields = "__all__"


class ABARatingSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="person-detail",
        queryset=Person.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = ABARating
        fields = "__all__"


class PersonDisclosureSerializer(
    DynamicFieldsMixin,
    HyperlinkedModelSerializerWithId,
):
    position_str = serializers.SerializerMethodField()
    name_full = serializers.CharField()
    disclosure_years = serializers.SerializerMethodField()
    thumbnail_path = serializers.SerializerMethodField()
    newest_disclosure_url = serializers.SerializerMethodField()

    def get_position_str(self, obj: Person) -> str:
        """Make a simple string of a judge's most recent position

        Assumes you have the judge's position prefetched in the `positions`
        attr.
        """
        if len(obj.court_positions) > 0:
            return obj.court_positions[0].court.short_name
        return ""

    def get_disclosure_years(self, obj: Person) -> str:
        return make_disclosure_year_range(obj)

    def get_thumbnail_path(self, obj: Person) -> str:
        return portrait(obj.id, ImageSizes.SMALL)

    def get_newest_disclosure_url(self, obj: Person) -> str:
        """Get the URL of the"""
        return obj.disclosures[0].get_absolute_url()

    class Meta:
        model = Person
        fields = (
            "position_str",
            "name_full",
            "disclosure_years",
            "thumbnail_path",
            "newest_disclosure_url",
        )


class PersonSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    race = serializers.StringRelatedField(many=True)
    sources = SourceSerializer(many=True, read_only=True)
    aba_ratings = ABARatingSerializer(many=True, read_only=True)
    educations = EducationSerializer(many=True, read_only=True)
    positions = serializers.HyperlinkedRelatedField(
        many=True,
        view_name="position-detail",
        queryset=Position.objects.all(),
        style={"base_template": "input.html"},
    )
    political_affiliations = PoliticalAffiliationSerializer(
        many=True, read_only=True
    )
    is_alias_of = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="person-detail",
        queryset=Person.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = Person
        fields = "__all__"


class RetentionEventSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    position = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="position-detail",
        queryset=Position.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = RetentionEvent
        fields = "__all__"


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
        view_name="position-detail",
        queryset=Position.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = Position
        fields = "__all__"


class CriminalCountSerializer(serializers.ModelSerializer):
    class Meta:
        model = CriminalCount
        fields = "__all__"


class CriminalComplaintSerializer(serializers.ModelSerializer):
    class Meta:
        model = CriminalComplaint
        fields = "__all__"


class PartyTypeSerializer(serializers.HyperlinkedModelSerializer):
    criminal_counts = CriminalCountSerializer(many=True)
    criminal_complaints = CriminalComplaintSerializer(many=True)
    docket_id = serializers.ReadOnlyField()

    class Meta:
        model = PartyType
        fields = (
            "docket",
            "docket_id",
            "name",
            "date_terminated",
            "extra_info",
            "highest_offense_level_opening",
            "highest_offense_level_terminated",
            "criminal_counts",
            "criminal_complaints",
        )


class AttorneyRoleSerializer(serializers.HyperlinkedModelSerializer):
    role = serializers.ChoiceField(choices=Role.ATTORNEY_ROLES)
    attorney_id = serializers.ReadOnlyField()
    docket_id = serializers.ReadOnlyField()

    class Meta:
        model = Role
        fields = (
            "attorney",
            "attorney_id",
            "date_action",
            "docket",
            "docket_id",
            "role",
        )


class PartyRoleSerializer(serializers.HyperlinkedModelSerializer):
    role = serializers.ChoiceField(choices=Role.ATTORNEY_ROLES)

    class Meta:
        model = Role
        fields = ("role", "docket", "party", "date_action")


class DynamicAttorneyRoleSerializer(
    serializers.SerializerMethodField, AttorneyRoleSerializer
):
    """
    Serializes attorney role data by dynamically computing the field's value
    using a serializer method. This combines the flexibility of the
    SerializerMethodField class and allow us to use the schema defined in
    AttorneyRoleSerializer.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.read_only = False


class DynamicPartyTypeSerializer(
    serializers.SerializerMethodField, PartyTypeSerializer
):
    """
    Serializes party type data by dynamically computing the field's value
    using a serializer method. This combines the flexibility of the
    SerializerMethodField class and allow us to use the schema defined in
    PartyTypeSerializer.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.read_only = False


class PartySerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    attorneys = DynamicAttorneyRoleSerializer()
    party_types = DynamicPartyTypeSerializer()

    def get_attorneys(self, obj: Party):
        if hasattr(obj, "filtered_roles"):
            data = obj.filtered_roles
        else:
            data = obj.roles

        return AttorneyRoleSerializer(
            data, many=True, context={"request": self.context["request"]}
        ).data

    def get_party_types(self, obj: Party):
        if hasattr(obj, "filtered_party_types"):
            data = obj.filtered_party_types
        else:
            data = obj.party_types

        return PartyTypeSerializer(
            data, many=True, context={"request": self.context["request"]}
        ).data

    class Meta:
        model = Party
        fields = "__all__"


class DynamicPartySerializer(
    serializers.SerializerMethodField, PartyRoleSerializer
):
    """
    Serializes party data by dynamically computing the field's value using a
    serializer method. This combines the flexibility of the
    SerializerMethodField class and allow us to use the schema defined in
    PartyRoleSerializer.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.read_only = False


class AttorneySerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    parties_represented = DynamicPartySerializer()

    def get_parties_represented(self, obj: Attorney):
        if hasattr(obj, "filtered_roles"):
            data = obj.filtered_roles
        else:
            data = obj.roles

        return PartyRoleSerializer(
            data, many=True, context={"request": self.context["request"]}
        ).data

    class Meta:
        model = Attorney
        exclude = ("organizations",)
