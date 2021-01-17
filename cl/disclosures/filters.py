from rest_framework_filters import FilterSet, filters

from cl.api.utils import ALL_TEXT_LOOKUPS, BOOLEAN_LOOKUPS, DATETIME_LOOKUPS
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

disclosure_fields = {
    "id": ["exact"],
    "date_created": DATETIME_LOOKUPS,
    "date_modified": DATETIME_LOOKUPS,
    "redacted": BOOLEAN_LOOKUPS,
}


class AgreementFilter(FilterSet):
    financial_disclosure = filters.RelatedFilter(
        "cl.disclosures.filters.FinancialDisclosureFilter",
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = Agreement
        fields = disclosure_fields.copy()
        fields.update({"parties_and_terms": ALL_TEXT_LOOKUPS})


class DebtFilter(FilterSet):
    financial_disclosure = filters.RelatedFilter(
        "cl.disclosures.filters.FinancialDisclosureFilter",
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = Debt
        fields = disclosure_fields.copy()


class FinancialDisclosureFilter(FilterSet):

    agreements = filters.RelatedFilter(
        AgreementFilter,
        queryset=FinancialDisclosure.objects.all(),
    )
    debts = filters.RelatedFilter(
        DebtFilter,
        queryset=FinancialDisclosure.objects.all(),
    )
    gifts = filters.RelatedFilter(
        "cl.disclosures.filters.GiftFilter",
        queryset=FinancialDisclosure.objects.all(),
    )
    investments = filters.RelatedFilter(
        "cl.disclosures.filters.InvestmentFilter",
        queryset=FinancialDisclosure.objects.all(),
    )
    non_investment_incomes = filters.RelatedFilter(
        "cl.disclosures.filters.NonInvestmentIncomeFilter",
        queryset=FinancialDisclosure.objects.all(),
    )
    person = filters.RelatedFilter(
        "cl.people_db.filters.PersonFilter",
        queryset=Person.objects.all(),
    )
    positions = filters.RelatedFilter(
        "cl.disclosures.filters.PositionFilter",
        queryset=FinancialDisclosure.objects.all(),
    )
    reimbursements = filters.RelatedFilter(
        "cl.disclosures.filters.ReimbursementFilter",
        queryset=FinancialDisclosure.objects.all(),
    )
    spouse_incomes = filters.RelatedFilter(
        "cl.disclosures.filters.SpouseIncomeFilter",
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = FinancialDisclosure
        fields = {
            "id": ["exact"],
            "person": ["exact"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "addendum_content_raw": ALL_TEXT_LOOKUPS,
            "has_been_extracted": BOOLEAN_LOOKUPS,
        }


class GiftFilter(FilterSet):

    financial_disclosure = filters.RelatedFilter(
        FinancialDisclosureFilter,
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = Gift
        fields = {
            "id": ["exact"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "redacted": BOOLEAN_LOOKUPS,
        }


class InvestmentFilter(FilterSet):
    financial_disclosure = filters.RelatedFilter(
        FinancialDisclosureFilter,
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = Investment
        fields = disclosure_fields.copy()
        fields.update(
            {
                "description": ALL_TEXT_LOOKUPS,
                "gross_value_code": ["exact"],
                "income_during_reporting_period_code": ["exact"],
                "transaction_during_reporting_period": ALL_TEXT_LOOKUPS,
                "transaction_value_code": ["exact"],
            }
        )


class NonInvestmentIncomeFilter(FilterSet):
    financial_disclosure = filters.RelatedFilter(
        FinancialDisclosureFilter,
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = NonInvestmentIncome
        fields = disclosure_fields.copy()


class PositionFilter(FilterSet):
    financial_disclosure = filters.RelatedFilter(
        FinancialDisclosureFilter,
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = Position
        fields = disclosure_fields.copy()


class ReimbursementFilter(FilterSet):
    financial_disclosure = filters.RelatedFilter(
        FinancialDisclosureFilter,
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = Reimbursement
        fields = disclosure_fields.copy()


class SpouseIncomeFilter(FilterSet):
    financial_disclosure = filters.RelatedFilter(
        FinancialDisclosureFilter,
        queryset=FinancialDisclosure.objects.all(),
    )

    class Meta:
        model = SpouseIncome
        fields = disclosure_fields.copy()
