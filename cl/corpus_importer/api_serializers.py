"""Serializers for exporting dockets, with their related data, and opinions as JSON."""

from rest_framework.serializers import CharField, ModelSerializer

from cl.people_db.models import (
    Attorney,
    CriminalComplaint,
    CriminalCount,
    Party,
    PartyType,
    Role,
)
from cl.recap.models import FjcIntegratedDatabase
from cl.search.models import (
    BankruptcyInformation,
    Claim,
    ClaimHistory,
    Docket,
    DocketEntry,
    Opinion,
    OriginatingCourtInformation,
    RECAPDocument,
)


class CriminalCountSerializer(ModelSerializer):
    """Serialize a criminal count without its party type."""

    class Meta:
        model = CriminalCount
        exclude = ("party_type",)


class CriminalComplaintSerializer(ModelSerializer):
    """Serialize a criminal complaint without its party type."""

    class Meta:
        model = CriminalComplaint
        exclude = ("party_type",)


class PartyTypeSerializer(ModelSerializer):
    """Serialize a party type with its criminal counts and complaints."""

    criminal_counts = CriminalCountSerializer(many=True)
    criminal_complaints = CriminalComplaintSerializer(many=True)

    class Meta:
        model = PartyType
        exclude = ("docket", "party")


class RoleSerializer(ModelSerializer):
    """Serialize an attorney's role without its party, attorney, or docket."""

    class Meta:
        model = Role
        exclude = ("party", "attorney", "docket")


class AttorneySerializer(ModelSerializer):
    """Serialize an attorney with their roles."""

    roles = RoleSerializer(many=True)

    class Meta:
        model = Attorney
        exclude = ("organizations",)


class PartySerializer(ModelSerializer):
    """Serialize a party with its attorneys and party types."""

    attorneys = AttorneySerializer(many=True)
    party_types = PartyTypeSerializer(many=True)

    class Meta:
        model = Party
        fields = "__all__"


class RECAPDocumentSerializer(ModelSerializer):
    """Serialize a RECAP document with its URL, without its text or tags."""

    absolute_url = CharField(source="get_absolute_url", read_only=True)

    class Meta:
        model = RECAPDocument
        exclude = ("docket_entry", "plain_text", "tags")


class DocketEntrySerializer(ModelSerializer):
    """Serialize a docket entry with its RECAP documents, without its tags."""

    recap_documents = RECAPDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = DocketEntry
        exclude = ("tags",)


class OriginalCourtInformationSerializer(ModelSerializer):
    """Serialize all fields of a docket's originating court information."""

    class Meta:
        model = OriginatingCourtInformation
        fields = "__all__"


class FjcIntegratedDatabaseSerializer(ModelSerializer):
    """Serialize all fields of an FJC Integrated Database row."""

    class Meta:
        model = FjcIntegratedDatabase
        fields = "__all__"


class BankruptcyInformationSerializer(ModelSerializer):
    """Serialize all fields of a docket's bankruptcy information."""

    class Meta:
        model = BankruptcyInformation
        fields = "__all__"


class ClaimHistorySerializer(ModelSerializer):
    """Serialize a claim history entry without its claim or text."""

    class Meta:
        model = ClaimHistory
        exclude = ("claim", "plain_text")


class ClaimSerializer(ModelSerializer):
    """Serialize a claim with its history entries, without its docket or tags."""

    claim_history_entries = ClaimHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Claim
        exclude = ("docket", "tags")


class IADocketSerializer(ModelSerializer):
    """Serialize a docket with its entries, parties, claims, and related court data."""

    docket_entries = DocketEntrySerializer(many=True, read_only=True)
    parties = PartySerializer(many=True, read_only=True)
    original_court_info = OriginalCourtInformationSerializer(
        source="originating_court_information",
    )
    bankruptcy_information = BankruptcyInformationSerializer()
    claims = ClaimSerializer(many=True, read_only=True)
    idb_data = FjcIntegratedDatabaseSerializer()
    absolute_url = CharField(source="get_absolute_url", read_only=True)

    class Meta:
        model = Docket
        exclude = (
            "view_count",
            "tags",
            "originating_court_information",
            "ia_upload_failure_count",
            "ia_needs_upload",
            "ia_date_first_change",
        )


class OpinionSerializer(ModelSerializer):
    """Serialize all fields of an opinion."""

    class Meta:
        model = Opinion
        fields = "__all__"
