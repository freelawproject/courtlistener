from rest_framework.serializers import CharField
from rest_framework.serializers import ModelSerializer

from cl.people_db.models import Party, Role, PartyType, Attorney, \
    CriminalCount, CriminalComplaint
from cl.search.models import RECAPDocument, Docket, DocketEntry, \
    OriginatingCourtInformation


class CriminalCountSerializer(ModelSerializer):
    class Meta:
        model = CriminalCount
        exclude = ('party_type',)


class CriminalComplaintSerializer(ModelSerializer):
    class Meta:
        model = CriminalComplaint
        exclude = ('party_type',)


class PartyTypeSerializer(ModelSerializer):
    criminal_counts = CriminalCountSerializer(many=True)
    criminal_complaints = CriminalComplaintSerializer(many=True)

    class Meta:
        model = PartyType
        exclude = ('docket', 'party')


class RoleSerializer(ModelSerializer):
    class Meta:
        model = Role
        exclude = ('party', 'attorney', 'docket')


class AttorneySerializer(ModelSerializer):
    roles = RoleSerializer(many=True)

    class Meta:
        model = Attorney
        exclude = ('organizations',)


class PartySerializer(ModelSerializer):
    attorneys = AttorneySerializer(many=True)
    party_types = PartyTypeSerializer(many=True)

    class Meta:
        model = Party
        fields = '__all__'


class RECAPDocumentSerializer(ModelSerializer):
    absolute_url = CharField(source='get_absolute_url', read_only=True)

    class Meta:
        model = RECAPDocument
        exclude = ('docket_entry', 'plain_text', 'tags')


class DocketEntrySerializer(ModelSerializer):
    recap_documents = RECAPDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = DocketEntry
        exclude = ('tags', 'docket')


class OriginalCourtInformationSerializer(ModelSerializer):

    class Meta:
        model = OriginatingCourtInformation
        fields = '__all__'


class IADocketSerializer(ModelSerializer):
    docket_entries = DocketEntrySerializer(many=True, read_only=True)
    parties = PartySerializer(many=True, read_only=True)
    original_court_info = OriginalCourtInformationSerializer(
        source='originating_court_information',
    )
    absolute_url = CharField(source='get_absolute_url', read_only=True)

    class Meta:
        model = Docket
        exclude = ('view_count', 'tags', 'originating_court_information',
                   'ia_upload_failure_count', 'ia_needs_upload')
