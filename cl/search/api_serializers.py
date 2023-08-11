from collections import OrderedDict

from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from cl.api.utils import HyperlinkedModelSerializerWithId
from cl.audio.models import Audio
from cl.people_db.models import PartyType, Person
from cl.recap.api_serializers import FjcIntegratedDatabaseSerializer
from cl.search.models import (
    Citation,
    Court,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    OriginatingCourtInformation,
    RECAPDocument,
    Tag,
)


class PartyTypeSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    party_type = serializers.CharField(source="name")

    class Meta:
        model = PartyType
        fields = (
            "party",
            "party_type",
        )


class OriginalCourtInformationSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    class Meta:
        model = OriginatingCourtInformation
        fields = "__all__"


class DocketSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    court = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="court-detail",
        queryset=Court.objects.exclude(jurisdiction=Court.TESTING_COURT),
    )
    court_id = serializers.ReadOnlyField()
    original_court_info = OriginalCourtInformationSerializer(
        source="originating_court_information",
    )
    idb_data = FjcIntegratedDatabaseSerializer()
    clusters = serializers.HyperlinkedRelatedField(
        many=True,
        view_name="opinioncluster-detail",
        queryset=OpinionCluster.objects.all(),
        style={"base_template": "input.html"},
    )
    audio_files = serializers.HyperlinkedRelatedField(
        many=True,
        view_name="audio-detail",
        queryset=Audio.objects.all(),
        style={"base_template": "input.html"},
    )
    assigned_to = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="person-detail",
        queryset=Person.objects.all(),
        style={"base_template": "input.html"},
    )
    referred_to = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="person-detail",
        queryset=Person.objects.all(),
        style={"base_template": "input.html"},
    )
    absolute_url = serializers.CharField(
        source="get_absolute_url", read_only=True
    )

    class Meta:
        model = Docket
        exclude = (
            "view_count",
            "parties",
            "originating_court_information",
            "filepath_local",
        )


class RECAPDocumentSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    tags = serializers.HyperlinkedRelatedField(
        many=True,
        view_name="tag-detail",
        queryset=Tag.objects.all(),
        style={"base_template": "input.html"},
    )
    absolute_url = serializers.CharField(
        source="get_absolute_url", read_only=True
    )

    class Meta:
        model = RECAPDocument
        exclude = ("docket_entry",)


class DocketEntrySerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    docket = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="docket-detail",
        queryset=Docket.objects.all(),
        style={"base_template": "input.html"},
    )
    recap_documents = RECAPDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = DocketEntry
        fields = "__all__"


class FullDocketSerializer(DocketSerializer):
    docket_entries = DocketEntrySerializer(many=True, read_only=True)


class CourtSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    class Meta:
        model = Court
        exclude = ("notes",)


class OpinionSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    absolute_url = serializers.CharField(
        source="get_absolute_url", read_only=True
    )
    cluster = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="opinioncluster-detail",
        queryset=OpinionCluster.objects.all(),
        style={"base_template": "input.html"},
    )
    author = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="person-detail",
        queryset=Person.objects.all(),
        style={"base_template": "input.html"},
    )
    joined_by = serializers.HyperlinkedRelatedField(
        many=True,
        view_name="person-detail",
        queryset=Person.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = Opinion
        fields = "__all__"


class OpinionsCitedSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    # These attributes seem unnecessary and this endpoint serializes the same
    # data without them, but when they're not here the API does a query that
    # pulls back ALL Opinions.
    citing_opinion = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="opinion-detail",
        queryset=Opinion.objects.all(),
        style={"base_template": "input.html"},
    )
    cited_opinion = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="opinion-detail",
        queryset=Opinion.objects.all(),
        style={"base_template": "input.html"},
    )

    class Meta:
        model = OpinionsCited
        fields = "__all__"


class CitationSerializer(ModelSerializer):
    class Meta:
        model = Citation
        exclude = (
            "id",
            "cluster",
        )


class OpinionClusterSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    absolute_url = serializers.CharField(
        source="get_absolute_url", read_only=True
    )
    panel = serializers.HyperlinkedRelatedField(
        many=True,
        view_name="person-detail",
        queryset=Person.objects.all(),
        style={"base_template": "input.html"},
    )
    non_participating_judges = serializers.HyperlinkedRelatedField(
        many=True,
        view_name="person-detail",
        queryset=Person.objects.all(),
        style={"base_template": "input.html"},
    )
    docket = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="docket-detail",
        queryset=Docket.objects.all(),
        style={"base_template": "input.html"},
    )
    sub_opinions = serializers.HyperlinkedRelatedField(
        many=True,
        view_name="opinion-detail",
        queryset=Opinion.objects.all(),
        style={"base_template": "input.html"},
    )
    citations = CitationSerializer(many=True)

    class Meta:
        model = OpinionCluster
        fields = "__all__"


class TagSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    class Meta:
        model = Tag
        fields = "__all__"


class SearchResultSerializer(serializers.Serializer):
    """The serializer for search results.

    Does not presently support the fields argument.
    """

    def update(self, instance, validated_data):
        raise NotImplementedError

    def create(self, validated_data):
        raise NotImplementedError

    solr_field_mappings = {
        "boolean": serializers.BooleanField,
        "string": serializers.CharField,
        "text_en_splitting_cl": serializers.CharField,
        "text_no_word_parts": serializers.CharField,
        "date": serializers.DateTimeField,
        # Numbers
        "int": serializers.IntegerField,
        "tint": serializers.IntegerField,
        "long": serializers.IntegerField,
        # schema.SolrFloatField: serializers.FloatField,
        # schema.SolrDoubleField: serializers.IntegerField,
        # Other
        "pagerank": serializers.CharField,
    }
    skipped_fields = ["_version_", "django_ct", "django_id", "text"]

    def get_fields(self):
        """Return a list of fields so that they don't have to be declared one
        by one and updated whenever there's a new field.
        """
        fields = {
            "snippet": serializers.CharField(read_only=True),
        }
        # Map each field in the Solr schema to a DRF field
        for field in self._context["schema"]["fields"]:
            if field.get("multiValued"):
                drf_field = serializers.ListField
            else:
                drf_field = self.solr_field_mappings[field["type"]]
            fields[field["name"]] = drf_field(read_only=True)

        for field in self.skipped_fields:
            if field in fields:
                fields.pop(field)
        fields = OrderedDict(sorted(fields.items()))  # Sort by key
        return fields


class SearchESResultSerializer(serializers.Serializer):
    """The serializer for Elasticsearch results.
    Does not presently support the fields argument.
    """

    def update(self, instance, validated_data):
        raise NotImplementedError

    def create(self, validated_data):
        raise NotImplementedError

    es_field_mappings = {
        "boolean": serializers.BooleanField,
        "text": serializers.CharField,
        "keyword": serializers.CharField,
        "date": serializers.DateTimeField,
        # Numbers
        "integer": serializers.IntegerField,
    }
    skipped_fields = ["text", "docket_slug", "percolator_query"]

    def get_fields(self):
        """Return a list of fields so that they don't have to be declared one
        by one and updated whenever there's a new field.
        """
        fields = {
            "snippet": serializers.CharField(read_only=True),
            "panel_ids": serializers.ListField(read_only=True),
        }

        properties = self._context["schema"]["properties"]
        # Map each field in the ES schema to a DRF field
        for field_name, value in properties.items():
            if field_name in fields or field_name in self.skipped_fields:
                # Exclude fields that are already set in fields.
                continue
            drf_field = self.es_field_mappings[properties[field_name]["type"]]
            fields[field_name] = drf_field(read_only=True)

        for field in self.skipped_fields:
            if field in fields:
                fields.pop(field)

        fields = OrderedDict(sorted(fields.items()))  # Sort by key
        return fields
