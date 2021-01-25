from drf_dynamic_fields import DynamicFieldsMixin

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
from cl.people_db.api_serializers import PersonSerializer


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
    person = PersonSerializer(many=False, read_only=True)

    class Meta:
        model = FinancialDisclosure
        exclude = ("download_filepath",)
