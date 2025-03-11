from datetime import timezone

from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from cl.api.utils import HyperlinkedModelSerializerWithId
from cl.audio.models import Audio
from cl.custom_filters.templatetags.extras import get_highlight
from cl.lib.document_serializer import (
    CoerceDateField,
    DocumentSerializer,
    HighlightedField,
    NoneToListField,
    NullableListField,
    TimeStampField,
)
from cl.people_db.models import PartyType, Person
from cl.recap.api_serializers import FjcIntegratedDatabaseSerializer
from cl.search.constants import o_type_index_map
from cl.search.documents import (
    AudioDocument,
    DocketDocument,
    ESRECAPDocument,
    OpinionClusterDocument,
    OpinionDocument,
    PersonDocument,
    PositionDocument,
)
from cl.search.models import (
    PRECEDENTIAL_STATUS,
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

inverted_o_type_index_map = {
    value: key for key, value in o_type_index_map.items()
}


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
    cluster_id = serializers.ReadOnlyField()
    cluster = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="opinioncluster-detail",
        queryset=OpinionCluster.objects.all(),
        style={"base_template": "input.html"},
    )
    author_id = serializers.ReadOnlyField()
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
    docket_id = serializers.ReadOnlyField()
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


class V3OAESResultSerializer(DocumentSerializer):
    """The serializer for Oral argument results."""

    snippet = serializers.SerializerMethodField(read_only=True)
    panel_ids = NullableListField(read_only=True)
    timestamp = TimeStampField(read_only=True)

    def get_snippet(self, obj):
        # If the snippet has not yet been set upstream, set it here.
        return get_highlight(obj, "text")

    class Meta:
        document = AudioDocument
        exclude = (
            "text",
            "docket_slug",
            "percolator_query",
            "case_name_full",
            "dateArgued_text",
            "dateReargued_text",
            "dateReargumentDenied_text",
            "court_id_text",
        )


class V3PersonESResultSerializer(DocumentSerializer):
    """The serializer for Person results."""

    class Meta:
        document = PersonDocument
        exclude = ("text", "person_child")


class ExtendedPersonESSerializer(V3PersonESResultSerializer):
    """Extends the Person serializer with all the field we get from the db"""

    snippet = serializers.SerializerMethodField(read_only=True)
    appointer = serializers.ListField(read_only=True)
    court = serializers.ListField(read_only=True)
    court_exact = serializers.ListField(read_only=True)
    position_type = serializers.ListField(read_only=True)
    supervisor = serializers.ListField(read_only=True)
    predecessor = serializers.ListField(read_only=True)
    date_nominated = serializers.ListField(read_only=True)
    date_elected = serializers.ListField(read_only=True)
    date_recess_appointment = serializers.ListField(read_only=True)
    date_referred_to_judicial_committee = serializers.ListField(read_only=True)
    date_judicial_committee_action = serializers.ListField(read_only=True)
    date_hearing = serializers.ListField(read_only=True)
    date_confirmation = serializers.ListField(read_only=True)
    date_start = serializers.ListField(read_only=True)
    date_granularity_start = serializers.ListField(read_only=True)
    date_retirement = serializers.ListField(read_only=True)
    date_termination = serializers.ListField(read_only=True)
    date_granularity_termination = serializers.ListField(read_only=True)
    judicial_committee_action = serializers.ListField(read_only=True)
    nomination_process = serializers.ListField(read_only=True)
    selection_method = serializers.ListField(read_only=True)
    selection_method_id = serializers.ListField(read_only=True)
    termination_reason = serializers.ListField(read_only=True)

    def get_snippet(self, obj):
        # If the snippet has not yet been set upstream, set it here.
        return get_highlight(obj, "text")


