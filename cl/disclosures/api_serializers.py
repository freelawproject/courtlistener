from drf_dynamic_fields import DynamicFieldsMixin
from rest_framework import serializers

from cl.api.utils import HyperlinkedModelSerializerWithId
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
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    class Meta:
        model = Agreement
        fields = "__all__"


class DebtSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    class Meta:
        model = Debt
        fields = "__all__"


class InvestmentSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    class Meta:
        model = Investment
        fields = "__all__"


class GiftSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    class Meta:
        model = Gift
        fields = "__all__"


class NonInvestmentIncomeSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    class Meta:
        model = NonInvestmentIncome
        fields = "__all__"


class PositionSerializer(DynamicFieldsMixin, HyperlinkedModelSerializerWithId):
    class Meta:
        model = Position
        fields = "__all__"


class ReimbursementSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    class Meta:
        model = Reimbursement
        fields = "__all__"


class SpouseIncomeSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):
    class Meta:
        model = SpouseIncome
        fields = "__all__"


class FinancialDisclosureSerializer(
    DynamicFieldsMixin, HyperlinkedModelSerializerWithId
):

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

    class Meta:
        model = FinancialDisclosure
        exclude = ("download_filepath",)
