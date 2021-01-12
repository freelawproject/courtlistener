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


class AgreementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agreement
        fields = "__all__"


class DebtSerializer(serializers.ModelSerializer):
    class Meta:
        model = Debt
        fields = "__all__"


class InvestmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Investment
        fields = "__all__"


class GiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gift
        fields = "__all__"


class NonInvestmentIncomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NonInvestmentIncome
        fields = "__all__"


class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = "__all__"


class ReimbursementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reimbursement
        fields = "__all__"


class SpouseIncomeSerializer(serializers.ModelSerializer):
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

    class Meta:
        model = FinancialDisclosure

        fields = (
            "agreements",
            "debts",
            "gifts",
            "investments",
            "non_investment_incomes",
            "positions",
            "reimbursements",
            "spouse_incomes",
            "person",
        )