class V3OpinionESResultSerializer(DocumentSerializer):
    """The serializer for V3 Opinion Search API results."""

    cluster_id = serializers.IntegerField(read_only=True)

    # Fields from the opinion child
    id = serializers.IntegerField(read_only=True)
    snippet = serializers.SerializerMethodField(read_only=True)
    author_id = serializers.IntegerField(read_only=True)
    type = serializers.SerializerMethodField(read_only=True)
    download_url = serializers.CharField(read_only=True)
    local_path = serializers.CharField(read_only=True)
    cites = NullableListField(read_only=True)
    joined_by_ids = NullableListField(read_only=True)
    panel_ids = NullableListField(read_only=True)
    sibling_ids = NullableListField(read_only=True)
    citation = NullableListField(read_only=True)
    per_curiam = serializers.BooleanField(read_only=True)
    court_exact = serializers.CharField(read_only=True, source="court_id")
    timestamp = TimeStampField(read_only=True)
    status = serializers.SerializerMethodField(read_only=True)

    def get_type(self, obj):
        return inverted_o_type_index_map.get(obj.type)

    def get_status(self, obj):
        return PRECEDENTIAL_STATUS.get_status_value_reverse(obj.status)

    def get_snippet(self, obj):
        # If the snippet has not yet been set upstream, set it here.
        return get_highlight(obj, "text")

    class Meta:
        document = OpinionDocument
        exclude = (
            "text",
            "caseNameFull",
            "dateFiled_text",
            "dateArgued_text",
            "dateReargued_text",
            "type_text",
            "dateReargumentDenied_text",
            "posture",
            "syllabus",
            "procedural_history",
            "panel_names",
            "sha1",
        )


class ScoreDataSerializer(serializers.Serializer):
    bm25 = serializers.FloatField(read_only=True, source="bm25_score")


class BaseMetaDataSerializer(serializers.Serializer):
    """The metadata serializer V4 Search API."""

    timestamp = TimeStampField(read_only=True, default_timezone=timezone.utc)
    date_created = TimeStampField(
        read_only=True, default_timezone=timezone.utc
    )


class MainDocumentMetaDataSerializer(BaseMetaDataSerializer):
    """The metadata serializer V4 Search API for main documents.
    Includes the score field.
    """

    score = ScoreDataSerializer(source="*", read_only=True)


class RECAPMetaDataSerializer(MainDocumentMetaDataSerializer):
    """The metadata serializer for the RECAP search type includes the
    additional more_docs field.
    """

    more_docs = serializers.BooleanField(
        read_only=True, source="child_remaining", default=False
    )


class RECAPWebhookMetaDataSerializer(BaseMetaDataSerializer):
    """The metadata serializer for the RECAP search Webhook that includes the
    additional more_docs field without the score field.
    """

    more_docs = serializers.BooleanField(
        read_only=True, source="child_remaining", default=False
    )


class MainMetaMixin(serializers.Serializer):
    """Mixin to add nested metadata serializer for main documents."""

    meta = MainDocumentMetaDataSerializer(source="*", read_only=True)


class ChildMetaMixin(serializers.Serializer):
    """Mixin to add nested metadata serializer for child documents."""

    meta = BaseMetaDataSerializer(source="*", read_only=True)


class BaseRECAPDocumentESResultSerializer(DocumentSerializer):
    """The base serializer class for RECAP_DOCUMENT search type results."""

    # Fields from the RECAPDocument
    cites = NoneToListField(read_only=True, required=False)
    description = HighlightedField(read_only=True)
    short_description = HighlightedField(read_only=True)
    snippet = HighlightedField(read_only=True, source="plain_text")

    class Meta:
        document = ESRECAPDocument
        exclude = (
            "caseName",
            "case_name_full",
            "docketNumber",
            "suitNature",
            "cause",
            "juryDemand",
            "jurisdictionType",
            "dateArgued",
            "dateFiled",
            "dateTerminated",
            "assignedTo",
            "assigned_to_id",
            "referredTo",
            "referred_to_id",
            "court",
            "court_id",
            "court_citation_string",
            "chapter",
            "trustee_str",
            "date_created",
            "timestamp",
            "pacer_case_id",
            "plain_text",
            "docket_id",
        )


class NestedRECAPDocumentESResultSerializer(
    BaseRECAPDocumentESResultSerializer, ChildMetaMixin
):
    """Mixin to add nested metadata serializer for nested Recap documents."""


