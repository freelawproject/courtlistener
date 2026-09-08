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


class CriminalCountSerializer(ModelSerializer[CriminalCount]):
    class Meta(ModelSerializer.Meta):
        model = CriminalCount
        exclude = ("party_type",)


class CriminalComplaintSerializer(ModelSerializer[CriminalComplaint]):
    class Meta(ModelSerializer.Meta):
        model = CriminalComplaint
        exclude = ("party_type",)


class PartyTypeSerializer(ModelSerializer[PartyType]):
    criminal_counts = CriminalCountSerializer(many=True)
    criminal_complaints = CriminalComplaintSerializer(many=True)

    class Meta(ModelSerializer.Meta):
        model = PartyType
        exclude = ("docket", "party")


class RoleSerializer(ModelSerializer[Role]):
    class Meta(ModelSerializer.Meta):
        model = Role
        exclude = ("party", "attorney", "docket")


class AttorneySerializer(ModelSerializer[Attorney]):
    roles = RoleSerializer(many=True)

    class Meta(ModelSerializer.Meta):
        model = Attorney
        exclude = ("organizations",)


class PartySerializer(ModelSerializer[Party]):
    attorneys = AttorneySerializer(many=True)
    party_types = PartyTypeSerializer(many=True)

    class Meta(ModelSerializer.Meta):
        model = Party
        fields = "__all__"


class RECAPDocumentSerializer(ModelSerializer[RECAPDocument]):
    absolute_url = CharField(source="get_absolute_url", read_only=True)

    class Meta(ModelSerializer.Meta):
        model = RECAPDocument
        exclude = ("docket_entry", "plain_text", "tags")


class DocketEntrySerializer(ModelSerializer[DocketEntry]):
    recap_documents = RECAPDocumentSerializer(many=True, read_only=True)

    class Meta(ModelSerializer.Meta):
        model = DocketEntry
        exclude = ("tags",)


class OriginalCourtInformationSerializer(
    ModelSerializer[OriginatingCourtInformation]
):
    class Meta(ModelSerializer.Meta):
        model = OriginatingCourtInformation
        fields = "__all__"


class FjcIntegratedDatabaseSerializer(ModelSerializer[FjcIntegratedDatabase]):
    class Meta(ModelSerializer.Meta):
        model = FjcIntegratedDatabase
        fields = "__all__"


class BankruptcyInformationSerializer(ModelSerializer[BankruptcyInformation]):
    class Meta(ModelSerializer.Meta):
        model = BankruptcyInformation
        fields = "__all__"


class ClaimHistorySerializer(ModelSerializer[ClaimHistory]):
    class Meta(ModelSerializer.Meta):
        model = ClaimHistory
        exclude = ("claim", "plain_text")


class ClaimSerializer(ModelSerializer[Claim]):
    claim_history_entries = ClaimHistorySerializer(many=True, read_only=True)

    class Meta(ModelSerializer.Meta):
        model = Claim
        exclude = ("docket", "tags")


class IADocketSerializer(ModelSerializer[Docket]):
    docket_entries = DocketEntrySerializer(many=True, read_only=True)
    parties = PartySerializer(many=True, read_only=True)
    original_court_info = OriginalCourtInformationSerializer(
        source="originating_court_information",
    )
    bankruptcy_information = BankruptcyInformationSerializer()
    claims = ClaimSerializer(many=True, read_only=True)
    idb_data = FjcIntegratedDatabaseSerializer()
    absolute_url = CharField(source="get_absolute_url", read_only=True)

    class Meta(ModelSerializer.Meta):
        model = Docket
        exclude = (
            "view_count",
            "tags",
            "originating_court_information",
            "ia_upload_failure_count",
            "ia_needs_upload",
            "ia_date_first_change",
        )


class OpinionSerializer(ModelSerializer[Opinion]):
    class Meta(ModelSerializer.Meta):
        model = Opinion
        fields = "__all__"
