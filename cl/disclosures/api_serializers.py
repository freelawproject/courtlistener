"""REST API serializers for financial disclosures and their parts."""

from django.conf import settings
from rest_framework import serializers

from cl.api.utils import (
    DynamicFieldsMixin,
    HyperlinkedModelSerializerWithId,
    NestedDynamicFieldsMixin,
    RetrieveFilteredFieldsMixin,
)
from cl.disclosures.models import (
    Agreement,
    Debt,
    FinancialDisclosure,
    Gift,
    Investment,
    NonInvestmentIncome,
    Position,
    Reimbursement,
    SpouseIncome,
)
from cl.people_db.models import Person


class AgreementSerializer(
    RetrieveFilteredFieldsMixin,
    NestedDynamicFieldsMixin,
    HyperlinkedModelSerializerWithId,
):
    """Serializer for disclosed agreements."""

    class Meta:
        model = Agreement
        fields = "__all__"


class DebtSerializer(
    RetrieveFilteredFieldsMixin,
    NestedDynamicFieldsMixin,
    HyperlinkedModelSerializerWithId,
):
    """Serializer for disclosed debts."""

    class Meta:
        model = Debt
        fields = "__all__"


class InvestmentSerializer(
    RetrieveFilteredFieldsMixin,
    NestedDynamicFieldsMixin,
    HyperlinkedModelSerializerWithId,
):
    """Serializer for disclosed investments."""

    class Meta:
        model = Investment
        fields = "__all__"


class GiftSerializer(
    RetrieveFilteredFieldsMixin,
    DynamicFieldsMixin,
    HyperlinkedModelSerializerWithId,
):
    """Serializer for disclosed gifts."""

    class Meta:
        model = Gift
        fields = "__all__"


class NonInvestmentIncomeSerializer(
    RetrieveFilteredFieldsMixin,
    NestedDynamicFieldsMixin,
    HyperlinkedModelSerializerWithId,
):
    """Serializer for disclosed non-investment income."""

    class Meta:
        model = NonInvestmentIncome
        fields = "__all__"


class PositionSerializer(
    RetrieveFilteredFieldsMixin,
    NestedDynamicFieldsMixin,
    HyperlinkedModelSerializerWithId,
):
    """Serializer for disclosed positions."""

    resource_uri = serializers.SerializerMethodField()

    def get_resource_uri(self, position: Position) -> str:
        """Override incorrect resource uri in disclousre-position api.

        This 'hack' is used to correctly generate the resource_uri field
        in the api. Currently django-rest-framework auto-generates the
        wrong api location, because of the positions table in the people model.

        Here we are simply overriding the incorrect field with the correct one
        by passing in the correct path and id.

        Args:
            position: The position object

        Returns:
            Corrected resouce_uri
        """
        path = f"/api/rest/v3/disclosure-positions/{position.id}/"
        return self.context["request"].build_absolute_uri(path)

    class Meta:
        model = Position
        fields = "__all__"


class ReimbursementSerializer(
    RetrieveFilteredFieldsMixin,
    NestedDynamicFieldsMixin,
    HyperlinkedModelSerializerWithId,
):
    """Serializer for disclosed reimbursements."""

    class Meta:
        model = Reimbursement
        fields = "__all__"


class SpouseIncomeSerializer(
    RetrieveFilteredFieldsMixin,
    NestedDynamicFieldsMixin,
    HyperlinkedModelSerializerWithId,
):
    """Serializer for disclosed spouse income."""

    class Meta:
        model = SpouseIncome
        fields = "__all__"


class FinancialDisclosureSerializer(
    RetrieveFilteredFieldsMixin,
    NestedDynamicFieldsMixin,
    HyperlinkedModelSerializerWithId,
):
    """Serializer for financial disclosures, with their parts nested."""

    agreements = AgreementSerializer(many=True, read_only=True)
    debts = DebtSerializer(many=True, read_only=True)
    gifts = GiftSerializer(many=True, read_only=True)
    investments = InvestmentSerializer(many=True, read_only=True)
    non_investment_incomes = NonInvestmentIncomeSerializer(
        many=True, read_only=True
    )
    positions = PositionSerializer(many=True, read_only=True)
    reimbursements = ReimbursementSerializer(many=True, read_only=True)
    spouse_incomes = SpouseIncomeSerializer(many=True, read_only=True)
    person = serializers.HyperlinkedRelatedField(
        many=False,
        view_name="person-detail",
        queryset=Person.objects.all(),
        style={"base_template": "input.html"},
    )
    filepath = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = FinancialDisclosure
        exclude = ("download_filepath",)

    def get_filepath(self, disclosure):
        """Get the disclosure PDF's URL in storage."""
        return f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{disclosure.filepath}"

    def get_thumbnail(self, disclosure):
        """Get the disclosure thumbnail's URL in storage."""
        return (
            f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{disclosure.thumbnail}"
        )