class BaseDocketESResultSerializer(DocumentSerializer):
    """The serializer class for DOCKETS Search type results."""

    # Fields from the Docket.
    referred_to_id = serializers.IntegerField(read_only=True)
    assigned_to_id = serializers.IntegerField(read_only=True)
    dateArgued = CoerceDateField(read_only=True)
    dateFiled = CoerceDateField(read_only=True)
    dateTerminated = CoerceDateField(read_only=True)
    assignedTo = HighlightedField(read_only=True)
    caseName = HighlightedField(read_only=True)
    cause = HighlightedField(read_only=True)
    court_citation_string = HighlightedField(read_only=True)
    docketNumber = HighlightedField(read_only=True)
    juryDemand = HighlightedField(read_only=True)
    referredTo = HighlightedField(read_only=True)
    suitNature = HighlightedField(read_only=True)
    party_id = NoneToListField(read_only=True, required=False)
    party = NoneToListField(read_only=True, required=False)
    attorney_id = NoneToListField(read_only=True, required=False)
    attorney = NoneToListField(read_only=True, required=False)
    firm_id = NoneToListField(read_only=True, required=False)
    firm = NoneToListField(read_only=True, required=False)

    class Meta:
        document = DocketDocument
        exclude = (
            "_related_instance_to_ignore",
            "docket_child",
            "docket_slug",
            "court_exact",
            "timestamp",
            "date_created",
        )


class RECAPDocumentESResultSerializer(
    BaseRECAPDocumentESResultSerializer, MainMetaMixin
):
    """The serializer for RECAP_DOCUMENT search type results."""

    docket_id = serializers.IntegerField(read_only=True)


class DocketESResultSerializer(MainMetaMixin, BaseDocketESResultSerializer):
    """The serializer class for DOCKETS Search type results."""


class RECAPESResultSerializer(BaseDocketESResultSerializer):
    """The serializer class for RECAP search type results."""

    recap_documents = NestedRECAPDocumentESResultSerializer(
        many=True, read_only=True, source="child_docs"
    )
    meta = RECAPMetaDataSerializer(source="*", read_only=True)


class RECAPESWebhookResultSerializer(BaseDocketESResultSerializer):
    """The serializer class for RECAP search Webhooks results."""

    recap_documents = NestedRECAPDocumentESResultSerializer(
        many=True, read_only=True, source="child_docs"
    )
    meta = RECAPWebhookMetaDataSerializer(source="*", read_only=True)


class OpinionDocumentESResultSerializer(ChildMetaMixin, DocumentSerializer):
    """The serializer for OpinionDocument results."""

    snippet = HighlightedField(read_only=True, source="text")
    joined_by_ids = NoneToListField(read_only=True, required=False)

    class Meta:
        document = OpinionDocument
        fields = (
            "id",
            "author_id",
            "type",
            "per_curiam",
            "download_url",
            "local_path",
            "sha1",
            "cites",
            "ordering_key",
        )


class OpinionClusterBaseESResultSerializer(DocumentSerializer):
    """The serializer for OpinionCluster Search results."""

    opinions = OpinionDocumentESResultSerializer(
        many=True, read_only=True, source="child_docs"
    )
    dateArgued = CoerceDateField(read_only=True)
    dateFiled = CoerceDateField(read_only=True)
    dateReargued = CoerceDateField(read_only=True)
    dateReargumentDenied = CoerceDateField(read_only=True)
    caseName = HighlightedField(read_only=True)
    court_citation_string = HighlightedField(read_only=True)
    docketNumber = HighlightedField(read_only=True)
    suitNature = HighlightedField(read_only=True)
    panel_names = NoneToListField(read_only=True, required=False)
    citation = NoneToListField(read_only=True, required=False)
    sibling_ids = NoneToListField(read_only=True, required=False)
    panel_ids = NoneToListField(read_only=True, required=False)

    class Meta:
        document = OpinionClusterDocument
        exclude = (
            "court_exact",
            "_related_instance_to_ignore",
            "cluster_child",
            "date_created",
            "timestamp",
        )


class OpinionClusterESResultSerializer(
    OpinionClusterBaseESResultSerializer, MainMetaMixin
):
    """The serializer for OpinionCluster Search results."""


class OpinionClusterWebhookResultSerializer(
    OpinionClusterBaseESResultSerializer
):
    """The serializer class for OpinionCluster search Webhooks results."""

    meta = BaseMetaDataSerializer(source="*", read_only=True)


class PositionESResultSerializer(ChildMetaMixin, DocumentSerializer):
    """The serializer for Positions Search results."""

    class Meta:
        document = PositionDocument
        exclude = (
            "absolute_url",
            "absolute_url",
            "date_granularity_dob",
            "date_granularity_dod",
            "id",
            "alias_ids",
            "races",
            "political_affiliation_id",
            "fjc_id",
            "name",
            "gender",
            "religion",
            "alias",
            "dob",
            "dod",
            "dob_city",
            "dob_state",
            "dob_state_id",
            "political_affiliation",
            "positions",
            "aba_rating",
            "school",
            "_related_instance_to_ignore",
            "person_child",
            "date_created",
            "timestamp",
        )


class PersonESResultSerializer(MainMetaMixin, DocumentSerializer):
    """The serializer for Person Search results."""

    name = HighlightedField(read_only=True)
    dob_city = HighlightedField(read_only=True)
    dob_state_id = HighlightedField(read_only=True)
    dob = CoerceDateField(read_only=True)
    dod = CoerceDateField(read_only=True)
    political_affiliation = NoneToListField(read_only=True, required=False)
    political_affiliation_id = NoneToListField(read_only=True, required=False)
    aba_rating = NoneToListField(read_only=True, required=False)
    school = NoneToListField(read_only=True, required=False)
    races = NoneToListField(read_only=True, required=False)
    alias = NoneToListField(read_only=True, required=False)
    alias_ids = NoneToListField(read_only=True, required=False)
    positions = PositionESResultSerializer(
        many=True, read_only=True, source="child_docs"
    )

    class Meta:
        document = PersonDocument
        exclude = (
            "_related_instance_to_ignore",
            "person_child",
            "name_reverse",
            "date_created",
            "timestamp",
        )


class OAESResultSerializer(MainMetaMixin, DocumentSerializer):
    """The serializer for V4 Oral argument results."""

    snippet = HighlightedField(read_only=True, source="text")
    dateArgued = CoerceDateField(read_only=True)
    dateReargued = CoerceDateField(read_only=True)
    dateReargumentDenied = CoerceDateField(read_only=True)
    panel_ids = NoneToListField(read_only=True)
    caseName = HighlightedField(read_only=True)
    judge = HighlightedField(read_only=True)
    docketNumber = HighlightedField(read_only=True)
    court_citation_string = HighlightedField(read_only=True)

    class Meta:
        document = AudioDocument
        exclude = (
            "court_exact",
            "text",
            "docket_slug",
            "percolator_query",
            "dateArgued_text",
            "dateReargued_text",
            "dateReargumentDenied_text",
            "court_id_text",
            "timestamp",
            "date_created",
        )


class V3RECAPDocumentESResultSerializer(DocumentSerializer):
    """The V3 serializer class for RECAP search type results."""

    referred_to_id = serializers.IntegerField(read_only=True)
    assigned_to_id = serializers.IntegerField(read_only=True)
    description = HighlightedField(read_only=True)
    short_description = HighlightedField(read_only=True)
    snippet = serializers.SerializerMethodField(read_only=True)
    court_exact = serializers.CharField(read_only=True, source="court_id")
    timestamp = TimeStampField(read_only=True)

    def get_snippet(self, obj):
        # If the snippet has not yet been set upstream, set it here.
        return get_highlight(obj, "plain_text")

    class Meta:
        document = ESRECAPDocument
        exclude = (
            "case_name_full",
            "date_created",
            "pacer_case_id",
            "plain_text",
            "docket_absolute_url",
            "chapter",
            "cites",
            "pacer_doc_id",
            "trustee_str",
        )
